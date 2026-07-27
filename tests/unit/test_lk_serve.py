"""B2: lk serve integration with Login/Workbench and RuntimeSelector.

AC references:
- AC-FR1801-01: `lk serve` in a git repo without Louke metadata starts Login
  instead of exiting.
- AC-FR1801-03: the server starts Login even when no principal exists.
- AC-FR2401-02: lk serve selects the nearest workspace root and local runtime.
- AC-FR2401-04: local runtime missing/corrupt fails before state writes; no
  silent fallback to global.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from louke import serve


def _namespace(**kwargs) -> argparse.Namespace:
    defaults = dict(
        host="127.0.0.1",
        port=8000,
        project_root="",
        dry_run=True,
        opencode_backend="mock",
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _write_project_toml(root: Path, *, current_stage: str = "M-DEV") -> None:
    project_dir = root / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        f"""
[project]
version = "0.12"
repo = "github.com/zillionare/louke"
project = "louke-v0.12"
project_id = ""
spec_id = "v0.12-001-programmatic-workflow-runtime"
release_branch = "main"

[meta]
created = "2026-07-14"
tag = "unreleased"
current_stage = "{current_stage}"
security_audit = "disabled"
smoke_test_issue = ""
smoke_test_pr = ""
pre_commit = "installed (python + base)"
test_framework = "pytest"
acknowledged_orphan_releases = []
""",
        encoding="utf-8",
    )


def _write_first_user(root: Path, name: str = "owner") -> None:
    """Persist a first local human principal via the same store the server uses."""
    louke_dir = root / ".louke"
    louke_dir.mkdir(parents=True, exist_ok=True)
    import json

    (louke_dir / "web-users.json").write_text(
        json.dumps({"version": 1, "users": [{"username": name, "password": "x"}]})
        + "\n",
        encoding="utf-8",
    )


def _ready_workspace(tmp_path: Path, *, current_stage: str = "M-DEV") -> None:
    """Create a workspace that serve treats as ready (valid stage + principal)."""
    _write_project_toml(tmp_path, current_stage=current_stage)
    _write_first_user(tmp_path)
    runtime = tmp_path / ".louke" / "runtime"
    runtime.mkdir()
    (runtime / "lk").touch()


# -- AC-FR1801-01: Login when project.toml is missing -------------------------


def test_serve_creates_minimal_project_toml_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-FR1801-01: serve auto-creates a minimal project.toml and exits 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    args = _namespace(dry_run=True)
    rc = serve.run(args)

    toml_path = tmp_path / ".louke" / "project" / "project.toml"
    assert rc == 0
    assert toml_path.exists(), "serve must auto-create a minimal project.toml"

    captured = capsys.readouterr()
    assert "starting Login/Workbench app" in captured.out
    assert str(toml_path) in captured.out


# -- AC-FR1801-03: Login when no first principal ------------------------------


def test_serve_starts_login_when_no_first_principal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-FR1801-03: project.toml present but no principal still starts Login."""
    _write_project_toml(tmp_path, current_stage="M-FOUND")
    runtime = tmp_path / ".louke" / "runtime"
    runtime.mkdir()
    (runtime / "lk").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    app_holder: dict[str, object] = {}

    real_create_app = serve.create_app

    def capture_app(project_root=None):
        app = real_create_app(project_root)
        app_holder["app"] = app
        return app

    monkeypatch.setattr(serve, "create_app", capture_app)

    args = _namespace(dry_run=True)
    rc = serve.run(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "Login/Workbench" not in captured.out
    app = app_holder["app"]
    assert not hasattr(app.state, "setup_only")


# -- AC-FR2401-04: fail-closed on missing local runtime ---------------------


def test_serve_fails_closed_on_missing_local_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-FR2401-04: local runtime missing -> non-zero exit, no global fallback."""
    _ready_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    nonexistent = tmp_path / "elsewhere"
    nonexistent.mkdir()
    _ready_workspace(nonexistent)
    (nonexistent / ".louke" / "runtime" / "lk").unlink()

    args = _namespace(
        project_root=str(nonexistent),
        opencode_backend="real",
        dry_run=True,
    )
    rc = serve.run(args)

    assert rc != 0
    captured = capsys.readouterr()
    assert "global fallback" in captured.err


# -- AC-FR2401-02: dry-run does not call uvicorn ----------------------------


def test_serve_dry_run_does_not_call_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run resolves but never starts uvicorn."""
    _ready_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    called = {"count": 0}

    def boom(*a, **kw):
        called["count"] += 1
        raise AssertionError("uvicorn.run must not be called in --dry-run")

    monkeypatch.setattr("louke.serve.uvicorn_run", boom, raising=False)

    args = _namespace(dry_run=True)
    rc = serve.run(args)

    assert rc == 0
    assert called["count"] == 0


# -- AC-FR2401-02: resolves local runtime identity --------------------------


def test_serve_resolves_local_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ready workspace resolves RuntimeSelector and prints LOCAL identity."""
    _ready_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    args = _namespace(dry_run=True)
    rc = serve.run(args)

    assert rc == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "LOCAL" in combined
    assert "0.12.0" in combined


# -- AC-FR1401-05: recovery scan skipped in mock mode -----------------------


def test_serve_skips_recovery_in_mock_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-FR1401-05: mock backend (default) skips the recovery scan and prints the marker.

    Even when persisted instances exist, the mock backend is a deterministic
    stub and must not attempt recovery. Only the explicit ``mock`` marker is
    printed so a human cannot be fooled into thinking recovery ran.
    """
    _ready_workspace(tmp_path)
    # Persisted instances file present; mock mode must still skip recovery.
    opencode_dir = tmp_path / ".louke" / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    (opencode_dir / "instances.json").write_text(
        '{"fake":{"instance_id":"fake","status":"running","pid":99999,'
        '"workspace_path":"x","base_url":"http://x","last_seen":1.0}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOUKE_OPENCODE_BACKEND", raising=False)
    monkeypatch.delenv("LOUKE_OPENCODE_BASE_URL", raising=False)
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    args = _namespace(opencode_backend="mock", dry_run=True)
    rc = serve.run(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "skipping recovery scan" in captured.out
    # Mock mode must never emit a recovery summary line.
    assert "opencode recovery:" not in captured.out


# -- AC-FR1401-05: no persisted instances -> no recovery output --------------


def test_serve_recovery_skipped_when_no_instances_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-FR1401-05: real backend with no persisted instances reports nothing to recover.

    When ``instances.json`` is absent, there are no resources to re-associate.
    The real backend prints an explicit "no persisted instances" marker instead
    of fabricating recovery output. ``LOUKE_OPENCODE_BASE_URL`` is preset so no
    managed subprocess is started (the unit test environment has no real
    opencode lifecycle to own).
    """
    _ready_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOUKE_OPENCODE_BACKEND", "real")
    monkeypatch.setenv("LOUKE_OPENCODE_BASE_URL", "http://127.0.0.1:41234")
    monkeypatch.setattr("louke.serve.uvicorn_run", lambda *a, **kw: None, raising=False)

    args = _namespace(opencode_backend="real", dry_run=True)
    rc = serve.run(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "no persisted instances" in captured.out
    # No instances file means no recovery summary line at all.
    assert "opencode recovery:" not in captured.out
