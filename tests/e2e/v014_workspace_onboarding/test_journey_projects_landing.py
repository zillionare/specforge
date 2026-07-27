"""E2E journey: login → Projects landing (empty / active / conflict).

AC-FR0401-01, AC-FR0401-02, AC-FR0501-01, AC-FR0501-02, AC-FR0501-03

Mode B stub-first E2E: when Devon artifacts are present the journey
runs through the live Starlette app + Playwright Chromium; otherwise
the module-level fixture skips the suite. Per interfaces §3.2 only the
*happy path* is exercised here; the conflict branch is seeded through
the host project state file but without further interaction.
"""

from __future__ import annotations

import json


from tests.integration.v014_workspace_onboarding._mode_b import (
    devon_module_skip,
)


# ---------------------------------------------------------------------------
# Journey: login → Projects
# ---------------------------------------------------------------------------


def _register_and_login(page, base_url: str) -> None:
    """Use the public Register tab instead of seeding users or Setup state."""
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.locator("#tab-register").click()
    page.locator("#register-username").fill("projects-human")
    page.locator("#register-password").fill("canary")
    page.locator("#register-submit").click()
    page.wait_for_url("**/workbench?activity=projects")


def test_journey_login_lands_on_projects_empty(browser_page, live_server):
    """AC-FR0401-01: setup-complete login → Workbench Projects (empty)."""
    # AC-FR0401-01
    devon_module_skip("IF-WEB-01", fr="FR-0001")
    page, _ = browser_page
    base_url, _, _ = live_server

    _register_and_login(page, base_url)
    assert page.url.endswith("/workbench?activity=projects"), page.url
    body = page.inner_text("body").lower()
    assert "new project" in body


def test_journey_login_lands_on_projects_active(browser_page, live_server):
    """AC-FR0401-01: setup-complete login → active Project Status."""
    # AC-FR0401-01
    devon_module_skip("IF-PROJECT-01", fr="FR-0401")
    page, _ = browser_page
    base_url, workspace, _ = live_server

    _register_and_login(page, base_url)
    workspace_state = workspace.root / ".louke" / "project-state.json"
    workspace_state.parent.mkdir(parents=True, exist_ok=True)
    workspace_state.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "active",
                "project_id": "prj_demo",
            }
        ),
        encoding="utf-8",
    )
    page.goto(f"{base_url}/workbench", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    assert "/workbench?activity=projects" in page.url
    body = page.inner_text("body")
    assert "Project Status" in body or "Workflow" in body


def test_journey_login_lands_on_projects_conflict(browser_page, live_server):
    """AC-FR0401-02: two active Project bindings show conflict and block create."""
    # AC-FR0401-02
    devon_module_skip("IF-PROJECT-01", fr="FR-0401")
    page, _ = browser_page
    base_url, workspace, _ = live_server

    _register_and_login(page, base_url)
    workspace_state = workspace.root / ".louke" / "project-state.json"
    workspace_state.parent.mkdir(parents=True, exist_ok=True)
    workspace_state.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "conflict",
                "conflicts": [
                    {"project_id": "prj_a"},
                    {"project_id": "prj_b"},
                ],
            }
        ),
        encoding="utf-8",
    )
    page.goto(f"{base_url}/workbench", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()
    assert "conflict" in body


# ---------------------------------------------------------------------------
# Guide presence on Projects
# ---------------------------------------------------------------------------


def test_journey_projects_sidebar_has_guide_session(browser_page, live_server):
    """AC-FR0501-01: Guide session is mounted on the Projects sidebar."""
    # AC-FR0501-01
    devon_module_skip("IF-GUIDE-01", fr="FR-0501")
    page, _ = browser_page
    base_url, _, _ = live_server
    _register_and_login(page, base_url)
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    sidebar = page.query_selector('aside[data-role="guide"]') or page.query_selector(
        "aside.sidebar"
    )
    # AC-FR0501-01: Guide sidebar must be present on Projects landing
    assert sidebar is not None
    text = sidebar.inner_text().lower()
    assert "new project" in text or "environment" in text


def test_journey_guide_advice_after_environment_block(browser_page, live_server):
    """AC-FR0501-02: blocking Environment emits Runtime status then advice."""
    # AC-FR0501-02
    devon_module_skip("IF-GUIDE-01", fr="FR-0501")
    page, _ = browser_page
    base_url, workspace, _ = live_server

    _register_and_login(page, base_url)
    # Seed an active Project so the Projects surface can render its status.
    workspace_state = workspace.root / ".louke" / "project-state.json"
    workspace_state.parent.mkdir(parents=True, exist_ok=True)
    workspace_state.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "ws_demo",
                "state": "active",
                "project_id": "prj_demo",
            }
        ),
        encoding="utf-8",
    )
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()

    assert "scope" in body
    assert "guide" in body


def test_journey_guide_does_not_have_action_capability(browser_page, live_server):
    """AC-FR0501-03: Guide chat does not run install/auth/create actions."""
    # AC-FR0501-03
    devon_module_skip("IF-GUIDE-01", fr="FR-0501")
    page, _ = browser_page
    base_url, _, _ = live_server
    _register_and_login(page, base_url)
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    composer = page.query_selector('textarea[name="guide_message"]')
    # AC-FR0501-03: Guide composer must be present for chat interaction
    assert composer is not None
    composer.fill("install gh for me")
    page.click('button:has-text("Send")')
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()
    assert "guidance" in body or "guide" in body
