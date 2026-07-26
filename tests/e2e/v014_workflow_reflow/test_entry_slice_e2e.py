"""Browser e2e for the v0.14-001 public-entry slice (installed wheel).

AC-FR0100-01/02, AC-FR0300-01/02, AC-FR0400-01/02/03, AC-FR0500-01/03,
AC-FR0600-02, AC-FR0700-01/02/03, AC-FR0800-01.

The test drives the installed ``lk serve`` through a real Chromium browser
on a random loopback port.  Every page action (login, readiness,
``/projects/new`` preview/confirm, Foundation redirect, Story page, Scribe
Chat, reconcile, Human Go decision) goes through the public Web surface.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import pytest

from tests.fixtures.v014_workflow_reflow.harness import CANONICAL_HUMAN_STORY


def _chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


def _session_cookie(page, base_url: str) -> str:
    for c in page.context.cookies(base_url):
        if c["name"] == "louke_session":
            return c["value"].strip('"')
    return ""


def _csrf_from_page(page) -> str:
    return page.evaluate(
        """() => {
            const m = document.documentElement.innerHTML.match(/const\\s+csrf\\s*=\\s*["']([a-f0-9]+)["']/);
            if (m) return m[1];
            const el = document.querySelector('[data-csrf]');
            return el ? el.dataset.csrf : '';
        }"""
    )


@pytest.mark.v014_entry_e2e
@pytest.mark.skipif(
    not _chromium_installed(),
    reason="Chromium or Playwright is not installed (AC-NFR0300-01)",
)
def test_v014_entry_slice_golden_journey(live_server, browser_page):
    """AC-FR0100..0800: installed-wheel browser journey through the entry slice.

    Drives Chromium through: login -> preview/confirm -> Foundation redirect
    -> Story page -> Scribe Chat binding -> reconcile (provider result
    ingestion) -> waiting_for_human -> Human Go decision -> persisted
    actor/revision/digest while remaining at M-STORY.
    """
    page, base_url = browser_page
    _, workspace, opencode = live_server

    # AC-FR0100-01: register
    reg = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert reg.ok, reg.text()

    # AC-FR0300-01: preview
    page.goto(f"{base_url}/projects/new", wait_until="domcontentloaded")
    csrf = _csrf_from_page(page)
    assert csrf
    h = {"Content-Type": "application/json", "Origin": base_url, "X-Louke-CSRF": csrf}

    preview = page.request.post(
        f"{base_url}/api/v14/releases/preview",
        data=json.dumps({"story": CANONICAL_HUMAN_STORY, "release_version": "0.14.0"}),
        headers=h,
    )
    assert preview.ok, preview.text()
    pb = preview.json()
    assert pb["side_effects"] == []

    # AC-FR0300-02/AC-FR0400-02: confirm + Foundation
    confirm = page.request.post(
        f"{base_url}/api/v14/releases/confirm",
        data=json.dumps(
            {
                "preview_id": pb["preview_id"],
                "expected_preview_revision": pb["preview_revision"],
                "request_digest": pb["request_digest"],
                "idempotency_key": "e2e-confirm-1",
            }
        ),
        headers=h,
    )
    assert confirm.ok, confirm.text()
    rid = confirm.json()["request_id"]

    # Poll for ready.
    status = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        r = page.request.get(f"{base_url}/api/v14/releases/requests/{rid}")
        assert r.ok
        status = r.json()
        if status["status"] == "ready":
            break
        time.sleep(0.5)
    assert status and status["status"] == "ready"
    project_id = status["project_id"]
    run_id = status["run_id"]

    # AC-FR0400-02/03: Foundation evidence
    fr = page.request.get(f"{base_url}/api/v14/releases/requests/{rid}/foundation")
    assert fr.ok
    foundation = fr.json()
    assert foundation["status"] == "ready"
    rb = foundation["foundation"]["resources"]["release_branch"]
    assert rb["head_symbolic_ref"] == "releases/0.14.0"
    worktree_path = foundation["foundation"]["resources"]["worktree"]["path"]
    sym = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sym == "releases/0.14.0"

    # AC-FR0500-03: Story page
    page.goto(
        f"{base_url}/projects/{project_id}/requirements/story",
        wait_until="domcontentloaded",
    )
    page.locator("#story-page").wait_for()
    page.locator("p[data-run]").wait_for()
    assert "M-STORY" in page.locator("p[data-run]").inner_text()

    # AC-FR0700-01: Scribe Chat binding
    chat = page.locator("#scribe-chat")
    chat.wait_for()
    task_id = chat.get_attribute("data-task-id")
    assert task_id and task_id.startswith("task_")

    # AC-FR0700-02: before reconcile -- no recommendation
    cr = page.request.get(f"{base_url}/api/v14/projects/{project_id}/current")
    assert cr.ok
    current = cr.json()
    assert current["story_gate"]["recommendation"] is None
    assert current["story_gate"]["m_spec_task_count"] == 0

    # AC-FR0700-02: reconcile through public HTTP -> provider result ingestion
    rr = page.request.post(
        f"{base_url}/api/v14/runs/{run_id}/tasks/{task_id}/reconcile",
        headers=h,
    )
    assert rr.ok, rr.text()

    # Verify stand-in dispatched.
    ledger = opencode.read_ledger()
    assert any(e.get("kind") == "send_message" for e in ledger)

    # AC-FR0700-02: after reconcile -- recommendation, waiting_for_human
    cr = page.request.get(f"{base_url}/api/v14/projects/{project_id}/current")
    assert cr.ok
    current = cr.json()
    gate = current["story_gate"]
    assert gate["recommendation"] == "Go"
    assert gate["human_wait"] is True
    assert gate["m_spec_task_count"] == 0
    artifact = current["artifact"]
    story_path = (
        Path(worktree_path)
        / ".louke"
        / "project"
        / "specs"
        / "v0.14-001-workflow-reflow-spec"
        / "story.md"
    )
    expected = f"sha256:{hashlib.sha256(story_path.read_bytes()).hexdigest()}"
    assert artifact["digest"] == expected

    # AC-FR0800-01: click authenticated Human Go decision
    run_revision = current["run"]["revision"]
    # Reload the Story page so the decision gate renders the Go button
    # (it's only visible when human_wait is True after reconcile).
    page.reload(wait_until="domcontentloaded")
    page.locator("#story-page").wait_for()
    decision_section = page.locator("#story-decision-gate")
    decision_section.wait_for()
    go_button = decision_section.locator("[data-decision='Go']")
    go_button.wait_for()
    page.fill("#story-decision-reason", "The Story scope is bounded and ready.")
    go_button.click()
    page.wait_for_function(
        "() => document.getElementById('story-decision-status').textContent.includes('Decision recorded')",
        timeout=10000,
    )

    # Verify persisted actor/revision/digest.
    ar = page.request.get(f"{base_url}/api/v14/projects/{project_id}/current")
    assert ar.ok
    after = ar.json()
    assert after["story_gate"]["decision"]["value"] == "Go"
    assert after["story_gate"]["decision"]["actor"] == "human:human"
    assert after["run"]["revision"] > run_revision
    assert after["run"]["phase"] == "M-STORY"
    assert after["run"]["status"] == "running"
    assert after["artifact"]["digest"] == artifact["digest"]


@pytest.mark.v014_entry_e2e
@pytest.mark.skipif(
    not _chromium_installed(),
    reason="Chromium or Playwright is not installed (AC-NFR0300-01)",
)
def test_v014_entry_slice_foreign_origin_fail_closed(live_server, browser_page):
    """AC-FR0600-03: foreign Origin cannot mutate release state."""
    page, base_url = browser_page

    page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    page.goto(f"{base_url}/projects/new", wait_until="domcontentloaded")
    csrf = _csrf_from_page(page)
    assert csrf

    response = page.request.post(
        f"{base_url}/api/v14/releases/preview",
        data=json.dumps({"story": CANONICAL_HUMAN_STORY, "release_version": "0.14.0"}),
        headers={
            "Content-Type": "application/json",
            "Origin": "https://foreign.example",
            "X-Louke-CSRF": csrf,
        },
    )
    assert response.status == 403
    assert response.json()["error_code"] == "ORIGIN_FORBIDDEN"
