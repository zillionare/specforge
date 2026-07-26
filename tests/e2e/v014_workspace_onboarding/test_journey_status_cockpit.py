"""E2E Runtime-backed Project Status journey for the host entry definition."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from tests.integration.v014_workspace_onboarding._mode_b import devon_module_skip


def _register_and_log_in(page, base_url: str) -> None:
    """Create the supported authenticated browser session for this journey."""
    response = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert response.ok


def test_journey_status_projects_runtime_declared_stages(browser_page, live_server):
    """Project Status projects persisted M-START completion and active M-STORY."""
    devon_module_skip("IF-STATUS-01", fr="FR-1201")
    page, _ = browser_page
    base_url, _workspace, _ = live_server
    _register_and_log_in(page, base_url)

    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.click('button:has-text("New Project")')
    page.wait_for_selector('form[name="new_project_story"]')
    page.fill('textarea[name="story"]', "Runtime-backed status journey")
    page.fill('input[name="release_version"]', "0.15.0")
    page.click('button:has-text("Preview")')
    page.wait_for_selector('[data-testid="project-preview"]:not([hidden])')
    page.click('button:has-text("Create")')
    page.wait_for_url(f"{base_url}/workbench?activity=dev-docs*", timeout=15_000)
    project_id = parse_qs(urlparse(page.url).query)["project"][0]

    page.goto(
        f"{base_url}/workbench?activity=projects&project={project_id}",
        wait_until="domcontentloaded",
    )
    page.wait_for_load_state("networkidle")

    start = page.locator('[data-stage="M-START"]')
    story = page.locator('[data-stage="M-STORY"]')
    assert start.count() == 1
    assert start.get_attribute("data-status") == "completed"
    assert start.get_attribute("data-attempt-id") not in (None, "")
    assert story.count() == 1
    assert story.get_attribute("data-display-state") == "active"
    assert story.get_attribute("data-stage-id") not in (None, "")
