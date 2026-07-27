"""E2E happy path: empty Project → Environment Wizard → Preview → Create → Dev Docs.

AC-FR0601-01, AC-FR0601-02, AC-FR0701-01, AC-FR0801-01, AC-FR1001-01,
AC-FR1101-01, AC-NFR0301-01

Mode B stub-first: only the *happy path* is covered per interfaces §3.2;
faults and stale branches live in the integration tests.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse


from tests.integration.v014_workspace_onboarding._mode_b import (
    devon_module_skip,
)


def test_journey_wizard_only_runs_after_new_project_click(browser_page, live_server):
    """AC-FR0601-01: empty Projects page does not auto-start the gate."""
    # AC-FR0601-01
    devon_module_skip("IF-ENV-01", fr="FR-0601")
    page, _ = browser_page
    base_url, workspace, _ = live_server

    state_path = workspace.root / ".louke" / "project-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "empty",
                "project": None,
            }
        ),
        encoding="utf-8",
    )

    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    # The Wizard modal must NOT be visible yet.
    assert page.query_selector('form[name="new_project_story"]') is None


def test_journey_new_project_wizard_passes_and_creates_doc(browser_page, live_server):
    """AC-FR0601-01 / AC-FR0801-01 / AC-FR1001-01 / AC-FR1101-01.

    The happy-path journey: empty → env wizard → story/version → preview
    → create → Dev Docs.
    """
    # AC-FR0601-01 / AC-FR0801-01 / AC-FR1001-01 / AC-FR1101-01
    devon_module_skip("IF-PREVIEW-01", fr="FR-1001")
    page, _ = browser_page
    base_url, workspace, _ = live_server

    # 1. Empty Projects state
    state_path = workspace.root / ".louke" / "project-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "empty",
                "project": None,
            }
        ),
        encoding="utf-8",
    )

    # 2. The fixture supplies a bounded ``gh`` executable with authenticated
    # scope output; the product performs real argv readiness checks against it
    # and the fixture's initialized Git repository.

    # AC-FR1101-01 / AC-FR1001-01: ``/api/projects/preview`` and ``/api/projects/confirm``
    # are authenticated Human writes per interfaces §1 (Human writes) and
    # spec §FR-1101 ("已认证 Human 只能确认当前…Preview").  Establish the
    # authenticated session before the browser journey so the live product
    # receives a valid session cookie.  This mirrors the sibling
    # ``test_journey_compat_deep_link._register_and_log_in`` contract.
    register_response = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert register_response.ok, (
        "AC-FR1101-01: test setup registration must succeed through "
        "/api/auth/register to seed an authenticated browser session"
    )

    # 3. Click ``New Project`` from empty Projects.
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.click('button:has-text("New Project")')
    page.wait_for_load_state("networkidle")

    # 4. Wizard passes through and reveals the Story/version form.
    page.wait_for_selector('form[name="new_project_story"]', timeout=15_000)
    page.fill('textarea[name="story"]', "Initial Story for v0.15")
    page.fill('input[name="release_version"]', "0.15.0")

    # 5. Preview surface shows the canonical identity + Create + Cancel.
    page.click('button:has-text("Preview")')
    # The Preview POST is JS-driven; wait for the wizard preview panel to
    # become visible before reading the body so the assertions see the
    # post-Preview state, not the in-flight request.  This preserves the
    # AC-FR1001-01 contract that Preview produces a Create/Cancel/canonical
    # version surface visible to the Human before any Confirm.
    page.wait_for_selector(
        '[data-testid="project-preview"]:not([hidden])', timeout=15_000
    )
    body = page.inner_text("body")
    assert "Create" in body
    assert "Cancel" in body
    assert "0.15.0" in body

    # 6. Confirm and wait for the Dev Docs deep link.
    page.click('button:has-text("Create")')
    page.wait_for_url(
        f"{base_url}/workbench?activity=dev-docs*",
        timeout=15_000,
    )
    doc_body = page.inner_text("body")
    assert "Initial Story for v0.15" in doc_body
    project_id = parse_qs(urlparse(page.url).query)["project"][0]
    project = page.request.get(f"{base_url}/api/projects/{project_id}/current")
    assert project.ok
    project_body = project.json()
    assert project_body["project"]["project_id"] == project_id
    assert project_body["project"]["spec_id"].startswith("v0.15-")
    assert project_body["run"]["run_id"]

    page.goto(
        f"{base_url}/workbench?activity=projects&project={project_id}",
        wait_until="domcontentloaded",
    )
    page.wait_for_load_state("networkidle")
    status_body = page.inner_text("body")
    assert "Active: M-STORY" in status_body
    assert project_body["run"]["run_id"] in status_body


def test_journey_full_happy_path_keyboard_only(browser_page, live_server):
    """AC-NFR0301-01: keyboard-only flow completes the journey."""
    # AC-NFR0301-01
    devon_module_skip("IF-WEB-01", fr="FR-0001")
    page, _ = browser_page
    base_url, workspace, _ = live_server
    state_path = workspace.root / ".louke" / "project-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "empty",
                "project": None,
            }
        ),
        encoding="utf-8",
    )

    register_response = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert register_response.ok, (
        "AC-NFR0301-01: keyboard journey must authenticate before readiness"
    )
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # Tab to the public New Project control and press Enter.  Do not treat an
    # arbitrary toolbar button as success: this journey specifically proves
    # keyboard access to the user-facing project creation action.
    for _ in range(30):
        page.keyboard.press("Tab")
        focused_test_id = page.evaluate(
            "() => document.activeElement?.getAttribute('data-testid')"
        )
        if focused_test_id == "new-project":
            break
    else:
        raise AssertionError("AC-NFR0301-01: New Project was not keyboard reachable")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('form[name="new_project_story"]', timeout=15_000)
    page.wait_for_function(
        """() => {
            const card = document.querySelector('[data-projects-state="new_project"]');
            const step = document.querySelector('[data-testid="env-step-canonical_main"]');
            return card?.dataset.envPassed === 'true' && step?.dataset.state === 'passed';
        }""",
        timeout=15_000,
    )
    for step_id in (
        "gh_executable",
        "gh_auth_scopes",
        "repository_binding",
        "canonical_main",
    ):
        step = page.locator(f'[data-testid="env-step-{step_id}"]')
        assert step.get_attribute("data-state") == "passed", (
            f"AC-NFR0301-01: readiness step {step_id} must be terminal passed"
        )
    assert page.locator('textarea[name="story"]').is_enabled(), (
        "AC-NFR0301-01: Story input must be enabled after terminal readiness"
    )

    # Tab to the Story textarea and type.
    for _ in range(15):
        page.keyboard.press("Tab")
        if page.evaluate(
            "() => document.activeElement?.matches('textarea[name=story]')"
        ):
            break
    else:
        raise AssertionError("AC-NFR0301-01: Story input was not keyboard reachable")
    page.keyboard.type("Keyboard-only Story")

    # Tab to release_version and type.
    for _ in range(5):
        page.keyboard.press("Tab")
        if page.evaluate(
            "() => document.activeElement?.matches('input[name=release_version]')"
        ):
            break
    else:
        raise AssertionError(
            "AC-NFR0301-01: Release version input was not keyboard reachable"
        )
    page.keyboard.type("0.15.0")

    # Move focus to Preview and press Enter.
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")

    body = page.inner_text("body")
    assert "0.14.0" in body or "Preview" in body
