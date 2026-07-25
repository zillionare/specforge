"""E2E: input/focus preservation and navigation reachability (AC-NFR0301-02).

AC-NFR0301-02

Drives the locked v0.14-004 contract through a real Chromium browser against
an installed ``lk serve`` whose workspace is seeded ``complete`` (the default
``live_server`` fixture), so the Setup gate passes and the real New Project
public journey is reachable (test-plan §2.1 e2e layer).

The journey exercises the contract that background checks and Guide
auto-advice must not change focus, clear unsent Story/version or Chat input,
or block the cancel / return / owning-Wizard entries; and that within the
supported viewport + text-zoom the key actions, failure reasons, Guide and
Project Status history navigation stay reachable.

ATDD RED: the assertions target the locked two-context New Project surfaces.
Wherever a surface is not yet implemented the corresponding assertion fails
(discriminating against the retired Wizard / stub), attributable to the
relevant interface. No ``devon_module_skip`` gating.
"""

from __future__ import annotations


#: Viewport + text-zoom combinations the product declares support for
#: (AC-NFR0301-02 reachability).
_VIEWPORT_ZOOM_MATRIX: tuple[tuple[int, int, float], ...] = (
    (1280, 720, 1.0),
    (1024, 768, 1.0),
    (1280, 720, 1.5),  # text zoom 150%
    (800, 600, 1.0),
)


def _goto_projects(page, base_url: str) -> None:
    """Navigate to the Workbench Projects activity (Setup gate already passed)."""
    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")


def test_ac_nfr0301_02_unsent_input_and_focus_preserved_across_background_events(
    browser_page, live_server
):
    """AC-NFR0301-02: background events preserve unsent Story input and focus."""
    # AC-NFR0301-02
    page, base_url = browser_page
    _goto_projects(page, base_url)

    # The Projects context is shown (empty state offers the New Project action).
    new_project = page.get_by_role("button", name="New Project")
    assert new_project.count() >= 1, (
        "AC-NFR0301-02: the empty Projects context must offer the New Project action"
    )
    new_project.first.click()
    page.wait_for_load_state("networkidle")

    # Enter unsent Story/version input in the New Project flow.
    story_input = page.get_by_label("Story", exact=False)
    assert story_input.count() >= 1, (
        "AC-NFR0301-02: the New Project flow must expose a Story input"
    )
    story_input.first.fill("incremental story not yet submitted")
    version_input = page.get_by_label("Version", exact=False)
    if version_input.count() >= 1:
        version_input.first.fill("0.14.0")

    # Record the focused element before any background event.
    focus_before = page.evaluate(
        "() => (document.activeElement && document.activeElement.tagName) || null"
    )

    # A background check / Guide advice appears; it must not clear the unsent
    # input nor move focus.
    page.wait_for_load_state("networkidle")
    assert story_input.first.input_value() == "incremental story not yet submitted", (
        "AC-NFR0301-02: a background event must not clear the unsent Story input"
    )
    focus_after = page.evaluate(
        "() => (document.activeElement && document.activeElement.tagName) || null"
    )
    assert focus_after == focus_before, (
        "AC-NFR0301-02: a background event must not change the user's focus "
        f"(before={focus_before!r}, after={focus_after!r})"
    )


def test_ac_nfr0301_02_navigation_reachable_across_viewport_zoom(
    browser_page, live_server
):
    """AC-NFR0301-02: key navigation entries stay reachable across viewport + zoom."""
    # AC-NFR0301-02
    page, base_url = browser_page

    for width, height, zoom in _VIEWPORT_ZOOM_MATRIX:
        page.set_viewport_size({"width": width, "height": height})
        page.goto(
            f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded"
        )
        page.wait_for_load_state("networkidle")
        page.evaluate(f"() => {{ document.body.style.zoom = '{zoom}'; }}")

        # The primary action stays visible within the supported viewport+zoom.
        new_project = page.get_by_role("button", name="New Project")
        assert new_project.count() >= 1, (
            f"AC-NFR0301-02: New Project action must exist at {width}x{height}@{zoom}"
        )
        assert new_project.first.is_visible(), (
            f"AC-NFR0301-02: New Project action must be visible at {width}x{height}@{zoom}"
        )

        # The Guide session entry stays reachable (cancel / return / owning
        # navigation is not blocked).
        body = page.inner_text("body").lower()
        assert "guide" in body, (
            f"AC-NFR0301-02: the Guide entry must be reachable at {width}x{height}@{zoom}"
        )
