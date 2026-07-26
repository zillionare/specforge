"""Live HTTP contracts for v0.14 same-origin mutation enforcement."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from louke.opencode.adapter import Instance, Message
from louke.runtime.story_init import (
    StoryInitResult,
    StoryNavigation,
    StoryRevisionEvidence,
)
from louke.runtime.scribe_entry import ScribeEntryService
from louke.runtime.story_entry import StoryArtifactStore
from louke.web.app import create_app
from louke.web.environment_commands import CommandResult

from tests.test_web_server import build_project


def _client(tmp_path: Path) -> TestClient:
    """Build an authenticated live HTTP client with a configured origin."""
    app = create_app(build_project(tmp_path), allowed_origin="https://louke.example")
    app.state.environment_executor = _PassingEnvironmentExecutor(tmp_path)
    client = TestClient(app)
    assert (
        client.post(
            "/api/auth/register", json={"username": "human", "password": "secret"}
        ).status_code
        == 200
    )
    return client


def _csrf(client: TestClient) -> str:
    """Return a fresh CSRF token bound to the client's session cookie.

    The token is issued via the in-memory CSRF store used by the
    v0.14-004 gate, so the verify_token call on the API side
    accepts it.
    """
    from louke.web.csrf_middleware import issue_for_session

    cookie = client.cookies.get("louke_session", "")
    session = cookie.strip('"') if cookie else "preauth"
    return issue_for_session(session_id=session, revision=0)


def _release_request_count(client: TestClient) -> int:
    """Return the number of persisted Project creation requests."""
    connection = client.app.state.release_entry._requests._conn
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM release_requests"
    ).fetchone()
    return int(row["count"])


def _preview(client: TestClient) -> dict[str, object]:
    """Create a valid release preview through the authenticated HTTP surface."""
    response = client.post(
        "/api/projects/preview",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json={"story": "Ship the reflow", "release_version": "0.14.0"},
    )
    assert response.status_code == 200
    return response.json()


class _GateOpenCode:
    """Deterministic OpenCode stand-in for authenticated gate HTTP tests."""

    def create(self, *, correlation_id: str) -> Instance:
        """Return one stable Scribe session identity."""
        return Instance(id="gate-session", status="running")

    def send_message(
        self, instance_id: str, content: str, *, correlation_id: str
    ) -> tuple[Message, bool]:
        """Return one persisted provider message without external effects."""
        return (
            Message(
                id="gate-provider-message",
                instance_id=instance_id,
                role="user",
                kind="message",
                content=content,
            ),
            True,
        )

    def list_messages(self, instance_id: str, *, after_message_id: str | None):
        """Return no additional provider messages during reconciliation."""
        return []


class _PassingEnvironmentExecutor:
    """Return a valid bounded local Environment transcript for HTTP tests."""

    def __init__(self, root: Path) -> None:
        sha = "a" * 40
        self.responses = {
            ("gh", "--version"): CommandResult(0, "gh version 2.50.0\n"),
            ("gh", "auth", "status"): CommandResult(
                0,
                "Logged in to github.com account human\n"
                "Token scopes: 'gist', 'project', 'repo', 'workflow'\n",
            ),
            ("git", "rev-parse", "--is-inside-work-tree"): CommandResult(0, "true\n"),
            ("git", "rev-parse", "--show-toplevel"): CommandResult(
                0, f"{root.resolve()}\n"
            ),
            ("git", "remote", "get-url", "origin"): CommandResult(
                0, "git@github.com:human/louke.git\n"
            ),
            ("git", "rev-parse", "--verify", "refs/heads/main"): CommandResult(
                0, f"{sha}\n"
            ),
            ("git", "ls-remote", "--heads", "origin", "main"): CommandResult(
                0, f"{sha}\trefs/heads/main\n"
            ),
        }

    def run(self, argv, *, cwd: Path, timeout: float) -> CommandResult:
        """Return the configured response without a shell or side effect."""
        del cwd, timeout
        return self.responses[tuple(argv)]


def _gate_fixture(
    tmp_path: Path,
) -> tuple[TestClient, dict[str, object], dict[str, object]]:
    """Build a live authenticated client with a persisted M-STORY Scribe task."""
    client = _client(tmp_path)
    app = client.app
    run_store = app.state.v12_run_store
    run = run_store.create_run(run_store._catalog.get("new_feature", "1"))
    run = run_store.update_run(run.with_step("M-STORY", "waiting_for_human"), 0)
    artifact = StoryArtifactStore(run_store).save(
        run.run_id,
        "v0.14-001-workflow-reflow-spec",
        StoryInitResult(
            story_md_bytes=b"# Story\n\nShip the reflow\n",
            evidence=StoryRevisionEvidence(
                input_digest="sha256:input",
                file_digest="sha256:story",
                actor="human:human",
                run_id=run.run_id,
                commit_sha="sha-story",
            ),
            navigation=StoryNavigation(
                run_id=run.run_id,
                spec_id="v0.14-001-workflow-reflow-spec",
                phase="M-STORY",
                document="story",
                revision_digest="sha256:story",
                commit_sha="sha-story",
            ),
        ),
        f"story-init:{run.run_id}",
    )
    app.state.scribe_entry = ScribeEntryService(run_store, _GateOpenCode())
    task = app.state.scribe_entry.ensure_task(
        run_id=run.run_id,
        artifact=artifact,
        human_request="Ship the reflow",
        foundation_manifest_identity="foundation:gate",
        workspace=str(tmp_path),
    )
    preview = app.state.release_entry.preview("Ship the reflow", "0.14.0")
    app.state.release_entry._requests.update(
        preview["request_id"], project_id="project-gate", run_id=run.run_id
    )
    payload = {
        "role": "Scribe",
        "task_id": task["task_id"],
        "attempt_id": task["active_attempt"]["attempt_id"],
        "session_id": task["session_id"],
        "manifest_digest": task["manifest_digest"],
        "artifact_revision": artifact.revision,
        "artifact_digest": artifact.digest,
        "write_scope": ["story.md"],
        "recommendation": "Go",
        "reason": "The bounded story is ready for Human choice.",
    }
    app.state.scribe_entry.submit_result(
        run_id=run.run_id, task_id=task["task_id"], payload=payload
    )
    return client, {"run": run_store.get_run(run.run_id), "artifact": artifact}, task


def test_cross_origin_release_mutation_is_rejected_before_preview(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0600-03: foreign Origin cannot create or mutate a release request."""
    client = _client(tmp_path)

    response = client.post(
        "/api/projects/preview",
        headers={"Origin": "https://foreign.example", "X-Louke-CSRF": _csrf(client)},
        json={"story": "Ship the reflow", "release_version": "0.14.0"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_FORBIDDEN"


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        ({"story": "Ship the reflow", "release_version": ""}, "VALIDATION_ERROR"),
        ({"story": "Ship the reflow"}, "VALIDATION_ERROR"),
        (
            {"story": "Ship the reflow", "release_version": "../escape"},
            "RELEASE_VERSION_INVALID",
        ),
    ],
)
def test_preview_invalid_release_values_fail_closed_without_advancement(
    tmp_path: Path, setup_complete: Path, payload: dict[str, str], error_code: str
) -> None:
    """AC-FR0300-01: invalid preview values return stable 400 without persistence."""
    client = _client(tmp_path)
    before = _release_request_count(client)

    response = client.post(
        "/api/projects/preview",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == error_code
    assert _release_request_count(client) == before


def test_preview_non_object_payload_fails_closed_without_advancement(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0300-01: malformed preview structure returns stable 400 without state changes."""
    client = _client(tmp_path)
    before = _release_request_count(client)

    response = client.post(
        "/api/projects/preview",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json=["Ship the reflow", "0.14.0"],
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert _release_request_count(client) == before


def _story_action_payload(
    *,
    run_revision: int,
    artifact_revision: int,
    candidate: str,
    project_id: str = "project-gate",
) -> dict[str, object]:
    """Build a canonical Runtime phase-action request for Story decisions."""
    return {
        "action": "story_decision",
        "expected_run_revision": run_revision,
        "expected_artifact_revision": artifact_revision,
        "idempotency_key": f"decision-{candidate}",
        "payload": {
            "candidate": candidate,
            "reason": "Human decision reason",
            "project_id": project_id,
        },
    }


def test_story_gate_http_rejects_stale_agent_cross_project_and_invalid_candidate(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0700-03: invalid Human gate requests leave the decision empty."""
    client, facts, _ = _gate_fixture(tmp_path)
    run = facts["run"]
    artifact = facts["artifact"]
    headers = {
        "Origin": "https://louke.example",
        "X-Louke-CSRF": _csrf(client),
    }

    stale = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers=headers,
        json=_story_action_payload(
            run_revision=run.revision - 1,
            artifact_revision=artifact.revision,
            candidate="Go",
        ),
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "WORKFLOW_STATE_CONFLICT"

    agent_payload = _story_action_payload(
        run_revision=run.revision,
        artifact_revision=artifact.revision,
        candidate="Go",
    )
    agent_payload["payload"]["actor_kind"] = "agent"
    agent = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers=headers,
        json=agent_payload,
    )
    assert agent.status_code == 403
    assert agent.json()["error_code"] == "HUMAN_AUTHORITY_REQUIRED"

    outside = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers=headers,
        json=_story_action_payload(
            run_revision=run.revision,
            artifact_revision=artifact.revision,
            candidate="Go",
            project_id="project-other",
        ),
    )
    assert outside.status_code == 404
    assert outside.json()["error_code"] == "NOT_FOUND"

    invalid = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers=headers,
        json=_story_action_payload(
            run_revision=run.revision,
            artifact_revision=artifact.revision,
            candidate="Maybe",
        ),
    )
    assert invalid.status_code == 400
    assert invalid.json()["error_code"] == "VALIDATION_FAILED"
    assert client.app.state.scribe_entry.story_gate(run.run_id)["decision"] is None
    assert client.app.state.v12_run_store.get_run(run.run_id).current_step == "M-STORY"


def test_story_gate_http_accepts_authenticated_human_go_and_renders_gate_read_model(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0700-03: valid Human Go is persisted and exposed without M-SPEC."""
    client, facts, _ = _gate_fixture(tmp_path)
    run = facts["run"]
    artifact = facts["artifact"]
    pending = client.get("/api/projects/project-gate/current")
    assert pending.json()["story_gate"]["recommendation"] == "Go"
    assert pending.json()["story_gate"]["reason"]
    assert pending.json()["human_wait"] is True
    assert pending.json()["allowed_actions"] == ["story_decision"]
    story_page = client.get("/projects/project-gate/requirements/story")
    assert "Human story decision" in story_page.text
    assert "data-decision='Go'" in story_page.text
    headers = {
        "Origin": "https://louke.example",
        "X-Louke-CSRF": _csrf(client),
    }
    response = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers=headers,
        json=_story_action_payload(
            run_revision=run.revision,
            artifact_revision=artifact.revision,
            candidate="Go",
        ),
    )

    assert response.status_code == 200
    assert response.json()["value"] == "Go"
    assert response.json()["actor"] == "human:human"
    current = client.get("/api/projects/project-gate/current")
    assert current.status_code == 200
    assert current.json()["story_gate"]["decision"]["value"] == "Go"
    assert current.json()["run"]["phase"] == "M-STORY"
    assert current.json()["allowed_actions"] == []
    assert client.get("/projects/project-gate/requirements/story").status_code == 200


def test_story_gate_http_park_creates_terminal_backlog_and_needs_attention(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0800-01: valid Human Park creates one Backlog entry and no M-SPEC task."""
    client, facts, _ = _gate_fixture(tmp_path)
    run = facts["run"]
    artifact = facts["artifact"]
    response = client.post(
        f"/api/runs/{run.run_id}/actions",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json=_story_action_payload(
            run_revision=run.revision,
            artifact_revision=artifact.revision,
            candidate="Park",
        ),
    )

    assert response.status_code == 200
    assert response.json()["backlog_entry_count"] == 1
    assert response.json()["cleanup"]["status"] == "needs_attention"
    current = client.get("/api/projects/project-gate/current")
    assert current.json()["run"]["phase"] == "PARKED"
    assert current.json()["story_gate"]["m_spec_task_count"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {
            "expected_preview_revision": 0,
            "request_digest": "digest",
            "idempotency_key": "key",
        },
        {
            "preview_id": "",
            "expected_preview_revision": 0,
            "request_digest": "digest",
            "idempotency_key": "key",
        },
        {
            "preview_id": "preview",
            "expected_preview_revision": True,
            "request_digest": "digest",
            "idempotency_key": "key",
        },
        {
            "preview_id": "preview",
            "expected_preview_revision": 0,
            "request_digest": "",
            "idempotency_key": "key",
        },
    ],
)
def test_confirm_malformed_fields_fail_closed_without_advancement(
    tmp_path: Path, setup_complete: Path, payload: dict[str, object]
) -> None:
    """AC-FR0300-01: malformed confirm fields return stable 400 and keep preview state."""
    client = _client(tmp_path)
    preview = _preview(client)
    request_id = preview["request_id"]
    before = client.app.state.release_entry.status(request_id)

    response = client.post(
        "/api/projects/confirm",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    after = client.app.state.release_entry.status(request_id)
    assert after["status"] == before["status"] == "preview"


def test_confirm_non_object_payload_fails_closed_without_advancement(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0300-01: malformed confirm structure returns stable 400 without advancement."""
    client = _client(tmp_path)
    preview = _preview(client)
    request_id = preview["request_id"]

    response = client.post(
        "/api/projects/confirm",
        headers={"Origin": "https://louke.example", "X-Louke-CSRF": _csrf(client)},
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert client.app.state.release_entry.status(request_id)["status"] == "preview"


def test_cross_origin_scribe_mutation_is_rejected_before_task_access(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0600-03: foreign Origin cannot reply to a Scribe task."""
    client = _client(tmp_path)

    response = client.post(
        "/api/runs/run-1/tasks/task-1/messages",
        headers={"Origin": "https://foreign.example", "X-Louke-CSRF": _csrf(client)},
        json={
            "client_message_id": "message-1",
            "correlation_id": "correlation-1",
            "body": "Continue",
            "expected_attempt_id": "attempt-1",
            "expected_artifact_revision": 1,
        },
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_FORBIDDEN"


def test_story_page_renders_task_bound_chat_over_live_http(
    tmp_path: Path, setup_complete: Path
) -> None:
    """AC-FR0700-01: Story page exposes persisted Scribe facts and Chat controls."""
    client = _client(tmp_path)
    app = client.app
    app.state.release_entry.current_project = lambda project_id: {
        "project_id": project_id,
        "run_id": "run-1",
    }
    app.state.v12_run_store.get_run = lambda run_id: SimpleNamespace(
        run_id=run_id, current_step="M-STORY", revision=2, status="waiting_human"
    )
    app.state.story_entry.artifact = lambda run_id: SimpleNamespace(
        run_id=run_id,
        body_md="# Story\n\nShip the reflow",
        revision=1,
    )
    app.state.scribe_entry.task_for_run = lambda run_id: {"task_id": "task-1"}

    response = client.get("/projects/project-1/requirements/story")

    assert response.status_code == 200
    assert "id='scribe-chat'" in response.text
    assert "Scribe Chat" in response.text
    assert "/messages" in response.text
    assert "Role:" in response.text
    assert "Attempt:" in response.text
    assert "Session:" in response.text
    assert "Connection:" in response.text
    assert "scribe-retry" in response.text
    assert "scribe-reconcile" in response.text
    assert "crypto.randomUUID" in response.text
    assert "Maestro" not in response.text
    assert "<aside" not in response.text


def test_project_path_cannot_borrow_another_project_or_wrong_run(
    tmp_path: Path,
    setup_complete: Path,
) -> None:
    """AC-FR0600-01: project current lookup requires exact project/run binding."""
    client = _client(tmp_path)
    service = client.app.state.release_entry
    preview = service.preview("Ship the reflow", "v0.14.0")
    service._requests.update(
        preview["request_id"], project_id="project-a", run_id="run-a"
    )

    cross_project = client.get("/api/projects/project-b/current")
    wrong_run = client.get("/api/projects/project-a/current")

    assert cross_project.status_code == 404
    assert wrong_run.status_code == 404


def test_logout_deletes_strict_session_cookie(
    tmp_path: Path, setup_complete: Path
) -> None:
    """AC-NFR0100-01: logout deletion preserves the Strict cookie contract."""
    client = _client(tmp_path)

    response = client.post("/api/auth/logout")

    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1
    assert cookies[0].startswith("louke_session=")
    assert "Max-Age=0" in cookies[0]
    assert "SameSite=strict" in cookies[0]
