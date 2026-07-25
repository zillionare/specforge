"""Regression tests for the Runtime-backed Workbench Runs read model."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app


def _workspace(root: Path) -> None:
    """Create the minimum project metadata required by the web application."""
    project_dir = root / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nspec_id = "fixture"\n', encoding="utf-8"
    )


def _create_runtime_run(client: TestClient) -> dict[str, object]:
    """Create and return one Runtime-authoritative workflow run."""
    response = client.post(
        "/api/runtime/runs",
        json={"definition_id": "new_feature", "definition_version": "1"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_runtime_run_is_visible_in_ui_projection_and_workbench(
    tmp_path: Path, setup_complete: Path
) -> None:
    """A Runtime-created run is visible without a legacy runs.json file."""
    _workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    run = _create_runtime_run(client)
    projection = client.get("/api/ui/runs")
    workbench = client.get("/workbench?activity=chat")

    assert projection.status_code == 200
    assert run["run_id"] in {item["run_id"] for item in projection.json()["current"]}
    assert workbench.status_code == 200
    assert "/api/runtime/runs" in workbench.text
    assert "runs.json" not in workbench.text


def test_runtime_runs_persist_across_app_rebuild(
    tmp_path: Path, setup_complete: Path
) -> None:
    """Rebuilding the service for one project root retains its Runtime runs."""
    _workspace(tmp_path)
    first_app = create_app(tmp_path)
    first_client = TestClient(first_app)
    run = _create_runtime_run(first_client)
    first_app.state.v12_run_store.close()

    second_client = TestClient(create_app(tmp_path))
    response = second_client.get("/api/runtime/runs")

    assert response.status_code == 200
    assert [item["run_id"] for item in response.json()["items"]] == [run["run_id"]]


def test_runs_read_model_has_an_explicit_empty_state_without_legacy_file(
    tmp_path: Path, setup_complete: Path
) -> None:
    """An empty Runtime store is safe when the legacy read-model file is absent."""
    _workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    assert not (tmp_path / ".louke" / "project" / "runs.json").exists()
    assert client.get("/api/ui/runs").json()["current"] == []
    assert client.get("/api/ui/runs").json()["history"] == []
    assert (
        'data-testid="runs-empty-state"' in client.get("/workbench?activity=chat").text
    )


def test_run_detail_events_gates_and_ui_share_runtime_store(
    tmp_path: Path, setup_complete: Path
) -> None:
    """All Runs read surfaces resolve a run from the same project Runtime store."""
    _workspace(tmp_path)
    client = TestClient(create_app(tmp_path))
    run = _create_runtime_run(client)
    run_id = run["run_id"]

    detail = client.get(f"/api/runtime/runs/{run_id}")
    events = client.get(f"/api/runtime/runs/{run_id}/events")
    gates = client.get(f"/api/gates/runs/{run_id}/gates")
    projection = client.get("/api/ui/runs")

    assert detail.status_code == 200
    assert events.status_code == 200
    assert events.json()["items"][0]["run_id"] == run_id
    assert gates.status_code == 200
    assert projection.status_code == 200
    assert projection.json()["current"][0]["run_id"] == run_id


def test_unknown_runtime_status_is_retained_in_current_group(
    tmp_path: Path, setup_complete: Path
) -> None:
    """Unknown Runtime statuses fail safe without dropping the run from the UI."""
    _workspace(tmp_path)
    app = create_app(tmp_path)
    client = TestClient(app)
    run = _create_runtime_run(client)

    def mark_unknown() -> None:
        store = app.state.v12_run_store
        current = store.get_run(str(run["run_id"]))
        store.update_run(current.with_status("future_status"), current.revision)

    with client:
        client.portal.call(mark_unknown)
        projection = client.get("/api/ui/runs").json()

    assert projection["current"][0]["run_id"] == run["run_id"]
    assert projection["current"][0]["status"] == "future_status"
    assert projection["current"][0]["status_unknown"] is True
