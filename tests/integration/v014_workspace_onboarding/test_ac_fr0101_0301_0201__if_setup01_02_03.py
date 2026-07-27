"""Login/Register, aggregate readiness, and post-Setup entry contracts.

AC-FR0101-01, AC-FR0101-02, AC-FR0201-01, AC-FR0201-02,
AC-FR0301-01, AC-FR0301-02, AC-FR0401-01,
AC-FR0901-01, AC-FR1001-01, AC-FR1101-01, AC-FR1501-01

These tests use the public Login and Project HTTP surfaces. Only the external
GitHub/Git command boundary and OpenCode model probe are controlled; no user
or Setup manifest is privately seeded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from starlette.testclient import TestClient

from louke.web.app import create_app
from louke.web.csrf_middleware import issue_for_session
from louke.web.environment_commands import CommandResult
from louke.web.opencode_probe import ModelCheckResult

from tests.test_web_server import authenticate, build_project


ORIGIN = "https://louke.example"


class ReadyExecutor:
    """Return a realistic, bounded GitHub/Git readiness transcript."""

    def __init__(self, root: Path) -> None:
        sha = "a" * 40
        self.responses = {
            ("gh", "--version"): CommandResult(0, "gh version 2.89.0\n"),
            ("gh", "auth", "status"): CommandResult(
                0,
                "github.com\n"
                "  ✓ Logged in to github.com account fixture-login\n"
                "  - Active account: true\n"
                "  - Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'\n",
            ),
            ("git", "rev-parse", "--is-inside-work-tree"): CommandResult(0, "true\n"),
            ("git", "rev-parse", "--show-toplevel"): CommandResult(
                0, f"{root.resolve()}\n"
            ),
            ("git", "remote", "get-url", "origin"): CommandResult(
                0, "git@github.com:zillionare/louke.git\n"
            ),
            ("git", "rev-parse", "--verify", "refs/heads/main"): CommandResult(
                0, f"{sha}\n"
            ),
            ("git", "ls-remote", "--heads", "origin", "main"): CommandResult(
                0, f"{sha}\trefs/heads/main\n"
            ),
        }

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        """Return the configured bounded command response."""
        del cwd, timeout
        return self.responses[tuple(argv)]


def _model_result(state: str) -> ModelCheckResult:
    """Return one redacted model-check result for the public seam."""
    diagnosis = None
    if state != "passed":
        diagnosis = {
            "object": "selected OpenCode model",
            "known_facts": "the selected model probe did not pass",
            "impact": "Login readiness cannot verify a working OpenCode model",
            "recovery_url": "/login",
        }
    return ModelCheckResult(
        check_id="chk_login_integration",
        revision=1,
        state=state,
        current_model_id="ark/minimax-m3",
        diagnosis=diagnosis,
    )


def _app(
    tmp_path: Path,
    model_checker: Callable[[Path], ModelCheckResult],
) -> TestClient:
    """Build a canonical ``zillionare/louke`` app with controlled seams."""
    root = build_project(tmp_path / "louke")
    project_toml = root / ".louke" / "project" / "project.toml"
    project_toml.write_text(
        project_toml.read_text(encoding="utf-8")
        .replace('version = "0.8"', 'version = "0.14.1"')
        .replace(
            'repo = "github.com/example/louke"', 'repo = "github.com/zillionare/louke"'
        )
        .replace('project = "louke-v0.8"', 'project = "louke-0.14.0"'),
        encoding="utf-8",
    )
    app = create_app(root, allowed_origin=ORIGIN)
    app.state.environment_executor = ReadyExecutor(root)
    app.state.readiness_model_checker = model_checker
    return TestClient(app)


def _csrf(client: TestClient) -> str:
    """Issue the current session-bound mutation token."""
    return issue_for_session(
        session_id=client.cookies["louke_session"].strip('"'), revision=0
    )


def _headers(client: TestClient) -> dict[str, str]:
    """Return the public mutation headers for the authenticated Human."""
    return {"Origin": ORIGIN, "X-Louke-CSRF": _csrf(client)}


def test_login_forms_and_warning_remain_public_when_model_is_blocked(
    tmp_path: Path,
) -> None:
    """AC-FR0201-02/AC-FR0301-01: readiness failure never blocks auth forms."""
    # AC-FR0201-02 / AC-FR0301-01
    client = _app(tmp_path, lambda _: _model_result("failed"))

    login = client.get("/login")
    readiness = client.get("/api/readiness/login")

    assert login.status_code == 200
    assert 'id="tab-login"' in login.text
    assert 'id="tab-register"' in login.text
    assert 'id="readiness-warning"' in login.text
    assert 'id="readiness-retry"' in login.text
    assert readiness.status_code == 200
    body = readiness.json()
    assert body["state"] == "blocked"
    assert body["current_step"] == "opencode_model"
    failed = body["steps"][-1]
    assert failed["diagnosis"]["object"]
    assert failed["diagnosis"]["impact"]
    assert failed["actions"] == ["Retry"]

    registered = client.post(
        "/api/auth/register", json={"username": "human", "password": "secret"}
    )
    assert registered.status_code == 200
    client.post("/api/auth/logout")
    logged_in = client.post(
        "/api/auth/login", json={"username": "human", "password": "secret"}
    )
    assert logged_in.status_code == 200


def test_login_readiness_retry_is_fresh_and_preserves_uncertainty(
    tmp_path: Path,
) -> None:
    """AC-FR0201-02: each readiness request is a fresh terminal rerun."""
    # AC-FR0201-02
    states = iter(("uncertain", "passed"))
    calls: list[int] = []

    def checker(_: Path) -> ModelCheckResult:
        calls.append(1)
        return _model_result(next(states))

    client = _app(tmp_path, checker)
    first = client.get("/api/readiness/login").json()
    second = client.get("/api/readiness/login").json()

    assert first["state"] == "uncertain"
    assert first["current_step"] == "opencode_model"
    assert second["state"] == "passed"
    assert calls == [1, 1]


def test_unauthenticated_workbench_uses_the_public_login_entry(
    tmp_path: Path,
) -> None:
    """AC-FR0401-01: Login is the sole unauthenticated Web entry."""
    # AC-FR0401-01
    client = _app(tmp_path, lambda _: _model_result("passed"))

    root = client.get("/", follow_redirects=False)
    workbench = client.get("/workbench", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"].startswith("/login")
    assert workbench.status_code == 303
    assert workbench.headers["location"].startswith("/login")


def test_project_preview_identity_and_confirm_gate_bind_to_aggregate_readiness(
    tmp_path: Path,
) -> None:
    """AC-FR0901-01/AC-FR1001-01/AC-FR1101-01/AC-FR1501-01: Project gate."""
    # AC-FR0901-01 / AC-FR1001-01 / AC-FR1101-01 / AC-FR1501-01
    state = {"value": "failed"}
    client = _app(tmp_path, lambda _: _model_result(state["value"]))
    authenticate(client, username="human", password="secret")

    wizard = client.get("/workbench?activity=projects&action=new_project")
    assert wizard.status_code == 200
    assert 'name="story"' in wizard.text
    assert 'name="release_version"' in wizard.text
    assert 'name="story"' in wizard.text and "required disabled" in wizard.text
    assert 'data-testid="env-step-opencode_model"' in wizard.text

    state["value"] = "passed"
    ready = client.post("/api/projects/environment-checks", headers=_headers(client))
    assert ready.status_code == 200
    assert ready.json()["state"] == "passed"

    preview = client.post(
        "/api/projects/preview",
        headers={**_headers(client), "Idempotency-Key": "login-preview"},
        json={"story": "Ship Login readiness", "release_version": "0.14.1"},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["workspace"] == {
        "workspace_id": "github.com/zillionare/louke",
        "label": "louke",
    }
    assert body["repository"]["owner"] == "zillionare"
    assert body["repository"]["name"] == "louke"
    assert body["release"]["canonical"] == "0.14.1"
    assert "louke-0.14.0" not in json.dumps(body["workspace"])

    state["value"] = "failed"
    confirm = client.post(
        "/api/projects/confirm",
        headers={**_headers(client), "Idempotency-Key": "login-confirm"},
        json={
            "preview_id": body["preview_id"],
            "expected_preview_revision": body["preview_revision"],
            "request_digest": body["request_digest"],
        },
    )
    assert confirm.status_code == 409
    assert confirm.json()["error_code"] == "ENVIRONMENT_GATE_BLOCKED"
