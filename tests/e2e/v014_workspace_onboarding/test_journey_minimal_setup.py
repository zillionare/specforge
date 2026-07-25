"""E2E journey: minimal first-user Setup, gated workbench, real OpenCode probe.

AC-FR0001-01, AC-FR0001-02, AC-FR0101-01, AC-FR0201-01, AC-FR0201-02, AC-FR0301-01, AC-FR0301-02

Per interfaces §3.2 *E2E scope*, only the user-facing happy path is
covered. The journey exercises the real Starlette app plus a Playwright
stand-in for OpenCode so the ``opencode run --model`` line can be
observed without the real provider.

Mode B: every test calls ``devon_module_skip`` for the v0.14-004
interface id; if Devon has not yet shipped the artifact the suite is
dormant. The helper is imported from the integration suite's
``_mode_b`` module so the prior spec-003 ``_module_available`` /
``DEVON_MODULES`` convention is reused.
"""

from __future__ import annotations

from tests.integration.v014_workspace_onboarding._mode_b import (
    devon_module_skip,
)


# ---------------------------------------------------------------------------
# Journey: minimal first-user Setup
# ---------------------------------------------------------------------------


def test_journey_minimal_setup_redirects_user_facing_routes(browser_page, live_server):
    """AC-FR0001-01 / AC-FR0301-01: blank workspace redirects to ``/setup``."""
    # AC-FR0001-01 / AC-FR0301-01
    page, _ = browser_page
    base_url = live_server[0]
    page.goto(f"{base_url}/workbench", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    assert page.url.endswith("/setup"), page.url


def test_journey_minimal_setup_completes_with_real_probe(browser_page, live_server):
    """AC-FR0301-01: setup closes after first user + a real ``opencode run`` exit 0.

    This test exercises Mode A activation: it requires Devon artifacts.
    When the artifacts are absent ``devon_module_skip`` fires before
    the test body runs; otherwise the test drives a real Chromium
    browser through ``/setup``.
    """
    # AC-FR0301-01
    devon_module_skip("IF-SETUP-01", fr="FR-0101")

    page, _ = browser_page
    base_url = live_server[0]

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    name_input = page.query_selector('input[name="name"]')
    cred_input = page.query_selector('input[name="credential"]')
    # AC-FR0301-01: first-user form fields must be present
    assert name_input is not None
    assert cred_input is not None

    page.fill('input[name="name"]', "demo_owner")
    page.fill('input[name="credential"]', "canary_demo_credential")
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")

    body = page.inner_text("body").lower()
    assert "model" in body or "opencode" in body

    retry_button = page.query_selector('button[name="retry"]')
    if retry_button is not None:
        retry_button.click()
        page.wait_for_load_state("networkidle")

    page.wait_for_load_state("networkidle")
    assert page.url.endswith("/workbench?activity=projects"), page.url


def test_journey_minimal_setup_recovery_after_restart(browser_page, live_server):
    """AC-FR0301-02: refreshing ``/setup`` after first user resumes the model step."""
    # AC-FR0301-02
    devon_module_skip("IF-SETUP-01", fr="FR-0101")

    page, _ = browser_page
    base_url = live_server[0]

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.fill('input[name="name"]', "demo_owner")
    page.fill('input[name="credential"]', "canary")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()
    assert "model" in body or "opencode" in body
    assert page.query_selector('form[action*="first-user"]') is None
