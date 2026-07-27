"""Focused HTTP contracts for the stable Project creation API.

These replace the useful Preview/Confirm coverage lost with the retired
mounted ``/api/projects`` sub-app.  The real HTTP handlers, Runtime release
service, SQLite store, and Story transition are exercised; only the external
GitHub/Foundation and document-writer boundaries are controlled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from louke.runtime.release_entry import (
    FoundationOutcome,
    MainCheck,
    ReleaseEntryService,
)
from louke.runtime.story_entry import StoryEntryService
from louke.runtime.story_init import (
    StoryInitResult,
    StoryNavigation,
    StoryRevisionEvidence,
)
from louke.web.app import create_app
from louke.web.csrf_middleware import issue_for_session
from louke.web.environment_commands import CommandResult
from louke.web.opencode_probe import ModelCheckResult
from louke.web.pages.workbench import (
    _projects_main_panel_active,
    _runtime_active_project_state,
)

from tests.test_web_server import authenticate, build_project


ORIGIN = "https://louke.example"
SHA = "a" * 40


def _passed_model(_: Path) -> ModelCheckResult:
    """Return explicit selected-model evidence for the controlled host."""
    return ModelCheckResult(
        check_id="chk_projects",
        revision=1,
        state="passed",
        current_model_id="fixture/model",
    )


class ReadOnlyExecutor:
    """Provide the exact bounded argv transcript for a ready workspace."""

    def __init__(self, root: Path) -> None:
        self.calls: list[tuple[tuple[str, ...], float]] = []
        self.responses = {
            ("gh", "--version"): CommandResult(0, "gh version 2.50.0\n"),
            ("gh", "auth", "status"): CommandResult(
                0,
                "Logged in to github.com account alice\n"
                "Token scopes: 'gist', 'project', 'repo', 'workflow'\n",
            ),
            ("git", "rev-parse", "--is-inside-work-tree"): CommandResult(0, "true\n"),
            ("git", "rev-parse", "--show-toplevel"): CommandResult(
                0, f"{root.resolve()}\n"
            ),
            ("git", "remote", "get-url", "origin"): CommandResult(
                0, "git@github.com:alice/louke.git\n"
            ),
            ("git", "rev-parse", "--verify", "refs/heads/main"): CommandResult(
                0, f"{SHA}\n"
            ),
            ("git", "ls-remote", "--heads", "origin", "main"): CommandResult(
                0, f"{SHA}\trefs/heads/main\n"
            ),
        }

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        """Record one read-only readiness command without invoking a shell."""
        del cwd
        command = tuple(argv)
        self.calls.append((command, timeout))
        return self.responses[command]


@dataclass
class ReadyFoundation:
    """Controlled external Foundation boundary for the real release service."""

    preflight_calls: int = 0
    provision_calls: int = 0

    def preflight(self, story: str, release_version: str) -> MainCheck:
        """Return a successful external preflight without changing Git."""
        del story, release_version
        self.preflight_calls += 1
        return MainCheck(
            status="pass",
            remote_main={"sha": SHA},
            previous_branch={},
            remediation="",
        )

    def provision(
        self,
        story: str,
        release_version: str,
        run_id: str,
        main_check: MainCheck,
        spec_id: str,
    ) -> FoundationOutcome:
        """Return one stable external resource bundle for the confirmed request."""
        del story, release_version, main_check
        self.provision_calls += 1
        return FoundationOutcome(
            status="ready",
            resources={
                "github_project": {"node_id": "PVT_stable"},
                "workflow_run": {"id": run_id},
                "spec_directory": {"path": f".louke/project/specs/{spec_id}"},
                "worktree": {"path": "/workspace"},
            },
            remediation="",
        )


@dataclass
class StoryWriter:
    """Controlled document boundary that records canonical Story initialization."""

    calls: int = 0

    def write_story(
        self,
        *,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        run_id: str,
    ) -> StoryInitResult:
        """Return an independent Story write result for the real runtime transition."""
        del workspace
        self.calls += 1
        body = f"# Story\n\n{human_story}\n"
        return StoryInitResult(
            story_md_bytes=body.encode(),
            evidence=StoryRevisionEvidence(
                input_digest="sha256:input",
                file_digest="sha256:story",
                actor=actor,
                run_id=run_id,
                commit_sha="story-sha",
            ),
            navigation=StoryNavigation(
                run_id=run_id,
                spec_id=spec_id,
                phase="M-STORY",
                document="story",
                revision_digest="sha256:story",
                commit_sha="story-sha",
            ),
        )


def _csrf(client: TestClient) -> str:
    """Issue a CSRF token for the authenticated test session."""
    return issue_for_session(
        session_id=client.cookies["louke_session"].strip('"'), revision=0
    )


def _headers(
    client: TestClient, *, idempotency_key: str | None = None
) -> dict[str, str]:
    """Return the public same-origin mutation headers."""
    headers = {"Origin": ORIGIN, "X-Louke-CSRF": _csrf(client)}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _client_with_ready_runtime(
    root: Path,
) -> tuple[TestClient, ReadOnlyExecutor, ReadyFoundation, StoryWriter]:
    """Build an authenticated real app with only external boundaries controlled."""
    build_project(root)
    app = create_app(root, allowed_origin=ORIGIN)
    executor = ReadOnlyExecutor(root)
    foundation = ReadyFoundation()
    writer = StoryWriter()
    app.state.environment_executor = executor
    app.state.readiness_model_checker = _passed_model
    app.state.release_entry = ReleaseEntryService(
        app.state.v12_run_store,
        foundation,
        workspace_id=app.state.workspace_id,
        story_entry=StoryEntryService(app.state.v12_run_store, writer),
        workspace_root=root,
    )
    client = TestClient(app)
    authenticate(client, username="human", password="secret")
    return client, executor, foundation, writer


def test_ac_fr0601_01_environment_api_is_terminal_fresh_and_read_only(
    tmp_path: Path,
) -> None:
    """AC-FR0601-01: each Retry is a new terminal read-only readiness run."""
    client, executor, _foundation, _writer = _client_with_ready_runtime(tmp_path)

    first = client.post("/api/projects/environment-checks", headers=_headers(client))
    second = client.post("/api/projects/environment-checks", headers=_headers(client))

    assert first.status_code == second.status_code == 200
    assert first.json()["state"] == second.json()["state"] == "passed"
    assert len(executor.calls) == 14, (
        "AC-FR0601-01: Retry must rerun all readiness reads"
    )
    assert all(0 < timeout <= 15 for _command, timeout in executor.calls)
    mutating_argv_prefixes = {
        ("git", "init"),
        ("git", "add"),
        ("git", "commit"),
        ("git", "push"),
        ("git", "fetch"),
        ("git", "checkout"),
        ("git", "switch"),
        ("git", "remote", "set-url"),
    }
    assert not any(
        command[: len(prefix)] == prefix
        for command, _timeout in executor.calls
        for prefix in mutating_argv_prefixes
    ), "AC-FR0601-01: readiness may read origin but must not rewrite workspace Git"
    assert not (tmp_path / ".louke" / "gh-ledger.json").exists()


def test_ac_fr0601_01_environment_permission_error_is_a_terminal_diagnosis(
    tmp_path: Path, monkeypatch
) -> None:
    """AC-FR0601-01: an unavailable command is a readable terminal result, not HTTP 500."""
    client, _executor, _foundation, _writer = _client_with_ready_runtime(tmp_path)
    client.app.state.environment_executor = None

    def denied(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied", "gh")

    monkeypatch.setattr("louke.web.environment_commands.subprocess.run", denied)

    response = client.post("/api/projects/environment-checks", headers=_headers(client))

    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "blocked"
    assert result["current_step"] == "gh_executable"
    assert result["steps"][0]["diagnosis"] == {
        "object": "gh_executable",
        "impact": "Install or expose gh, then retry.",
    }
    assert result["steps"][0]["actions"] == ["Retry"]


def test_ac_fr1001_01_fr1101_01_preview_is_read_only_and_confirm_creates_one_project(
    tmp_path: Path,
) -> None:
    """AC-FR1001-01/AC-FR1101-01: stable Preview then Create yields one M-STORY Project."""
    client, executor, foundation, writer = _client_with_ready_runtime(tmp_path)

    preview = client.post(
        "/api/projects/preview",
        headers=_headers(client),
        json={"story": "Ship the focused bootstrap", "release_version": "0.15.0"},
    )

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["release"] == {
        "external": "0.15.0",
        "canonical": "0.15.0",
        "tag": "v0.15.0",
        "branch": "releases/0.15.0",
    }
    assert preview_body["side_effects"] == []
    assert foundation.preflight_calls == foundation.provision_calls == writer.calls == 0
    assert not (tmp_path / ".louke" / "project-state.json").exists()

    confirm_payload = {
        "preview_id": preview_body["preview_id"],
        "expected_preview_revision": preview_body["preview_revision"],
        "request_digest": preview_body["request_digest"],
    }
    created = client.post(
        "/api/projects/confirm",
        headers=_headers(client, idempotency_key="create-focused-bootstrap"),
        json=confirm_payload,
    )
    readiness_calls_before_replay = len(executor.calls)
    executor.responses[("gh", "--version")] = CommandResult(1, stderr="gh unavailable")
    replay = client.post(
        "/api/projects/confirm",
        headers=_headers(client, idempotency_key="create-focused-bootstrap"),
        json=confirm_payload,
    )

    assert created.status_code == replay.status_code == 202
    assert replay.json() == created.json()
    assert len(executor.calls) == readiness_calls_before_replay, (
        "AC-FR1101-01: an exact ready replay must return persisted state before "
        "a later readiness change is observed"
    )
    creation = created.json()
    assert creation["state"] == "ready"
    assert creation["project_id"].startswith("prj_")
    assert creation["story"]["phase"] == "M-STORY"
    assert creation["run"]["current_step"] == "M-STORY"
    assert foundation.preflight_calls == foundation.provision_calls == writer.calls == 1
    state = json.loads((tmp_path / ".louke" / "project-state.json").read_text())
    assert state["state"] == "active"
    assert state["project_id"] == creation["project_id"]
    status = client.get(f"/api/projects/requests/{creation['request_id']}")
    assert status.status_code == 200
    assert status.json()["run_id"] == creation["run_id"]
    current = client.get(f"/api/projects/{creation['project_id']}/current")
    assert current.status_code == 200
    current_body = current.json()
    assert current_body["project"] == {
        "project_id": creation["project_id"],
        "spec_id": creation["spec_id"],
    }
    assert current_body["run"]["run_id"] == creation["run_id"]
    assert "project_id" not in current_body
    assert "spec_id" not in current_body
    request = Request({"type": "http", "method": "GET", "path": "/", "app": client.app})
    projected = _runtime_active_project_state(request, state)
    html = _projects_main_panel_active(projected)
    assert "Active: M-STORY" in html
    assert creation["run_id"] in html
    assert 'data-stage="M-START" data-status="completed"' in html
    runtime_status = client.app.state.v12_run_store.get_run(creation["run_id"]).status
    assert f'data-stage="M-STORY" data-status="{runtime_status}"' in html
    assert 'data-display-state="active"' in html
    assert f'data-stage-id="stage:{creation["run_id"]}:M-START"' in html
    assert f'data-stage-id="stage:{creation["run_id"]}:M-STORY"' in html

    wrong_key = client.post(
        "/api/projects/confirm",
        headers=_headers(client, idempotency_key="another-key"),
        json=confirm_payload,
    )
    wrong_digest = client.post(
        "/api/projects/confirm",
        headers=_headers(client, idempotency_key="create-focused-bootstrap"),
        json={**confirm_payload, "request_digest": "sha256:wrong"},
    )
    assert wrong_key.status_code == 409
    assert wrong_key.json()["error_code"] == "REQUEST_CONFLICT"
    assert wrong_digest.status_code == 409
    assert wrong_digest.json()["error_code"] == "STALE_PREVIEW"
    attempts = client.app.state.v12_run_store.get_step_attempts(creation["run_id"])
    start_attempt = next(
        attempt for attempt in attempts if attempt.step_id == "M-START"
    )
    assert start_attempt.status == "completed"
    assert start_attempt.attempt_id
    assert (
        f'data-attempt-id="{start_attempt.attempt_id}" '
        f'data-stage-id="stage:{creation["run_id"]}:M-START"'
    ) in html


@pytest.mark.parametrize("change_repository", [False, True])
def test_confirm_rejects_a_preview_when_readiness_identity_changes(
    tmp_path: Path, change_repository: bool
) -> None:
    """Confirm fails stale before Foundation, Runtime, or Story side effects."""
    client, executor, foundation, writer = _client_with_ready_runtime(tmp_path)
    preview = client.post(
        "/api/projects/preview",
        headers=_headers(client),
        json={"story": "Ship stale protection", "release_version": "0.15.0"},
    ).json()
    changed_sha = "b" * 40
    if change_repository:
        executor.responses[("git", "remote", "get-url", "origin")] = CommandResult(
            0, "git@github.com:bob/other.git\n"
        )
    else:
        executor.responses[("git", "rev-parse", "--verify", "refs/heads/main")] = (
            CommandResult(0, f"{changed_sha}\n")
        )
        executor.responses[("git", "ls-remote", "--heads", "origin", "main")] = (
            CommandResult(0, f"{changed_sha}\trefs/heads/main\n")
        )

    confirmed = client.post(
        "/api/projects/confirm",
        headers=_headers(client, idempotency_key="stale-main"),
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"],
            "request_digest": preview["request_digest"],
        },
    )

    assert confirmed.status_code == 409
    assert confirmed.json()["error_code"] == "STALE_PREVIEW"
    assert foundation.preflight_calls == foundation.provision_calls == writer.calls == 0
    assert client.app.state.v12_run_store.list_runs() == ()
    assert not (tmp_path / ".louke" / "project-state.json").exists()


def test_ac_fr0601_02_stable_routes_expose_no_versioned_project_api(
    tmp_path: Path,
) -> None:
    """AC-FR0601-02: the bootstrap exports stable Project endpoints only."""
    build_project(tmp_path)
    app = create_app(tmp_path, allowed_origin=ORIGIN)
    paths = {getattr(route, "path", "") for route in app.routes}

    assert {
        "/api/projects/environment-checks",
        "/api/projects/preview",
        "/api/projects/confirm",
        "/api/projects/requests/{request_id}",
    }.issubset(paths)
    assert not any("/v14/" in path or "/v0.14/" in path for path in paths)
