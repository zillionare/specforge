"""Wiring test: Setup gate is mounted in ``louke.web.app.create_app``.

AC-FR0001-01, AC-FR0001-02: the running web app must protect
non-allowlist routes when the v2 Setup manifest is incomplete
(303 to ``/setup`` for pages, 428 ``SETUP_REQUIRED`` for APIs)
and must let requests through when the manifest is ``complete``.
"""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from louke.web.setup_state import SetupManifest, SetupStatus, write_manifest


def _workspace(tmp_path: Path, *, status: SetupStatus) -> Path:
    """Build a workspace with a v2 manifest at the given status."""
    (tmp_path / ".louke" / "project").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".louke" / "project" / "project.toml").write_text(
        '[project]\nversion = "0.8"\nspec_id = "demo"\n', encoding="utf-8"
    )
    base = SetupManifest(
        workspace_id="ws_wiring",
        revision=0,
        status=SetupStatus.PENDING_USER,
    )
    if status == SetupStatus.PENDING_USER:
        manifest = base
    elif status == SetupStatus.PENDING_MODEL:
        manifest = base.advance_to_pending_model(
            first_principal_id="prin_wiring", expected_revision=0
        )
    else:
        manifest = base.advance_to_pending_model(
            first_principal_id="prin_wiring", expected_revision=0
        ).complete(
            model_check_state="passed",
            model_check_id="chk_wiring",
            model_check_revision=1,
            model_id="minimax/m2",
            diagnosis=None,
            observed_at="2026-07-24T00:00:00Z",
            expected_revision=1,
        )
    write_manifest(tmp_path, manifest)
    return tmp_path


def test_setup_gate_mounted_in_create_app_blocks_user_routes(tmp_path: Path) -> None:
    """AC-FR0001-01: a non-allowlist page returns 303 to /setup."""
    workspace = _workspace(tmp_path, status=SetupStatus.PENDING_USER)
    client = TestClient(create_app(workspace), raise_server_exceptions=False)
    resp = client.get("/workbench", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"


def test_setup_gate_mounted_in_create_app_blocks_apis(tmp_path: Path) -> None:
    """AC-FR0001-01: a non-allowlist API returns 428 SETUP_REQUIRED."""
    workspace = _workspace(tmp_path, status=SetupStatus.PENDING_USER)
    client = TestClient(create_app(workspace), raise_server_exceptions=False)
    resp = client.get("/api/projects/current")
    assert resp.status_code == 428
    body = resp.json()
    assert body["error"] == "SETUP_REQUIRED"
    assert body["setup_url"] == "/setup"


def test_setup_gate_mounted_in_create_app_allows_setup_routes(tmp_path: Path) -> None:
    """AC-FR0001-01: the allowlist is reachable during incomplete Setup."""
    workspace = _workspace(tmp_path, status=SetupStatus.PENDING_USER)
    client = TestClient(create_app(workspace), raise_server_exceptions=False)
    # /setup is allowlisted: the gate must let it through to the handler
    # (no 303 redirect, no 428). The two-context page is an Archer interface
    # stub (IF-SETUP-01) returning 500 until Devon implements it; AC-FR0001-01
    # here verifies the gate does NOT block /setup, not that the page renders.
    setup_resp = client.get("/setup", follow_redirects=False)
    assert setup_resp.status_code not in (303, 428), (
        "AC-FR0001-01: the gate must allow /setup through; "
        f"got {setup_resp.status_code}"
    )
    assert client.get("/health").status_code == 200
    assert client.get("/api/setup/status").status_code == 200


def test_setup_gate_lifts_after_complete(tmp_path: Path) -> None:
    """AC-FR0001-02: a v2 complete manifest lets every route through."""
    workspace = _workspace(tmp_path, status=SetupStatus.COMPLETE)
    client = TestClient(create_app(workspace), raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    # Non-allowlist API also passes the gate now. (The endpoint
    # itself may not exist; what matters is that the gate does
    # not return 428.)
    resp = client.get("/api/v14/projects/dummy_project/current")
    assert resp.status_code != 428, (
        f"gate should let complete-Setup traffic through; got {resp.status_code} {resp.text}"
    )
