"""Browser e2e for the v0.14-001 public-entry slice (installed wheel).

AC-FR0100-01/02, AC-FR0300-01/02, AC-FR0400-01/02/03, AC-FR0500-01/03,
AC-FR0600-02, AC-FR0700-01/02/03, AC-FR0800-01.

The test drives the installed ``lk serve`` through a real Chromium browser
on a random loopback port. Every action (login, readiness,
canonical Project Preview/Confirm, Foundation, Story page, Scribe task,
reconcile, Human Go decision) goes through the public Web surface.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
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


def _csrf_from_page(page) -> str:
    return page.evaluate(
        """() => {
            const m = document.documentElement.innerHTML.match(/const\\s+csrf\\s*=\\s*["']([a-f0-9]+)["']/);
            if (m) return m[1];
            const el = document.querySelector('[data-csrf]');
            return el ? el.dataset.csrf : '';
        }"""
    )


def _register_and_context(page, base_url: str) -> dict[str, str]:
    """Register the browser Human and return canonical mutation headers."""
    register = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert register.ok, register.text()
    page.goto(
        f"{base_url}/workbench?activity=projects&action=new_project",
        wait_until="domcontentloaded",
    )
    csrf = _csrf_from_page(page)
    assert csrf
    return {
        "Content-Type": "application/json",
        "Origin": base_url,
        "X-Louke-CSRF": csrf,
    }


def _canonical_environment_check(page, base_url: str, headers: dict[str, str]) -> dict:
    """Run the real bounded readiness check before Project creation."""
    response = page.request.post(
        f"{base_url}/api/projects/environment-checks", headers=headers
    )
    assert response.ok, response.text()
    body = response.json()
    assert body["state"] == "passed", body
    assert body["story_input_enabled"] is True
    return body


def _canonical_preview(page, base_url: str, headers: dict[str, str]) -> dict:
    """Create a revision-bound canonical Project Preview."""
    response = page.request.post(
        f"{base_url}/api/projects/preview",
        data=json.dumps(
            {
                "story": CANONICAL_HUMAN_STORY,
                "release_version": "0.15.0",
            }
        ),
        headers={**headers, "Idempotency-Key": "e2e-preview-1"},
    )
    assert response.ok, response.text()
    preview = response.json()
    assert preview["side_effects"] == []
    assert preview["release"]["canonical"] == "0.15.0"
    return preview


def _canonical_create_and_readback(
    page, base_url: str, headers: dict[str, str], preview: dict
) -> tuple[dict, dict]:
    """Confirm once with idempotency, then read nested Project/Run identities."""
    confirm = page.request.post(
        f"{base_url}/api/projects/confirm",
        data=json.dumps(
            {
                "preview_id": preview["preview_id"],
                "expected_preview_revision": preview["preview_revision"],
                "request_digest": preview["request_digest"],
            }
        ),
        headers={**headers, "Idempotency-Key": "e2e-confirm-1"},
    )
    assert confirm.status == 202, confirm.text()
    request_id = confirm.json()["request_id"]
    status = page.request.get(f"{base_url}/api/projects/requests/{request_id}")
    assert status.ok, status.text()
    status_body = status.json()
    assert status_body["status"] == "ready"
    project_id = status_body["project"]["project_id"]
    run_id = status_body["run"]["run_id"]
    assert project_id
    assert run_id

    current = page.request.get(f"{base_url}/api/projects/{project_id}/current")
    assert current.ok, current.text()
    current_body = current.json()
    assert current_body["project"]["project_id"] == project_id
    assert current_body["run"]["run_id"] == run_id
    assert current_body["project"]["spec_id"].startswith("v0.15-")
    return status_body, current_body


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

    # AC-FR0100-01: authenticated Human + terminal readiness.
    headers = _register_and_context(page, base_url)
    _canonical_environment_check(page, base_url, headers)

    # AC-FR0300-01/02 + AC-FR0400-02: canonical Preview/Confirm + Foundation.
    preview = _canonical_preview(page, base_url, headers)
    status, current = _canonical_create_and_readback(page, base_url, headers, preview)
    project_id = status["project"]["project_id"]
    run_id = status["run"]["run_id"]
    foundation = status
    assert foundation["status"] == "ready"
    rb = foundation["foundation"]["resources"]["release_branch"]
    assert rb["head_symbolic_ref"] == "releases/0.15.0"
    worktree_path = foundation["foundation"]["resources"]["worktree"]["path"]
    sym = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sym == "releases/0.15.0"

    # AC-FR0500-03: canonical Story page and nested artifact identity.
    page.goto(
        f"{base_url}/workbench?activity=dev-docs&project={project_id}"
        "&document=story&revision=1",
        wait_until="domcontentloaded",
    )
    page.get_by_test_id("dev-docs-story").wait_for()
    story_view = page.get_by_test_id("dev-docs-story")
    assert CANONICAL_HUMAN_STORY in story_view.inner_text()
    assert "Revision: 1" in story_view.inner_text()
    assert current["artifact"]["kind"] == "story"
    assert current["artifact"]["revision"] == 1
    assert current["artifact"]["digest"].startswith("sha256:")

    # AC-FR0700-01: Scribe Chat binding
    task = current["task"]
    assert task["task_id"].startswith("task_")
    task_id = task["task_id"]

    # AC-FR0700-02: before reconcile -- no recommendation
    assert current["story_gate"]["recommendation"] is None
    assert current["story_gate"]["m_spec_task_count"] == 0

    # AC-FR0700-02: reconcile through public HTTP -> provider result ingestion
    rr = page.request.post(
        f"{base_url}/api/runs/{run_id}/tasks/{task_id}/reconcile",
        headers=headers,
    )
    assert rr.ok, rr.text()

    # Verify stand-in dispatched.
    ledger = opencode.read_ledger()
    assert any(e.get("kind") == "send_message" for e in ledger)

    # AC-FR0700-02: after reconcile -- recommendation, waiting_for_human
    cr = page.request.get(f"{base_url}/api/projects/{project_id}/current")
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
        / current["project"]["spec_id"]
        / "story.md"
    )
    expected = f"sha256:{hashlib.sha256(story_path.read_bytes()).hexdigest()}"
    assert artifact["digest"] == expected

    # AC-FR0800-01: authenticated Human Go decision through canonical action API.
    run_revision = current["run"]["revision"]
    decision = page.request.post(
        f"{base_url}/api/runs/{run_id}/actions",
        data=json.dumps(
            {
                "action": "story_decision",
                "expected_run_revision": run_revision,
                "expected_artifact_revision": current["artifact"]["revision"],
                "idempotency_key": "e2e-go-1",
                "payload": {
                    "candidate": "Go",
                    "reason": "The Story scope is bounded and ready.",
                    "project_id": project_id,
                },
            }
        ),
        headers=headers,
    )
    assert decision.ok, decision.text()
    decision_body = decision.json()

    # Verify persisted actor/revision/digest.
    ar = page.request.get(f"{base_url}/api/projects/{project_id}/current")
    assert ar.ok
    after = ar.json()
    assert after["story_gate"]["decision"]["value"] == "Go"
    assert after["story_gate"]["decision"]["actor"] == "human:human"
    assert after["run"]["revision"] > run_revision
    assert after["run"]["phase"] == "M-STORY"
    assert after["run"]["status"] == "running"
    assert after["artifact"]["digest"] == artifact["digest"]
    assert decision_body["run"]["run_id"] == run_id


@pytest.mark.v014_entry_e2e
@pytest.mark.skipif(
    not _chromium_installed(),
    reason="Chromium or Playwright is not installed (AC-NFR0300-01)",
)
def test_v014_entry_slice_foreign_origin_fail_closed(live_server, browser_page):
    """AC-FR0600-03: foreign Origin cannot mutate release state."""
    page, base_url = browser_page

    headers = _register_and_context(page, base_url)

    response = page.request.post(
        f"{base_url}/api/projects/preview",
        data=json.dumps({"story": CANONICAL_HUMAN_STORY, "release_version": "0.15.0"}),
        headers={
            **headers,
            "Origin": "https://foreign.example",
            "Idempotency-Key": "e2e-foreign-preview-1",
        },
    )
    assert response.status == 403
    assert response.json()["error_code"] == "ORIGIN_FORBIDDEN"
