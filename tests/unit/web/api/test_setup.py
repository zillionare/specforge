"""TestClient tests for the /api/setup sub-app (v0.14-004).

AC references covered:
- AC-FR0301-01: GET /status returns the v2 manifest projection.
- AC-FR0201-01: POST /first-user creates the first principal and
  advances the v2 manifest from pending_user to pending_model.
- AC-FR0101-04: missing required body fields return 400 VALIDATION_ERROR.
- AC-NFR0101-01: CSRF token is required for the first-user POST.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from louke.web.api.setup import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Return a TestClient backed by a fresh persisted setup sub-app."""
    project = tmp_path / ".louke" / "project"
    project.mkdir(parents=True)
    (project / "project.toml").write_text("[project]\n", encoding="utf-8")
    return TestClient(create_app(tmp_path))


def _csrf_token(client: TestClient) -> str:
    """Fetch a fresh CSRF token from the v2 status endpoint."""
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "csrf_token" in body
    return body["csrf_token"]


def test_status_returns_v2_manifest_shape(client: TestClient) -> None:
    """AC-FR0301-01: GET /status returns the v2 manifest projection."""
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    # v2 shape per interfaces §IF-SETUP-01.
    assert body["status"] == "pending_user"
    assert body["first_user"] is None
    assert body["model_check"] is None
    assert body["revision"] == 0
    assert "create_first_user" in body["available_actions"]
    assert body["continue_url"] == "/setup"
    assert len(body["csrf_token"]) == 64


def test_status_advances_after_first_user(client: TestClient) -> None:
    """AC-FR0301-01: status reflects the v2 manifest advance after first-user."""
    token = _csrf_token(client)
    resp = client.post(
        "/first-user",
        json={"name": "alice", "credential": "secret-token", "expected_revision": 0},
        headers={"X-Louke-CSRF": token},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["principal_id"].startswith("prin_")
    assert body["status"] == "pending_model"
    assert body["setup_revision"] == 1
    # Manifest is persisted.
    status = client.get("/status").json()
    assert status["status"] == "pending_model"
    assert status["first_user"]["principal_id"].startswith("prin_")


def test_first_user_without_csrf_is_rejected(client: TestClient) -> None:
    """AC-NFR0101-01: a POST without CSRF token returns 403."""
    resp = client.post(
        "/first-user",
        json={"name": "alice", "credential": "secret-token"},
    )
    assert resp.status_code == 403


def test_first_user_with_invalid_csrf_is_rejected(client: TestClient) -> None:
    """AC-NFR0101-01: a POST with wrong CSRF token returns 403."""
    resp = client.post(
        "/first-user",
        json={"name": "alice", "credential": "secret-token"},
        headers={"X-Louke-CSRF": "deadbeef" * 8},
    )
    assert resp.status_code == 403


def test_first_user_persists_to_workspace(client: TestClient, tmp_path: Path) -> None:
    """The first user is present after a fresh setup sub-app is created."""
    token = _csrf_token(client)
    client.post(
        "/first-user",
        json={"name": "alice", "credential": "secret-token"},
        headers={"X-Louke-CSRF": token},
    )
    # Restart the sub-app against the same workspace.
    restarted = TestClient(create_app(tmp_path))
    status = restarted.get("/status").json()
    assert status["status"] == "pending_model"
    assert status["first_user"]["principal_id"].startswith("prin_")


def test_create_first_user_missing_fields(client: TestClient) -> None:
    """AC-FR0101-04: missing required fields return 400 VALIDATION_ERROR."""
    token = _csrf_token(client)
    resp = client.post(
        "/first-user",
        json={"name": "alice"},
        headers={"X-Louke-CSRF": token},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


def test_csrf_token_rotation_on_re_issue(client: TestClient) -> None:
    """AC-NFR0101-01: re-issuing a CSRF token invalidates the old one."""
    # First issuance: get a token and use it successfully.
    token1 = _csrf_token(client)
    resp = client.post(
        "/first-user",
        json={"name": "alice", "credential": "secret-token"},
        headers={"X-Louke-CSRF": token1},
    )
    assert resp.status_code == 201
    # A fresh token issuance rotates the old one out.
    token2_resp = client.get("/status")
    assert token2_resp.status_code == 200
    token2 = token2_resp.json()["csrf_token"]
    assert token1 != token2, "issue_for_session must rotate the stored token"


# ---------------------------------------------------------------------------
# IF-SETUP-03: real OpenCode model check
# ---------------------------------------------------------------------------


def _seed_pending_model(tmp_path: Path) -> None:
    """Persist a ``pending_model`` manifest with an established first user."""
    from louke.web.first_user import principal_id_for
    from louke.web.setup_state import (
        SetupManifest,
        SetupStatus,
        write_manifest,
    )
    from louke.web.store import ProjectStore

    manifest = SetupManifest(
        workspace_id="",
        revision=0,
        status=SetupStatus.PENDING_USER,
    ).advance_to_pending_model(
        first_principal_id=principal_id_for("alice"), expected_revision=0
    )
    write_manifest(tmp_path, manifest)
    ProjectStore(tmp_path).create_user("alice", "secret-token")


def _probe_result(state: str, model_id: str | None = "minimax/m2"):
    """Build a deterministic :class:`ModelCheckResult` for ``run_check``."""
    from louke.web.opencode_probe import ModelCheckResult, ProbeResult

    diagnosis = None
    if state != "passed":
        diagnosis = {
            "reason": "nonzero_exit",
            "object": "opencode model check",
            "known_facts": "opencode run --model minimax/m2 exited with code 1",
            "impact": "Setup cannot verify a working OpenCode model",
            "recovery_url": "/setup",
        }
    return ModelCheckResult(
        check_id="chk_unit",
        revision=1,
        state=state,
        current_model_id=model_id if state == "passed" else None,
        attempted=[ProbeResult(model_id="minimax/m2", state=state, diagnosis=diagnosis)],
        diagnosis=diagnosis,
        observed_at="2026-07-25T00:00:00Z",
    )


def test_model_checks_post_requires_csrf(client: TestClient, tmp_path: Path) -> None:
    """AC-NFR0101-01: a model-check POST without a CSRF token returns 403."""
    _seed_pending_model(tmp_path)
    resp = client.post("/model-checks", json={"expected_revision": 1})
    assert resp.status_code == 403


def test_model_checks_post_requires_first_user(client: TestClient) -> None:
    """IF-SETUP-03: a model check is refused before any first user exists."""
    token = _csrf_token(client)
    resp = client.post(
        "/model-checks",
        json={"expected_revision": 0},
        headers={"X-Louke-CSRF": token},
    )
    assert resp.status_code == 409


def test_model_checks_post_passed_completes_setup(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """AC-FR0301-01: a passed probe completes Setup and points at Projects."""
    from louke.web import opencode_probe
    from louke.web.setup_state import try_read_manifest

    _seed_pending_model(tmp_path)
    monkeypatch.setattr(
        opencode_probe, "run_check", lambda **kwargs: _probe_result("passed")
    )
    token = _csrf_token(client)
    resp = client.post(
        "/model-checks",
        json={"expected_revision": 1},
        headers={"X-Louke-CSRF": token},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["state"] == "passed"
    assert body["continue_url"] == "/workbench?activity=projects"
    assert body["current_model_id"] == "minimax/m2"
    # The manifest is atomically completed.
    assert try_read_manifest(tmp_path).status.value == "complete"


def test_model_checks_post_failed_keeps_pending_model(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """AC-FR0201-02: a failed probe persists a diagnosis and stays pending_model."""
    from louke.web import opencode_probe
    from louke.web.setup_state import try_read_manifest

    _seed_pending_model(tmp_path)
    monkeypatch.setattr(
        opencode_probe, "run_check", lambda **kwargs: _probe_result("failed")
    )
    token = _csrf_token(client)
    resp = client.post(
        "/model-checks",
        json={"expected_revision": 1},
        headers={"X-Louke-CSRF": token},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["state"] == "failed"
    assert body["continue_url"] is None
    assert body["retry_allowed"] is True
    for field_name in ("object", "known_facts", "impact", "recovery_url"):
        assert field_name in body["diagnosis"]
    manifest = try_read_manifest(tmp_path)
    assert manifest.status.value == "pending_model"
    assert manifest.model_check is not None
    assert manifest.model_check.check_id == "chk_unit"


def test_model_checks_get_returns_snapshot(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """IF-SETUP-03: GET /model-checks/{check_id} returns the persisted check."""
    from louke.web import opencode_probe

    _seed_pending_model(tmp_path)
    monkeypatch.setattr(
        opencode_probe, "run_check", lambda **kwargs: _probe_result("failed")
    )
    token = _csrf_token(client)
    client.post(
        "/model-checks",
        json={"expected_revision": 1},
        headers={"X-Louke-CSRF": token},
    )
    resp = client.get("/model-checks/chk_unit")
    assert resp.status_code == 200
    assert resp.json()["check_id"] == "chk_unit"


def test_model_checks_get_unknown_returns_404(
    client: TestClient, tmp_path: Path
) -> None:
    """IF-SETUP-03: an unknown check id returns 404."""
    _seed_pending_model(tmp_path)
    resp = client.get("/model-checks/chk_does_not_exist")
    assert resp.status_code == 404
