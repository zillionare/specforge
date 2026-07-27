"""Unit contracts for Login readiness and the post-Setup Web entry flow."""

from __future__ import annotations

from pathlib import Path
import time

from starlette.testclient import TestClient

from louke.web.app import create_app
from louke.web.csrf_middleware import issue_for_session
from louke.web.environment_commands import CommandResult
from louke.web.login_readiness import LoginReadinessService, _selected_model_candidates
from louke.web.opencode_probe import ModelCheckResult
from louke.web import login_readiness

from tests.test_web_server import authenticate, build_project

ORIGIN = "https://louke.example"


class ReadyExecutor:
    """Return a controlled terminal GitHub/Git readiness transcript."""

    def __init__(self, root: Path) -> None:
        sha = "a" * 40
        self.responses = {
            ("gh", "--version"): CommandResult(0, "gh version 2.89.0\n"),
            ("gh", "auth", "status"): CommandResult(
                0,
                "Logged in to github.com account quantclaws\n"
                "Active account: true\n"
                "Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'\n",
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
    """Return one redacted selected-model probe result for the app seam."""
    diagnosis = None
    if state != "passed":
        diagnosis = {
            "object": "selected OpenCode model",
            "known_facts": "the selected model probe failed",
            "impact": "New Project cannot verify a working model",
            "recovery_url": "/login",
        }
    return ModelCheckResult(
        check_id="chk_login",
        revision=1,
        state=state,
        current_model_id="minimax/m3",
        diagnosis=diagnosis,
    )


def _app(tmp_path: Path, model_result: ModelCheckResult) -> TestClient:
    """Build a Web app with the canonical repo and controlled readiness seams."""
    root = build_project(tmp_path / "louke")
    project_toml = root / ".louke" / "project" / "project.toml"
    project_toml.write_text(
        project_toml.read_text(encoding="utf-8")
        .replace(
            'repo = "github.com/example/louke"', 'repo = "github.com/zillionare/louke"'
        )
        .replace('project = "louke-v0.8"', 'project = "louke-0.14.0"'),
        encoding="utf-8",
    )
    app = create_app(root, allowed_origin=ORIGIN)
    app.state.environment_executor = ReadyExecutor(root)
    app.state.readiness_model_checker = lambda _: model_result
    return TestClient(app)


def _csrf(client: TestClient) -> str:
    """Issue the current session-bound CSRF token."""
    return issue_for_session(
        session_id=client.cookies["louke_session"].strip('"'), revision=0
    )


def test_selected_model_candidates_use_existing_alias_resolution(
    tmp_path: Path,
) -> None:
    """Readiness probes the configured concrete model rather than the old alias."""
    root = build_project(tmp_path / "louke")

    assert _selected_model_candidates(root) == ["ark/minimax-m3"]


def test_preview_uses_canonical_repo_workspace_and_visible_label(
    tmp_path: Path,
) -> None:
    """Preview binds repo identity while hiding the historical project label."""
    client = _app(tmp_path, _model_result("passed"))
    authenticate(client, username="human", password="secret")

    response = client.post(
        "/api/projects/preview",
        headers={
            "Origin": ORIGIN,
            "X-Louke-CSRF": _csrf(client),
            "Idempotency-Key": "preview-login-readiness",
        },
        json={"story": "Ship Login readiness", "release_version": "0.14.1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"] == {
        "workspace_id": "github.com/zillionare/louke",
        "label": "louke",
    }
    assert body["repository"] == {
        "host": "github.com",
        "owner": "zillionare",
        "name": "louke",
        "main_sha": "a" * 40,
    }
    assert body["release"]["canonical"] == "0.14.1"
    workbench = client.get("/workbench?activity=projects&action=new_project")
    assert workbench.status_code == 200
    assert "louke.new-project.v1:github.com/zillionare/louke:human" in workbench.text
    assert "louke.new-project.v1:louke-0.14.0:human" not in workbench.text


def test_login_readiness_is_public_and_retry_is_a_fresh_rerun(tmp_path: Path) -> None:
    """Blocked Login readiness exposes a warning and Retry reruns fresh facts."""
    client = _app(tmp_path, _model_result("failed"))
    checks: list[int] = []

    def checker(_: Path) -> ModelCheckResult:
        checks.append(1)
        return _model_result("failed" if len(checks) == 1 else "passed")

    client.app.state.readiness_model_checker = checker

    login = client.get("/login")
    first = client.get("/api/readiness/login")
    second = client.get("/api/readiness/login")

    assert login.status_code == 200
    assert 'id="tab-register"' in login.text
    assert "Readiness warning" in login.text
    assert 'id="login-submit" type="submit"' in login.text
    assert 'id="register-submit" class="secondary"' in login.text
    assert "disabled" not in login.text.split('id="readiness-panel"', 1)[0]
    assert (
        client.post(
            "/api/auth/register", json={"username": "human", "password": "secret"}
        ).status_code
        == 200
    )
    assert first.status_code == 200
    assert first.json()["state"] == "blocked"
    assert first.json()["current_step"] == "opencode_model"
    assert second.status_code == 200
    assert second.json()["state"] == "passed"
    assert checks == [1, 1]


def test_login_page_renders_all_readiness_failures_without_disabling_auth(
    tmp_path: Path,
) -> None:
    """Login reports every failure while Register and Login stay independent."""
    client = _app(tmp_path, _model_result("failed"))

    login = client.get("/login")

    assert "filter(function(step)" in login.text
    assert "response.ok" in login.text
    assert "invalid readiness response" in login.text
    assert "readinessWarning.hidden = false" in login.text
    assert 'id="login-submit" type="submit"' in login.text
    assert 'id="register-submit" class="secondary"' in login.text


def test_hung_readiness_returns_warning_without_disabling_auth(
    tmp_path: Path, monkeypatch
) -> None:
    """The public Login endpoint times out to an uncertain warning, not auth failure."""
    client = _app(tmp_path, _model_result("passed"))
    monkeypatch.setattr(login_readiness, "AGGREGATE_READINESS_TIMEOUT_SECONDS", 0.01)

    def delayed(_: Path) -> ModelCheckResult:
        time.sleep(0.05)
        return _model_result("passed")

    client.app.state.readiness_model_checker = delayed
    response = client.get("/api/readiness/login")
    login = client.get("/login")

    assert response.status_code == 200
    assert response.json()["state"] == "uncertain"
    assert 'id="login-submit" type="submit"' in login.text
    assert 'id="register-submit" class="secondary"' in login.text


def test_injected_git_executor_without_model_evidence_is_not_ready(
    tmp_path: Path,
) -> None:
    """A controlled Git executor cannot manufacture selected-model success."""
    root = build_project(tmp_path / "louke")

    result = LoginReadinessService(root, executor=ReadyExecutor(root)).check()

    assert result["state"] == "uncertain"
    assert result["current_step"] == "opencode_model"
    assert result["steps"][-1]["state"] == "uncertain"


def test_unauthenticated_entry_uses_login_and_setup_is_unregistered(
    tmp_path: Path,
) -> None:
    """Unauthenticated Web entry redirects to Login and no Setup route exists."""
    client = _app(tmp_path, _model_result("passed"))

    root = client.get("/", follow_redirects=False)
    workbench = client.get("/workbench", follow_redirects=False)
    setup = client.get("/setup")
    setup_api = client.get("/api/setup/status")

    assert root.status_code == 303
    assert root.headers["location"].startswith("/login")
    assert workbench.status_code == 303
    assert workbench.headers["location"].startswith("/login")
    assert setup.status_code == 404
    assert setup_api.status_code == 404


def test_new_project_is_fail_closed_until_aggregate_readiness_passes(
    tmp_path: Path,
) -> None:
    """New Project remains disabled/409 when the selected model is blocked."""
    client = _app(tmp_path, _model_result("failed"))
    authenticate(client, username="human", password="secret")

    check = client.post(
        "/api/projects/environment-checks",
        headers={"Origin": ORIGIN, "X-Louke-CSRF": _csrf(client)},
    )
    preview = client.post(
        "/api/projects/preview",
        headers={
            "Origin": ORIGIN,
            "X-Louke-CSRF": _csrf(client),
            "Idempotency-Key": "blocked-preview",
        },
        json={"story": "Blocked", "release_version": "0.14.1"},
    )

    assert check.status_code == 200
    assert check.json()["state"] == "blocked"
    assert check.json()["current_step"] == "opencode_model"
    assert preview.status_code == 409
    assert preview.json()["error_code"] == "ENVIRONMENT_GATE_BLOCKED"


def test_malformed_project_context_blocks_preview_and_confirm(tmp_path: Path) -> None:
    """Unreadable project context never becomes an empty creation context."""
    client = _app(tmp_path, _model_result("passed"))
    authenticate(client, username="human", password="secret")
    state_path = client.app.state.workspace_root / ".louke" / "project-state.json"
    state_path.write_text("not json", encoding="utf-8")

    response = client.post(
        "/api/projects/preview",
        headers={
            "Origin": ORIGIN,
            "X-Louke-CSRF": _csrf(client),
            "Idempotency-Key": "malformed-context",
        },
        json={"story": "Blocked", "release_version": "0.14.1"},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "PROJECT_CONTEXT_NOT_EMPTY"


def test_confirm_reruns_empty_context_before_side_effects(tmp_path: Path) -> None:
    """A context created after Preview blocks first Confirm before Foundation work."""
    client = _app(tmp_path, _model_result("passed"))
    authenticate(client, username="human", password="secret")
    preview = client.post(
        "/api/projects/preview",
        headers={
            "Origin": ORIGIN,
            "X-Louke-CSRF": _csrf(client),
            "Idempotency-Key": "preview-before-context-change",
        },
        json={"story": "Context race", "release_version": "0.14.1"},
    ).json()
    state_path = client.app.state.workspace_root / ".louke" / "project-state.json"
    state_path.write_text(
        '{"state": "active", "project_id": "prj_existing"}', encoding="utf-8"
    )

    confirmed = client.post(
        "/api/projects/confirm",
        headers={
            "Origin": ORIGIN,
            "X-Louke-CSRF": _csrf(client),
            "Idempotency-Key": "confirm-after-context-change",
        },
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"],
            "request_digest": preview["request_digest"],
        },
    )

    assert confirmed.status_code == 409
    assert confirmed.json()["error_code"] == "PROJECT_CONTEXT_NOT_EMPTY"
