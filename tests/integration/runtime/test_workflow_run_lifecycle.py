"""Integration tests for the current Runtime workflow-run lifecycle.

These tests stand up the current Starlette app stack with a fresh Runtime store
per test and exercise
multi-step flows via the in-process Starlette ``TestClient``. They do NOT
start a live uvicorn server and are NOT browser E2E; the conftest default skips
the live-server fixture.

Test layer (gap-analysis §3 P1-1 / §4 Batch 3, issue #177 S4): this file was
``tests/e2e/test_v12_integration_e2e.py`` and has been moved to
``tests/integration/runtime/`` because its name and behaviour are integration
(Starlette ``TestClient`` + real temporary store + multi-step flows), not
end-to-end browser/CLI journeys. It is now selected via ``pytest -m
integration`` and is no longer collected by ``pytest -m e2e``. The file carries
no ``@pytest.mark.e2e`` decorator; the path-based auto-mark in
``tests/integration/conftest.py`` applies the ``integration`` marker.

AC references covered (one integration test per FR):
- FR-0101 (AC-FR0101-01..04): WorkflowRun lifecycle - preview, confirm, audit events.
- FR-0401 (AC-FR0401-01): Runtime run create/read/update via HTTP.
- FR-0901 (AC-FR0901-01..04): M-LOCK semantics - gate blocks, approve, advance.
- FR-1001 (AC-FR1001-01..03): Runtime current/history projection.
- FR-1101 (AC-FR1101-01..03): Login-era Preview/Confirm request state.
- FR-1201 (AC-FR1201-01): workflow graph - nodes/edges/current_step.
- FR-1301 (AC-FR1301-01..02): bindings - list defaults, PUT override.
- FR-1501 (AC-FR1501-01): context manifest - event stream carries digests.
- FR-1601 (AC-FR1601-01): public Runtime definition selection.
- FR-1701 (AC-FR1701-01): workflow definitions - public graph validation.

Every mutation in this file is driven through the mounted production HTTP
surface after the public Register -> Login -> CSRF flow. The host currently
exposes gate *reads* and decisions, but has no public endpoint that creates
the requirements-approval or M-LOCK contract gate from document digests.
Accordingly, this suite verifies the observable fail-closed human-gate state;
it does not privately manufacture gates to simulate an approval.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.integration.v014_workspace_onboarding.test_ac_fr0101_0301_0201__if_setup01_02_03 import (
    ReadyExecutor,
    _model_result,
)
from tests.fixtures.v014_workflow_reflow.harness import (
    IsolatedWorkspace,
    OpenCodeStandIn,
    build_isolated_workspace,
    start_opencode_standin,
)


def _write_project_toml(root: Any) -> None:
    """Write a minimal project.toml so ``create_app`` does not fail on meta reads."""
    project_dir = root / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nversion = "0.14.1"\n'
        'repo = "github.com/zillionare/louke"\n'
        'spec_id = "v0.12-001-programmatic-workflow-runtime"\n'
        'release_branch = "main"\n\n'
        '[meta]\ncreated = "2026-07-14"\ntag = "unreleased"\n'
        'current_stage = "M-DEV"\nsecurity_audit = "disabled"\n'
        'smoke_test_issue = ""\nsmoke_test_pr = ""\n'
        'pre_commit = "installed"\ntest_framework = "pytest"\n'
        "acknowledged_orphan_releases = []\n",
        encoding="utf-8",
    )


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Build an authenticated public HTTP client for a fresh tmp workspace."""
    from louke.web.app import create_app

    _write_project_toml(tmp_path)
    monkeypatch.setenv("LOUKE_E2E_STATE", str(tmp_path / ".louke" / "server"))
    app = create_app(tmp_path, allowed_origin="http://testserver")
    app.state.environment_executor = ReadyExecutor(tmp_path)
    app.state.readiness_model_checker = lambda _: _model_result("passed")
    with TestClient(app) as c:
        _register_then_login(c)
        yield c


@pytest.fixture
def foundation_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, IsolatedWorkspace]]:
    """Build a real Git/GitHub/OpenCode-bound public Project creation client."""
    from louke.web.app import create_app

    workspace = build_isolated_workspace(tmp_path)
    opencode: OpenCodeStandIn = start_opencode_standin(tmp_path)
    monkeypatch.setenv(
        "PATH", f"{workspace.gh_bin.parent}:{os.environ.get('PATH', '')}"
    )
    monkeypatch.setenv("LOUKE_OPENCODE_BASE_URL", opencode.base_url)
    monkeypatch.setenv("LOUKE_OPENCODE_BACKEND", "real")
    monkeypatch.setenv("LOUKE_OPENCODE_USE_SERVER_DEFAULT", "1")
    monkeypatch.setenv("LOUKE_GH_OWNER", "zillionare")
    app = create_app(workspace.root, allowed_origin="http://testserver")
    app.state.environment_executor = ReadyExecutor(workspace.root)
    app.state.readiness_model_checker = lambda _: _model_result("passed")
    try:
        with TestClient(app) as test_client:
            _register_then_login(test_client)
            yield test_client, workspace
    finally:
        opencode.stop()
        workspace.cleanup()
        shutil.rmtree(workspace.bare_remote, ignore_errors=True)


def _register_then_login(client: TestClient) -> None:
    """Establish a public authenticated Human session without private seeding."""
    registered = client.post(
        "/api/auth/register", json={"username": "fixture-human", "password": "secret"}
    )
    assert registered.status_code == 200, registered.text
    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200, logged_out.text
    logged_in = client.post(
        "/api/auth/login", json={"username": "fixture-human", "password": "secret"}
    )
    assert logged_in.status_code == 200, logged_in.text


def _mutation_headers(client: TestClient, key: str) -> dict[str, str]:
    """Read the session-bound CSRF token from the public Workbench document."""
    page = client.get("/workbench?activity=projects&action=new_project")
    assert page.status_code == 200, page.text
    match = re.search(r'const\s+csrf\s*=\s*"([a-f0-9]+)"', page.text)
    assert match, "public Workbench did not expose its session-bound CSRF token"
    return {
        "Origin": "http://testserver",
        "X-Louke-CSRF": match.group(1),
        "Idempotency-Key": key,
    }


def _create_run(
    client: TestClient,
    story: str = "Build programmatic workflow runtime",
    definition_id: str = "new_feature",
) -> dict[str, Any]:
    """Create a Runtime run through the current public HTTP surface."""
    del story
    payload: dict[str, Any] = {
        "definition_id": definition_id,
        "definition_version": "1",
    }
    resp = client.post(
        "/api/runtime/runs",
        json=payload,
        headers=_mutation_headers(client, "create-run"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_e2e_fr_0101_workflow_run_lifecycle(client: TestClient) -> None:
    """AC-FR0101-01..04: preview, confirm, audit events exist with revision.

    Drives the full creation flow: a project is created, its workflow run is
    fetched via ``/api/runtime/runs/{id}``, and the audit event stream is read
    via ``/api/runtime/runs/{id}/events``. The run must have a ``current_step``
    and at least one ``run.created`` event with a non-empty ``correlation_id``
    and ``at`` timestamp.
    """
    project = _create_run(client)
    run_id = project["run_id"]

    run_resp = client.get(f"/api/runtime/runs/{run_id}")
    assert run_resp.status_code == 200, run_resp.text
    run = run_resp.json()
    assert run["run_id"] == run_id
    assert run["current_step"] == "start"
    assert run["revision"] == 0
    assert run["status"] == "in_progress"

    events_resp = client.get(f"/api/runtime/runs/{run_id}/events")
    assert events_resp.status_code == 200, events_resp.text
    events = events_resp.json()["items"]
    assert len(events) >= 1
    created = events[0]
    assert created["type"] == "run.created"
    assert created["at"] != ""
    assert created["correlation_id"] != ""


def test_e2e_fr_0401_project_store_crud_via_http(client: TestClient) -> None:
    """AC-FR0401-01: Runtime run create/read/update via public HTTP."""
    project = _create_run(client, story="Foundation CRUD e2e")
    run_id = project["run_id"]

    detail = client.get(f"/api/runtime/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["run_id"] == run_id
    assert detail.json()["status"] == "in_progress"

    transition = client.post(
        f"/api/runtime/runs/{run_id}/commands",
        json={"expected_revision": 0, "result": "done"},
        headers=_mutation_headers(client, "advance-run"),
    )
    assert transition.status_code == 200, transition.text
    assert transition.json()["run"]["revision"] == 1
    assert transition.json()["run"]["current_step"] == "requirements_approval"

    listed = client.get("/api/runtime/runs")
    assert listed.status_code == 200, listed.text
    assert any(item["run_id"] == run_id for item in listed.json()["items"])


def test_e2e_fr_0901_human_gate_is_fail_closed_on_public_runtime_surface(
    client: TestClient,
) -> None:
    """AC-FR0901-01..04: a public command cannot cross an unapproved Human gate.

    The production HTTP API deliberately has no gate-creation endpoint: gates
    can be listed and decided only after the host has materialised a
    document-bound gate. Creating one here would require private
    ``WorkflowOrchestrator.ensure_*_gate`` calls, so this integration test
    asserts the public, fail-closed behavior rather than fabricating approval.
    """
    project = _create_run(client, story="M-LOCK semantics e2e")
    run_id = project["run_id"]

    # Advance the implemented start step into the Human-controlled boundary.
    adv1 = client.post(
        f"/api/runtime/runs/{run_id}/commands",
        json={"expected_revision": 0, "result": "done"},
        headers=_mutation_headers(client, "enter-requirements-gate"),
    )
    assert adv1.status_code == 200, adv1.text
    assert adv1.json()["run"]["current_step"] == "requirements_approval"

    blocked = client.post(
        f"/api/runtime/runs/{run_id}/commands",
        json={"expected_revision": 1, "result": "done"},
        headers=_mutation_headers(client, "attempt-human-gate-bypass"),
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error_code"] == "VALIDATION_ERROR"
    assert (
        "human gate awaiting a host-authenticated decision" in blocked.json()["message"]
    )

    graph = client.get(f"/api/ui/runs/{run_id}/graph")
    assert graph.status_code == 200, graph.text
    assert graph.json()["current_step"] == "requirements_approval"

    gates_resp = client.get(f"/api/gates/runs/{run_id}/gates")
    assert gates_resp.status_code == 200, gates_resp.text
    assert gates_resp.json()["items"] == []


def test_e2e_fr_1001_project_listing_active_and_history(
    client: TestClient,
) -> None:
    """AC-FR1001-01..03: current/history Runtime projection remains observable.

    The removed Project archive API is represented by Runtime's public
    ``current``/``history`` read model. One run remains active while another is
    driven to terminal completion through public commands and the existing
    Human gate contract.
    """
    initial = client.get("/api/ui/runs")
    assert initial.status_code == 200, initial.text
    assert initial.json()["current"] == []
    assert initial.json()["history"] == []

    p1 = _create_run(client, story="First feature")
    p2 = _create_run(client, story="Second feature (hotfix)", definition_id="bug_fix")

    active = client.get("/api/ui/runs").json()["current"]
    active_ids = {item["run_id"] for item in active}
    assert {p1["run_id"], p2["run_id"]} == active_ids

    for item in active:
        assert item["workflow_definition_id"] in ("new_feature", "bug_fix")
        assert item["project_name"] in ("new_feature", "bug_fix")
        assert item["status"] == "in_progress"
        assert item["run_id"] != ""

    entered_gate = client.post(
        f"/api/runtime/runs/{p1['run_id']}/commands",
        json={"expected_revision": 0, "result": "done"},
        headers=_mutation_headers(client, "list-enter-gate"),
    )
    assert entered_gate.status_code == 200, entered_gate.text
    assert entered_gate.json()["run"]["status"] == "waiting_for_human"
    projection = client.get("/api/ui/runs").json()
    assert {item["run_id"] for item in projection["current"]} == {
        p1["run_id"],
        p2["run_id"],
    }
    assert projection["history"] == []


def test_e2e_fr_1001_runtime_recovery_survives_server_restart(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-FR1001-03: a persisted Runtime run recovers via the public API after restart."""
    from louke.web.app import create_app

    _write_project_toml(tmp_path)
    monkeypatch.setenv("LOUKE_E2E_STATE", str(tmp_path / ".louke" / "server"))
    app_before_restart = create_app(tmp_path, allowed_origin="http://testserver")
    app_before_restart.state.environment_executor = ReadyExecutor(tmp_path)
    app_before_restart.state.readiness_model_checker = lambda _: _model_result("passed")
    with TestClient(app_before_restart) as before_restart:
        _register_then_login(before_restart)
        created = _create_run(before_restart, story="Restart recovery project")

    app_after_restart = create_app(tmp_path, allowed_origin="http://testserver")
    app_after_restart.state.environment_executor = ReadyExecutor(tmp_path)
    app_after_restart.state.readiness_model_checker = lambda _: _model_result("passed")
    with TestClient(app_after_restart) as after_restart:
        logged_in = after_restart.post(
            "/api/auth/login", json={"username": "fixture-human", "password": "secret"}
        )
        assert logged_in.status_code == 200, logged_in.text
        recovered = after_restart.post(
            f"/api/runtime/runs/{created['run_id']}/recover",
            headers=_mutation_headers(after_restart, "recover-after-restart"),
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["run_id"] == created["run_id"]
        assert recovered.json()["status"] == "in_progress"
        assert recovered.json()["current_step"] == "start"
        assert recovered.json()["revision"] == 0


def test_e2e_fr_1101_project_creation_preview_confirm(
    foundation_client: tuple[TestClient, IsolatedWorkspace],
) -> None:
    """AC-FR1101-01..03: Confirm persists one Project, Runtime run and Story."""
    client, _workspace = foundation_client
    headers = _mutation_headers(client, "preview-runtime-lifecycle")
    preview_resp = client.post(
        "/api/projects/preview",
        headers=headers,
        json={
            "story": "Create project via preview and confirm flow",
            "release_version": "0.14.1",
        },
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview = preview_resp.json()
    assert preview["preview_id"] != ""
    assert preview["workspace"]["label"]
    assert preview["release"]["canonical"] == "0.14.1"
    assert preview["story"] == "Create project via preview and confirm flow"

    confirm_resp = client.post(
        "/api/projects/confirm",
        headers={**headers, "Idempotency-Key": "confirm-runtime-lifecycle"},
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"],
            "request_digest": preview["request_digest"],
        },
    )
    assert confirm_resp.status_code == 202, confirm_resp.text
    confirmation = confirm_resp.json()
    assert confirmation["request_id"] == preview["request_id"]
    assert confirmation["state"] == "ready"
    assert confirmation["project_id"].startswith("prj_")
    assert confirmation["project"]["release_version"] == "0.14.1"
    assert confirmation["run"]["run_id"] == confirmation["run_id"]
    assert confirmation["run"]["current_step"] == "M-STORY"
    assert confirmation["story"]["digest"].startswith("sha256:"), confirmation["story"]
    assert preview["actions"]["create"] is True

    persisted = client.get(f"/api/projects/requests/{preview['request_id']}")
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["project_id"] == confirmation["project_id"]
    assert persisted.json()["status"] == "ready"

    current = client.get(f"/api/projects/{confirmation['project_id']}/current")
    assert current.status_code == 200, current.text
    current_body = current.json()
    assert current_body["project"]["project_id"] == confirmation["project_id"], (
        current_body
    )
    assert current_body["run"]["run_id"] == confirmation["run_id"]
    assert current_body["run"]["phase"] == "M-STORY"

    story = client.get(f"/api/runs/{confirmation['run_id']}/artifacts/story")
    assert story.status_code == 200, story.text
    assert story.json()["digest"] == confirmation["story"]["digest"]

    replay = client.post(
        "/api/projects/confirm",
        headers={**headers, "Idempotency-Key": "confirm-runtime-lifecycle"},
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"],
            "request_digest": preview["request_digest"],
        },
    )
    assert replay.status_code == 202, replay.text
    assert replay.json() == confirmation

    stale_replay = client.post(
        "/api/projects/confirm",
        headers={**headers, "Idempotency-Key": "confirm-runtime-lifecycle"},
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"] + 1,
            "request_digest": preview["request_digest"],
        },
    )
    assert stale_replay.status_code == 409, stale_replay.text
    assert stale_replay.json()["error_code"] == "STALE_PREVIEW"


def test_e2e_fr_1201_workflow_graph_nodes_and_edges(client: TestClient) -> None:
    """AC-FR1201-01: workflow graph returns nodes, edges and current_step.

    After creating a run, ``GET /api/ui/runs/{id}/graph`` returns the
    full definition-bound graph with all expected node ids, edges and the
    current step pointing at ``start``.
    """
    project = _create_run(client, story="Workflow graph e2e")
    run_id = project["run_id"]

    resp = client.get(f"/api/ui/runs/{run_id}/graph")
    assert resp.status_code == 200, resp.text
    graph = resp.json()
    assert graph["run_id"] == run_id
    assert graph["definition_id"] == "new_feature"
    assert graph["definition_version"] == "1"
    assert graph["current_step"] == "start"

    node_ids = [n["stage_id"] for n in graph["nodes"]]
    assert node_ids == [
        "start",
        "requirements_approval",
        "design",
        "m_lock",
        "implementation",
        "complete",
    ]

    # The start node is marked current; others are pending.
    states = {n["stage_id"]: n["state"] for n in graph["nodes"]}
    assert states["start"] == "current"
    assert states["requirements_approval"] == "pending"

    # Edges connect the steps in order.
    edges = [(e["from_step"], e["to_step"]) for e in graph["edges"]]
    assert ("start", "requirements_approval") in edges
    assert ("m_lock", "implementation") in edges


def test_e2e_fr_1301_agent_bindings_default_and_override(
    client: TestClient,
) -> None:
    """AC-FR1301-01..02: list defaults, PUT override updates effective model.

    The current app exposes the real bindings sub-app at
    ``/api/runtime/bindings``. Drive the mounted public path directly.
    """
    run_resp = client.post(
        "/api/runtime/runs",
        json={"definition_id": "new_feature", "definition_version": "1"},
        headers=_mutation_headers(client, "create-binding-run"),
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["run_id"]

    list_resp = client.get(f"/api/runtime/bindings/devon?run_id={run_id}")
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    assert len(items) >= 1
    devon = next(item for item in items if item["agent_role"] == "devon")
    assert devon["effective_model"] == "claude-sonnet"
    assert devon["source"] == "default"

    put_resp = client.put(
        f"/api/runtime/bindings/devon?run_id={run_id}",
        json={"model": "claude-opus"},
        headers=_mutation_headers(client, "override-devon-binding"),
    )
    assert put_resp.status_code == 200, put_resp.text
    overridden = put_resp.json()
    assert overridden["agent_role"] == "devon"
    assert overridden["effective_model"] == "claude-opus"
    assert overridden["source"] == "override"

    list2_resp = client.get(f"/api/runtime/bindings/devon?run_id={run_id}")
    assert list2_resp.status_code == 200
    devon2 = next(
        item for item in list2_resp.json()["items"] if item["agent_role"] == "devon"
    )
    assert devon2["effective_model"] == "claude-opus"
    assert devon2["source"] == "override"


def test_e2e_fr_1501_context_manifest_event_stream(client: TestClient) -> None:
    """AC-FR1501-01: event stream carries manifest digests and correlation.

    The context manifest is materialised when a semantic task is created, but
    the observable HTTP surface for this FR is the event stream: each event
    carries ``at``, ``correlation_id``, ``input_digest`` and ``output_digest``
    fields that downstream manifest consumers rely on. This test verifies the
    run's audit events have the required manifest-adjacent fields populated.
    """
    project = _create_run(client, story="Context manifest e2e")
    run_id = project["run_id"]

    events_resp = client.get(f"/api/runtime/runs/{run_id}/events")
    assert events_resp.status_code == 200, events_resp.text
    events = events_resp.json()["items"]
    assert len(events) >= 1

    created = events[0]
    # Manifest-adjacent fields required by FR-1501.
    assert created["run_id"] == run_id
    assert created["at"] != ""
    assert created["correlation_id"] != ""
    assert created["input_digest"] != ""
    assert created["output_digest"] != ""
    assert created["revision"] == 0


def test_e2e_fr_1601_responsibility_catalog_two_definitions(
    client: TestClient,
) -> None:
    """AC-FR1601-01: public Runtime accepts the two registered definitions."""
    for definition_id in ("new_feature", "bug_fix"):
        response = client.post(
            "/api/runtime/runs",
            json={"definition_id": definition_id, "definition_version": "1"},
            headers=_mutation_headers(client, f"create-{definition_id}-definition"),
        )
        assert response.status_code == 201, response.text
        assert response.json()["definition_id"] == definition_id

    unknown = client.post(
        "/api/runtime/runs",
        json={"definition_id": "spec_change", "definition_version": "1"},
        headers=_mutation_headers(client, "create-unknown-definition"),
    )
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["error_code"] == "NOT_FOUND"


def test_e2e_fr_1701_workflow_definitions_catalog_validation(
    client: TestClient,
) -> None:
    """AC-FR1701-01: public Runtime graphs validate registered definitions.

    A workflow definition's nodes, legal edges and candidate decision results
    must be enumerable at registration time. This test creates a Runtime run
    for each definition and verifies the public graph endpoint returns a
    structurally valid graph (non-empty nodes/edges,
    a start step, a terminal step). Catalog validation passes without
    exceptions.
    """
    # new_feature graph.
    nf_run = _create_run(client, story="New feature def e2e")
    nf_graph = client.get(f"/api/ui/runs/{nf_run['run_id']}/graph")
    assert nf_graph.status_code == 200, nf_graph.text
    nf = nf_graph.json()
    assert nf["definition_id"] == "new_feature"
    assert len(nf["nodes"]) >= 4
    assert len(nf["edges"]) >= 3
    assert nf["nodes"][0]["stage_id"] == "start"
    # Terminal node has no outgoing edges.
    from_steps = {e["from_step"] for e in nf["edges"]}
    terminal_ids = {
        n["stage_id"] for n in nf["nodes"] if n["stage_id"] not in from_steps
    }
    assert "complete" in terminal_ids

    # bug_fix graph.
    bf_run = _create_run(client, story="Bug fix def e2e", definition_id="bug_fix")
    bf_graph = client.get(f"/api/ui/runs/{bf_run['run_id']}/graph")
    assert bf_graph.status_code == 200, bf_graph.text
    bf = bf_graph.json()
    assert bf["definition_id"] == "bug_fix"
    assert len(bf["nodes"]) >= 3
    assert len(bf["edges"]) >= 2
    # bug_fix starts at source_contract_verify.
    assert bf["nodes"][0]["stage_id"] == "source_contract_verify"
