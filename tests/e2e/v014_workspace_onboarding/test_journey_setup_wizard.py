"""E2E journey: two-context Setup Wizard (v0.14-004 locked baseline).

AC-FR0101-01, AC-FR0201-01, AC-FR0301-01, AC-FR0301-02

Drives the locked two-context Setup through a real Chromium browser against
an installed ``lk serve`` plus the OpenCode stand-in (per test-plan §2.1
e2e layer and §6.2 controllable external dependency):

  1. ``/setup`` shows the first-user form (``pending_user``).
  2. Creating the first user advances to the model-check context
     (``pending_model``) — never to the retired six-step URLs
     (``/setup/repository/``, ``/setup/dependencies/``, ``/setup/review/``,
     ``/setup/applying/``).
  3. A passed model probe completes Setup and redirects to
     ``/workbench?activity=projects``.

The retired continuous Wizard journey that previously lived here is
withdrawn (Prism review F-001); this file is its two-context replacement.
There is deliberately **no** ``devon_module_skip`` gating: the journey
asserts the locked contract through the real product surface and is RED
until the page migration to the two-context contract lands. Only the
external ``opencode`` executable is substituted (by the stand-in); the
Setup page, gate, projection and stores are the real product.
"""

from __future__ import annotations


#: Retired six-step wizard URLs the two-context journey must never visit.
RETIRED_SETUP_PATHS: tuple[str, ...] = (
    "/setup/repository/",
    "/setup/dependencies/",
    "/setup/review/",
    "/setup/applying/",
)

#: Test-only secret canary (test-plan §2.2); never a real credential.
_CANARY_CREDENTIAL = "SECRET_V014004_CANARY"


def _assert_not_on_retired_path(page) -> None:
    """Assert the browser has not landed on a retired six-step wizard URL."""
    for path in RETIRED_SETUP_PATHS:
        assert path not in page.url, (
            f"AC-FR0101-01: two-context Setup must not navigate to retired {path}; "
            f"landed at {page.url}"
        )


def test_setup_wizard_two_step_completes_to_projects(browser_page, live_server):
    """AC-FR0101-01 / AC-FR0201-01 / AC-FR0301-01: first user + passed probe -> Projects."""
    # AC-FR0101-01 / AC-FR0201-01 / AC-FR0301-01
    page, base_url = browser_page

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # Step 1: the first-user form is the only visible state for pending_user.
    assert page.query_selector('input[name="name"]') is not None, (
        "AC-FR0101-01: /setup must show the first-user name field"
    )
    assert page.query_selector('input[name="credential"]') is not None, (
        "AC-FR0101-01: /setup must show the first-user credential field"
    )
    page.fill('input[name="name"]', "demo_owner")
    page.fill('input[name="credential"]', _CANARY_CREDENTIAL)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")

    # Step 2: the journey advances to the model-check context, never a
    # retired six-step URL.
    _assert_not_on_retired_path(page)
    body = page.inner_text("body").lower()
    assert "model" in body or "opencode" in body, (
        "AC-FR0201-01: after the first user, /setup must show the model-check "
        f"context; body was: {body[:200]!r}"
    )

    # Trigger the model probe if a start/retry control is present; the
    # OpenCode stand-in returns success so the probe passes.
    trigger = page.query_selector('button[name="retry"]') or page.query_selector(
        'button[name="start"]'
    )
    if trigger is not None:
        trigger.click()
        page.wait_for_load_state("networkidle")
    page.wait_for_load_state("networkidle")

    # Step 3: a passed probe completes Setup and navigates to Projects.
    _assert_not_on_retired_path(page)
    assert page.url.endswith("/workbench?activity=projects"), (
        "AC-FR0301-01: Setup must complete to the Projects activity, "
        f"landed at {page.url}"
    )


def test_setup_wizard_first_user_resumes_at_model_context(browser_page, live_server):
    """AC-FR0101-01 / AC-FR0301-02: refresh after first user resumes the model context."""
    # AC-FR0101-01 / AC-FR0301-02
    page, base_url = browser_page

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="name"]', "demo_owner")
    page.fill('input[name="credential"]', _CANARY_CREDENTIAL)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # Restart/refresh: the persisted first user must resume the model-check
    # context, not re-show the first-user creation form or a retired step.
    page.reload(wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    _assert_not_on_retired_path(page)
    body = page.inner_text("body").lower()
    assert "model" in body or "opencode" in body, (
        "AC-FR0301-02: refresh after the first user must resume the model-check "
        f"context; body was: {body[:200]!r}"
    )
    assert page.query_selector('form[action*="first-user"]') is None, (
        "AC-FR0101-01: the first-user creation form must not reappear once a "
        "first user exists"
    )
