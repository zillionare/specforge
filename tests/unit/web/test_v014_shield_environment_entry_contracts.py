"""Traceable Shield contracts for the terminal Environment entry surface."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from louke.web.csrf_middleware import issue_for_session
from louke.web.environment_commands import CommandResult
from louke.web.opencode_probe import ModelCheckResult

from tests.test_web_server import authenticate, build_project


ORIGIN = "https://louke.example"


def _passed_model(_: Path) -> ModelCheckResult:
    """Return explicit selected-model evidence for the controlled host."""
    return ModelCheckResult(
        check_id="chk_environment",
        revision=1,
        state="passed",
        current_model_id="fixture/model",
    )


class RecordingExecutor:
    """Provide controlled read-only command results to the real HTTP app."""

    def __init__(self, root: Path) -> None:
        sha = "a" * 40
        self.calls: list[tuple[str, ...]] = []
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
                0, f"{sha}\n"
            ),
            ("git", "ls-remote", "--heads", "origin", "main"): CommandResult(
                0, f"{sha}\trefs/heads/main\n"
            ),
        }

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        """Record a bounded readiness read without invoking an external process."""
        del cwd, timeout
        command = tuple(argv)
        self.calls.append(command)
        return self.responses[command]


def _csrf(client: TestClient) -> str:
    """Issue the test session's canonical CSRF token."""
    return issue_for_session(
        session_id=client.cookies["louke_session"].strip('"'), revision=0
    )


def test_environment_entry_is_authenticated_and_terminal(tmp_path: Path) -> None:
    """New Project receives one current read-only readiness projection."""
    build_project(tmp_path)
    app = create_app(tmp_path, allowed_origin=ORIGIN)
    executor = RecordingExecutor(tmp_path)
    app.state.environment_executor = executor
    app.state.readiness_model_checker = _passed_model
    client = TestClient(app)

    assert client.post("/api/projects/environment-checks").status_code == 401

    authenticate(client, username="human", password="secret")
    response = client.post(
        "/api/projects/environment-checks",
        headers={"Origin": ORIGIN, "X-Louke-CSRF": _csrf(client)},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "passed"
    assert response.json()["create_enabled"] is True
    assert len(executor.calls) == 7
