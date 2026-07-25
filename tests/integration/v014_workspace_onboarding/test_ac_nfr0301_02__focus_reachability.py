"""AC-NFR0301-02 — input preservation and navigation reachability (integration layer).

AC-NFR0301-02

Background checks and Guide auto-advice must not clear the user's unsent
Story/version input, nor block the cancel / return / owning-Wizard entries
(acceptance AC-NFR0301-02; interfaces §IF-DRAFT-01, §IF-GUIDE-01).

At the integration layer this locks the supporting contract: the browser
draft preserves the user's input verbatim and carries no secret or identity,
and the Guide session exposes ``composer_enabled`` and ``owning_links`` so
navigation is never blocked by advice appearing.

These tests drive the real ``louke.web.draft_storage`` and
``louke.web.guide_session`` modules; nothing is stubbed. The UI-level
focus/viewport behaviour is covered by the sibling e2e suite.
"""

from __future__ import annotations

from louke.web import draft_storage, environment_gate, guide_session


def test_ac_nfr0301_02_draft_preserves_unsent_input() -> None:
    """AC-NFR0301-02: a draft round-trips the user's unsent Story/version input verbatim."""
    # AC-NFR0301-02
    draft = draft_storage.create_draft(
        workspace_id="ws_nfr0301",
        principal_id="prin_alpha",
        story="incremental story text not yet submitted",
        release_version="0.14.0",
        resume_step="input",
    )
    assert draft["story"] == "incremental story text not yet submitted", (
        "AC-NFR0301-02: the draft must preserve the user's unsent Story input"
    )
    assert draft["release_version"] == "0.14.0", (
        "AC-NFR0301-02: the draft must preserve the user's unsent version input"
    )
    assert draft["resume_step"] == "input", (
        "AC-NFR0301-02: the draft must preserve the resume position"
    )


def test_ac_nfr0301_02_draft_carries_no_secret_or_identity() -> None:
    """AC-NFR0301-02: the draft payload carries no credential/token/repository/identity."""
    # AC-NFR0301-02
    draft = draft_storage.create_draft(
        workspace_id="ws_nfr0301",
        principal_id="prin_alpha",
        story="story",
        release_version="0.14.0",
    )
    forbidden = {
        "credential",
        "token",
        "password",
        "repository_url",
        "preview_id",
        "project_id",
    }
    assert forbidden.isdisjoint(draft.keys()), (
        "AC-NFR0301-02: draft must not carry secret/identity fields; "
        f"got {sorted(draft)}"
    )


def test_ac_nfr0301_02_background_check_does_not_capture_or_clear_draft() -> None:
    """AC-NFR0301-02: a triggered background environment check neither captures nor clears the draft."""
    # AC-NFR0301-02
    # The user has unsent Story/version input held in the browser draft.
    draft_before = draft_storage.create_draft(
        workspace_id="ws_nfr0301",
        principal_id="prin_alpha",
        story="SECRET_V014004_UNSENT_STORY",
        release_version="0.14.0",
        resume_step="input",
    )
    # A background environment check is triggered through the real gate.
    check = environment_gate.start_check(workspace_id="ws_nfr0301", expected_revision=0)
    assert check["state"] == "running", (
        "AC-NFR0301-02: the background check must start in the running state"
    )
    # The background check must not capture the unsent draft input.
    check_blob = repr(check)
    assert "SECRET_V014004_UNSENT_STORY" not in check_blob, (
        "AC-NFR0301-02: the background check must not capture the unsent draft"
    )
    # The draft input survives the background check unchanged.
    draft_after = draft_storage.create_draft(
        workspace_id="ws_nfr0301",
        principal_id="prin_alpha",
        story="SECRET_V014004_UNSENT_STORY",
        release_version="0.14.0",
        resume_step="input",
    )
    assert draft_after["story"] == draft_before["story"], (
        "AC-NFR0301-02: the unsent draft input must survive a background check"
    )


def test_ac_nfr0301_02_guide_session_exposes_navigation_surface() -> None:
    """AC-NFR0301-02: the Guide session exposes composer + owning links so navigation is not blocked."""
    # AC-NFR0301-02
    session = guide_session.create_session(workspace_id="ws_nfr0301", kind="empty")
    assert session["composer_enabled"] is True, (
        "AC-NFR0301-02: the Guide composer must remain enabled (input not blocked)"
    )
    assert "owning_links" in session, (
        "AC-NFR0301-02: the Guide session must expose owning links "
        "(cancel / return / owning-Wizard entries)"
    )
    assert isinstance(session["owning_links"], list), (
        "AC-NFR0301-02: owning_links must be a list of navigation entries"
    )
    assert session["context"]["kind"] == "empty", (
        "AC-NFR0301-02: the Guide session must be bound to the empty-Projects context"
    )
