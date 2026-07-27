"""Terminal Environment readiness integration contracts.

AC-FR0601-01, AC-FR0601-02, AC-FR0701-01, AC-FR0801-01

The Human-authorized bootstrap has one synchronous, read-only Environment
projection. These tests exercise the real Environment service and GitHub/Git
readiness modules; only bounded external argv responses are controlled.
"""

from __future__ import annotations

from pathlib import Path

from louke.web.environment_commands import CommandResult
from louke.web.environment_service import CANONICAL_STEPS, EnvironmentService
from louke.web.github_readiness import REQUIRED_SCOPES


class RecordingExecutor:
    """Controlled argv boundary that records each read-only readiness call."""

    def __init__(
        self, root: Path, responses: dict[tuple[str, ...], CommandResult]
    ) -> None:
        self.root = root
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        assert cwd == self.root.resolve()
        assert 0 < timeout <= 15
        command = tuple(argv)
        self.calls.append(command)
        return self.responses[command]


def _ready_responses(root: Path) -> dict[tuple[str, ...], CommandResult]:
    sha = "a" * 40
    return {
        ("gh", "--version"): CommandResult(0, "gh version 2.65.0\n"),
        ("gh", "auth", "status"): CommandResult(
            0,
            "github.com\n"
            "  ✓ Logged in to github.com account fixture-login "
            "(/Users/openclaw/.config/gh/hosts.yml)\n"
            "  - Active account: true\n"
            "  - Git operations protocol: https\n"
            "  - Token: gho_************************************\n"
            "  - Token scopes: 'gist', 'project', 'repo', 'workflow'\n",
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


def test_ac_fr0701_01_required_github_scopes_are_locked() -> None:
    """AC-FR0701-01: readiness accepts exactly the required GitHub scopes."""
    assert set(REQUIRED_SCOPES) == {"gist", "project", "repo", "workflow"}


def test_ac_fr0601_01_terminal_ready_projection_is_read_only(tmp_path: Path) -> None:
    """AC-FR0601-01/AC-FR0801-01: one check returns canonical repository facts."""
    executor = RecordingExecutor(tmp_path, _ready_responses(tmp_path))

    result = EnvironmentService(tmp_path, executor=executor).check()

    assert result["state"] == "passed"
    assert result["current_step"] is None
    assert (
        result["story_input_enabled"]
        is result["preview_enabled"]
        is result["create_enabled"]
        is True
    )
    assert [step["id"] for step in result["steps"]] == list(CANONICAL_STEPS)
    auth = result["steps"][1]["observed"]
    assert auth["host"] == "github.com"
    assert isinstance(auth["identity"], str) and auth["identity"].strip()
    assert auth["identity"].lower() not in {"true", "false"}
    assert set(REQUIRED_SCOPES).issubset(auth["scopes"])
    repository = result["steps"][2]["observed"]
    assert repository == {"host": "github.com", "owner": "zillionare", "name": "louke"}
    assert result["steps"][3]["observed"]["main_sha"] == "a" * 40
    assert executor.calls == list(_ready_responses(tmp_path))
    assert all(
        command[:2] not in {("git", "add"), ("git", "commit"), ("git", "push")}
        for command in executor.calls
    )


def test_ac_fr0601_02_blocked_diagnosis_exposes_repair_action(tmp_path: Path) -> None:
    """AC-FR0601-02/AC-FR0701-02: missing scope is terminal and actionable."""
    responses = _ready_responses(tmp_path)
    responses[("gh", "auth", "status")] = CommandResult(
        0,
        "github.com\n"
        "  ✓ Logged in to github.com account fixture-login "
        "(/Users/openclaw/.config/gh/hosts.yml)\n"
        "  - Active account: true\n"
        "  - Git operations protocol: https\n"
        "  - Token: gho_************************************\n"
        "  - Token scopes: 'gist', 'project', 'repo'\n",
    )

    result = EnvironmentService(
        tmp_path, executor=RecordingExecutor(tmp_path, responses)
    ).check()

    assert result["state"] == "blocked"
    assert result["current_step"] == "gh_auth_scopes"
    failed = result["steps"][1]
    assert "workflow" in failed["missing"]
    assert failed["diagnosis"]["object"] == "gh_auth_scopes"
    assert failed["diagnosis"]["impact"]
    assert failed["actions"] == ["Retry"]
    assert result["create_enabled"] is False


def test_ac_fr0801_02_main_mismatch_blocks_without_mutating_workspace(
    tmp_path: Path,
) -> None:
    """AC-FR0801-02: mismatched canonical main remains blocked with Retry."""
    responses = _ready_responses(tmp_path)
    responses[("git", "ls-remote", "--heads", "origin", "main")] = CommandResult(
        0, f"{'b' * 40}\trefs/heads/main\n"
    )
    executor = RecordingExecutor(tmp_path, responses)

    result = EnvironmentService(tmp_path, executor=executor).check()

    failed = result["steps"][3]
    assert result["state"] == "blocked"
    assert failed["id"] == "canonical_main"
    assert failed["diagnosis"]["impact"] == "Local main must match origin/main."
    assert failed["actions"] == ["Retry"]
    assert all(
        command[0] != "git" or command[1] not in {"add", "commit", "push"}
        for command in executor.calls
    )


def test_ac_fr0601_02_retry_is_a_fresh_terminal_rerun(tmp_path: Path) -> None:
    """AC-FR0601-02: Retry is another synchronous read, never a background resume."""
    responses = _ready_responses(tmp_path)
    responses[("gh", "--version")] = CommandResult(None, timed_out=True)
    executor = RecordingExecutor(tmp_path, responses)
    service = EnvironmentService(tmp_path, executor=executor)

    first = service.check()
    executor.responses[("gh", "--version")] = CommandResult(0, "gh version 2.65.0\n")
    second = service.check()

    assert first["state"] == "uncertain"
    assert first["current_step"] == "gh_executable"
    assert first["steps"][0]["actions"] == ["Retry"]
    assert second["state"] == "passed"
    assert executor.calls.count(("gh", "--version")) == 2
