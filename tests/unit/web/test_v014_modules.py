"""Unit contracts for v0.14-004 workspace onboarding modules.

Covers the minimal public surface of each new module:
projects_context, guide_session, environment_gate, draft_storage,
document_surface, compatibility_router, csrf_middleware,
projection, return_application, foundation_scribe, project_identity,
attempt_detail, setup_projection, first_user, opencode_probe.
"""

from __future__ import annotations

from pathlib import Path


from louke.web.projects_context import (
    STATE_ACTIVE,
    STATE_CONFLICT,
    STATE_EMPTY,
    resolve as resolve_projects,
)
from louke.web.guide_session import (
    AUTHORITY_GUIDE,
    AUTHORITY_HUMAN,
    AUTHORITY_RUNTIME,
    create_session,
)
from louke.web.environment_service import CANONICAL_STEPS
from louke.web.github_readiness import REQUIRED_SCOPES
from louke.web.draft_storage import create_draft, draft_key
from louke.web.document_surface import story_artifact
from louke.web.compatibility_router import (
    ENTRY_CANONICAL_PROJECTS,
    resolve as resolve_compat,
)
from louke.web.csrf_middleware import issue_for_session
from louke.web.setup_projection import (
    SCHEMA_VERSION,
    STATUS_COMPLETE,
    STATUS_PENDING_MODEL,
    STATUS_PENDING_USER,
    read as read_projection,
)
from louke.web.first_user import (
    principal_id_for,
)
from louke.web.opencode_probe import PROBE_PROMPT, is_available, run_minimal
from louke.runtime.projection import CANONICAL_STAGES, project_status
from louke.runtime.return_application import cancel, confirm, preview
from louke.runtime.foundation_scribe import dispatch_scribe, reconcile
from louke.runtime.project_identity import build_identity
from louke.runtime.attempt_detail import attempt_detail


class TestProjectsContext:
    """IF-PROJECT-01: three-state Projects context."""

    def test_empty_when_no_bindings(self) -> None:
        result = resolve_projects(workspace_id="ws_1", bindings=[])
        assert result["state"] == STATE_EMPTY
        assert result["primary_action"]["enabled"] is True

    def test_active_when_single_binding(self) -> None:
        result = resolve_projects(
            workspace_id="ws_1", bindings=[{"project_id": "prj_1"}]
        )
        assert result["state"] == STATE_ACTIVE
        assert result["project"]["project_id"] == "prj_1"

    def test_conflict_when_multiple_bindings(self) -> None:
        result = resolve_projects(
            workspace_id="ws_1",
            bindings=[{"project_id": "prj_1"}, {"project_id": "prj_2"}],
        )
        assert result["state"] == STATE_CONFLICT
        assert result["primary_action"]["enabled"] is False


class TestGuideSession:
    """IF-GUIDE-01: authority values and session creation."""

    def test_authority_values(self) -> None:
        assert AUTHORITY_RUNTIME == "runtime"
        assert AUTHORITY_GUIDE == "guide"
        assert AUTHORITY_HUMAN == "human"

    def test_create_session(self) -> None:
        session = create_session(workspace_id="ws_1", kind="empty")
        assert session["context"]["kind"] == "empty"
        assert session["composer_enabled"] is True


class TestEnvironmentGate:
    """IF-ENV-01: terminal readiness requirements."""

    def test_required_scopes(self) -> None:
        assert set(REQUIRED_SCOPES) == {"gist", "project", "repo", "workflow"}

    def test_terminal_check_has_four_ordered_steps(self) -> None:
        assert CANONICAL_STEPS == (
            "gh_executable",
            "gh_auth_scopes",
            "repository_binding",
            "canonical_main",
        )


class TestDraftStorage:
    """IF-DRAFT-01: draft key and creation."""

    def test_draft_key_binds_workspace_and_principal(self) -> None:
        key = draft_key(workspace_id="ws_1", principal_id="prin_alpha")
        assert key == "louke.new-project.v1:ws_1:prin_alpha"

    def test_create_draft_excludes_credentials(self) -> None:
        draft = create_draft(
            workspace_id="ws_1", principal_id="prin_alpha", story="test"
        )
        assert "credential" not in draft
        assert draft["story"] == "test"


class TestDocumentSurface:
    """IF-DOC-01: story artifact access."""

    def test_returns_none_when_no_story(self, tmp_path: Path) -> None:
        # AC-FR1401-01
        result = story_artifact(workspace_root=tmp_path, spec_id="spec_1")
        assert result is None

    def test_returns_content_when_story_exists(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / ".louke" / "project" / "specs" / "spec_1"
        spec_dir.mkdir(parents=True)
        (spec_dir / "story.md").write_text("# Story", encoding="utf-8")
        result = story_artifact(workspace_root=tmp_path, spec_id="spec_1")
        # AC-FR1401-01: story artifact must exist when file is present
        assert result is not None
        assert "# Story" in result["content"]
        assert result["return_url"] == "/workbench?activity=projects"


class TestCompatibilityRouter:
    """IF-COMPAT-01: legacy deep link resolution."""

    def test_entry_canonical_projects(self) -> None:
        assert ENTRY_CANONICAL_PROJECTS == "/workbench?activity=projects"

    def test_resolves_legacy_projects(self) -> None:
        assert resolve_compat("/projects") == ENTRY_CANONICAL_PROJECTS
        assert resolve_compat("/projects/prj_1") == ENTRY_CANONICAL_PROJECTS

    def test_resolves_legacy_runs(self) -> None:
        assert resolve_compat("/runs/run_1") == ENTRY_CANONICAL_PROJECTS

    def test_returns_none_for_unknown(self) -> None:
        assert resolve_compat("/unknown") is None


class TestCsrfMiddleware:
    """IF-CSRF: session-bound token issuance."""

    def test_issue_for_session_returns_hex(self) -> None:
        token = issue_for_session(session_id="sess_1", revision=0)
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_different_sessions_get_different_tokens(self) -> None:
        t1 = issue_for_session(session_id="sess_1")
        t2 = issue_for_session(session_id="sess_2")
        assert t1 != t2


class TestSetupProjection:
    """IF-SETUP-01: manifest projection."""

    def test_schema_version_is_two(self) -> None:
        assert SCHEMA_VERSION == 2

    def test_status_constants(self) -> None:
        assert STATUS_PENDING_USER == "pending_user"
        assert STATUS_PENDING_MODEL == "pending_model"
        assert STATUS_COMPLETE == "complete"

    def test_read_returns_pending_user_for_missing_manifest(
        self, tmp_path: Path
    ) -> None:
        result = read_projection(tmp_path, workspace_id="ws_1")
        assert result["status"] == "pending_user"
        assert "create_first_user" in result["available_actions"]


class TestFirstUser:
    """IF-SETUP-02: first-user creation."""

    def test_principal_id_is_stable(self) -> None:
        assert principal_id_for("alice") == principal_id_for("alice")

    def test_principal_id_differs_for_different_names(self) -> None:
        assert principal_id_for("alice") != principal_id_for("bob")


class TestOpencodeProbe:
    """IF-SETUP-03: minimal model probe."""

    def test_probe_prompt(self) -> None:
        assert PROBE_PROMPT == "please echo hi"

    def test_is_available_returns_bool(self) -> None:
        assert isinstance(is_available(), bool)

    def test_run_minimal_returns_probe_result(self) -> None:
        result = run_minimal(model_id="test/model", executable="nonexistent_opencode")
        assert result.state == "failed"
        assert result.diagnosis is not None


class TestRuntimeProjection:
    """IF-STATUS-01: canonical stages."""

    def test_canonical_stages_count(self) -> None:
        # AC-FR1201-01
        assert len(CANONICAL_STAGES) == 13

    def test_project_status_returns_projection(self) -> None:
        result = project_status(workspace_id="ws_1", project_id="prj_1")
        assert result["state"] == "active"
        assert result["active"]["stage"] in CANONICAL_STAGES


class TestReturnApplication:
    """IF-RETURN-01: preview, confirm, cancel."""

    def test_preview_returns_unconfirmed(self) -> None:
        result = preview(project_id="prj_1", attempt_id="att_1", target_stage="M-IMPL")
        assert result["confirmed"] is False

    def test_confirm_returns_executed(self) -> None:
        result = confirm(project_id="prj_1", attempt_id="att_1", expected_revision=0)
        assert result["executed"] is True

    def test_cancel_returns_cancelled(self) -> None:
        result = cancel(project_id="prj_1", attempt_id="att_1")
        assert result["cancelled"] is True


class TestFoundationScribe:
    """IF-CREATE-01: reconcile and dispatch."""

    def test_reconcile_returns_status(self) -> None:
        result = reconcile(project_id="prj_1")
        assert result["state"] == "reconciled"

    def test_dispatch_scribe_returns_revision(self) -> None:
        result = dispatch_scribe(project_id="prj_1", spec_id="spec_1")
        assert result["story_revision"] == "latest"


class TestProjectIdentity:
    """IF-IDENTITY-01: canonical chain."""

    def test_build_identity_returns_chain(self) -> None:
        result = build_identity(
            project_id="prj_1",
            release_version="0.14",
            spec_id="spec_1",
        )
        assert result["project_id"] == "prj_1"
        assert result["planned_release"]["canonical"] == "0.14.0"
        assert result["spec_id"] == "spec_1"
        assert result["activity_state"] in {
            "active",
            "historical",
            "migration_required",
        }


class TestAttemptDetail:
    """IF-ATTEMPT-01: attempt detail."""

    def test_attempt_detail_returns_projection(self) -> None:
        result = attempt_detail(
            project_id="prj_1",
            attempt_id="att_1",
            stage="M-IMPL",
            owner="agent_devon",
        )
        assert result["stage"] == "M-IMPL"
        assert result["owner"] == "agent_devon"
        assert result["evidence"] == []
        assert result["actions"] == []
