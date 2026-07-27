"""Black-box contract checks for the Batch E Runs presentation."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from tests.test_web_server import authenticate


def _client(tmp_path: Path) -> TestClient:
    project = tmp_path / ".louke" / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.toml").write_text(
        "[project]\nspec_id='fixture'\n", encoding="utf-8"
    )
    client = TestClient(create_app(tmp_path))
    authenticate(client)
    return client


def _create_run(client: TestClient) -> dict[str, object]:
    """Create a Runtime run for the Workbench read-model checks."""
    response = client.post(
        "/api/runtime/runs",
        json={"definition_id": "new_feature", "definition_version": "1"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_runs_sidebar_lists_projects(tmp_path: Path, setup_complete: Path) -> None:
    """AC-FR1313-01: Runtime-created projects appear in the Runs projection."""
    client = _client(tmp_path)
    run = _create_run(client)
    response = client.get("/workbench?activity=chat")
    assert response.status_code == 200
    assert 'data-testid="runs-sidebar"' in response.text
    projection = client.get("/api/ui/runs").json()
    assert projection["current"][0]["run_id"] == run["run_id"]
    assert "/api/runtime/runs" in response.text


def test_runs_workflow_graph_renders(tmp_path: Path, setup_complete: Path) -> None:
    """AC-FR1313-02/04: graph nodes are derived from the bound Runtime definition."""
    client = _client(tmp_path)
    run = _create_run(client)
    graph = client.get(f"/api/ui/runs/{run['run_id']}/graph")
    assert graph.status_code == 200
    payload = graph.json()
    assert [node["stage_id"] for node in payload["nodes"]] == [
        "start",
        "requirements_approval",
        "design",
        "m_lock",
        "implementation",
        "complete",
    ]
    html = client.get("/workbench?activity=chat").text
    assert 'data-testid="runs-graph"' in html
    assert "/api/ui/runs/" in html


def test_stage_node_click_opens_artifact_detail(
    tmp_path: Path, setup_complete: Path
) -> None:
    """AC-FR1315-01/02/03: Runtime stage detail is read-only and explicit."""
    client = _client(tmp_path)
    run = _create_run(client)
    artifact = client.get(f"/api/ui/runs/{run['run_id']}/stages/start/artifact")
    assert artifact.status_code == 200
    body = artifact.json()
    assert body["run_id"] == run["run_id"]
    assert body["stage_id"] == "start"
    assert body["unknown"] is False
    assert body["result_kind"] == "run.created"
    assert "Save" not in client.get("/workbench?activity=chat").text


def test_stage_unknown_kind_fallback(tmp_path: Path, setup_complete: Path) -> None:
    """AC-FR1316-01/03/04: unknown Runtime statuses are explicit fallbacks."""
    client = _client(tmp_path)
    run = _create_run(client)
    app = client.app

    def mark_unknown() -> None:
        store = app.state.v12_run_store
        current = store.get_run(run["run_id"])
        store.update_run(current.with_status("future_status"), current.revision)

    with client:
        client.portal.call(mark_unknown)
        item = client.get("/api/ui/runs").json()["current"][0]
    assert item["status"] == "future_status"
    assert item["status_unknown"] is True


def test_badge_mapping_correct() -> None:
    """AC-FR1314-02/03: stage-result values map to approved labels."""
    from louke.web.runs.badges import badges_for_result

    assert (
        badges_for_result({"kind": "review", "verdict": "PASS"})[0]["display_label"]
        == "approved"
    )
    assert (
        badges_for_result({"kind": "gate", "verdict": "fail"})[0]["display_label"]
        == "blocked"
    )
    assert (
        badges_for_result({"kind": "author", "outcome": "running"})[0]["display_label"]
        == "running"
    )
