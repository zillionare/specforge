"""Cross-module release, Settings, and unified-runner integration checks."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile

from starlette.testclient import TestClient

from louke.web.app import create_app


ROOT = Path(__file__).parents[3]


def _workspace(tmp_path: Path) -> Path:
    project = tmp_path / ".louke" / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.toml").write_text(
        '[project]\nversion="0.13.1"\nspec_id="fixture"\n[meta]\ncurrent_stage="M-E2E"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_settings_read_model_matches_rendered_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    """I-15 / AC-FR1512-01/02@v0.13.1: API and page share identity."""
    monkeypatch.setenv("LOUKE_RUNTIME_MODE", "global")
    client = TestClient(create_app(_workspace(tmp_path)))
    registered = client.post(
        "/api/auth/register", json={"username": "fixture-human", "password": "secret"}
    )
    assert registered.status_code == 200
    runtime = client.get("/api/ui/settings/runtime")
    assert runtime.status_code == 200
    payload = runtime.json()
    assert payload["display"] == f"{payload['version']} (global)"
    page = client.get("/workbench")
    assert payload["display"] in page.text
    assert "待 v0.15" in page.text


def test_host_adapter_reads_embedded_wheel_metadata(tmp_path: Path) -> None:
    """I-11 / AC-FR1510-03@v0.13.1: inspect reads artifact content."""
    wheel = tmp_path / "opaque-name.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "louke-9.8.7.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: louke\nVersion: 9.8.7\n",
        )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "louke_python_release_adapter.py"),
            "inspect",
            "--artifact",
            str(wheel),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "artifact": str(wheel.resolve()),
        "version": "9.8.7",
    }


def test_canonical_workflow_gates_every_built_artifact() -> None:
    """I-12 / AC-FR1510-03@v0.13.1: publish follows per-artifact gate."""
    workflow = (ROOT / ".github" / "workflows" / "louke-ci.yml").read_text(
        encoding="utf-8"
    )
    assert "for artifact in dist/louke-*.whl dist/louke-*.tar.gz" in workflow
    assert "louke_python_release_adapter.py inspect" in workflow
    assert "release verify --tag" in workflow
    assert workflow.index("Verify every artifact against the git tag") < workflow.index(
        "Publish to PyPI"
    )


def test_unified_runner_declares_isolated_product_contract() -> None:
    """I-13/I-14 / AC-NFR1503-01@v0.13.1: one runner owns both cases."""
    runner = (ROOT / "tests" / "e2e" / "run_e2e.py").read_text(encoding="utf-8")
    project = (ROOT / ".louke" / "project" / "project.toml").read_text(encoding="utf-8")
    assert "LOUKE_E2E_SERVER_PYTHON" in runner
    assert "TemporaryDirectory" in runner
    assert "run-project-venv integration" in project
    assert "run-project-venv e2e --profile all --runtime both" in project
    chromium = (ROOT / "tests" / "e2e" / "test_v013_chromium_journey_e2e.py").read_text(
        encoding="utf-8"
    )
    assert 'os.environ.get("LOUKE_E2E_SERVER_PYTHON"' in chromium
    assert "sys.executable" not in chromium
