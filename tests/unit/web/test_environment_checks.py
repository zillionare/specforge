"""Unit evidence for terminal, read-only New Project Environment readiness."""

from __future__ import annotations

from pathlib import Path

from louke.web.environment_commands import CommandResult
from louke.web.environment_service import CANONICAL_STEPS, EnvironmentService


class RecordingExecutor:
    """Return fixed command results while retaining the executed argv calls."""

    def __init__(self, responses: dict[tuple[str, ...], CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        """Record one bounded command and return its configured transcript."""
        del cwd, timeout
        command = tuple(argv)
        self.calls.append(command)
        return self.responses.get(
            command, CommandResult(127, stderr="unsupported command")
        )


def _passing_responses(root: Path) -> dict[tuple[str, ...], CommandResult]:
    """Build the minimum read-only GitHub and Git transcript for readiness."""
    sha = "a" * 40
    return {
        ("gh", "--version"): CommandResult(0, "gh version 2.50.0\n"),
        ("gh", "auth", "status"): CommandResult(
            0,
            "Logged in to github.com account alice\n"
            "Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'\n",
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


def test_environment_check_returns_one_passed_terminal_projection(
    tmp_path: Path,
) -> None:
    """A verified local GitHub workspace enables Story, Preview, and Create."""
    executor = RecordingExecutor(_passing_responses(tmp_path))

    result = EnvironmentService(tmp_path, executor=executor).check()

    assert result["state"] == "passed"
    assert result["current_step"] is None
    assert result["story_input_enabled"] is True
    assert result["preview_enabled"] is True
    assert result["create_enabled"] is True
    assert [step["id"] for step in result["steps"]] == list(CANONICAL_STEPS)
    assert executor.calls == [
        ("gh", "--version"),
        ("gh", "auth", "status"),
        ("git", "rev-parse", "--is-inside-work-tree"),
        ("git", "rev-parse", "--show-toplevel"),
        ("git", "remote", "get-url", "origin"),
        ("git", "rev-parse", "--verify", "refs/heads/main"),
        ("git", "ls-remote", "--heads", "origin", "main"),
    ]


def test_environment_check_blocks_before_repository_reads_for_missing_scope(
    tmp_path: Path,
) -> None:
    """An incomplete GitHub token blocks the terminal projection without Git mutation."""
    responses = _passing_responses(tmp_path)
    responses[("gh", "auth", "status")] = CommandResult(
        0,
        "Logged in to github.com account alice\n"
        "Token scopes: 'gist', 'project', 'repo'\n",
    )
    executor = RecordingExecutor(responses)

    result = EnvironmentService(tmp_path, executor=executor).check()

    assert result["state"] == "blocked"
    assert result["current_step"] == "gh_auth_scopes"
    assert result["create_enabled"] is False
    assert "workflow" in result["steps"][1]["missing"]
    assert result["steps"][1]["diagnosis"]["impact"]
    assert result["steps"][1]["actions"] == ["Retry"]
    assert executor.calls == [("gh", "--version"), ("gh", "auth", "status")]


def test_environment_retry_is_a_fresh_terminal_rerun_after_uncertainty(
    tmp_path: Path,
) -> None:
    """AC-FR0601-02: Retry reruns readiness after an uncertain terminal result."""
    responses = _passing_responses(tmp_path)
    responses[("gh", "--version")] = CommandResult(None, timed_out=True)
    executor = RecordingExecutor(responses)
    service = EnvironmentService(tmp_path, executor=executor)

    uncertain = service.check()
    executor.responses[("gh", "--version")] = CommandResult(0, "gh version 2.50.0\n")
    retried = service.check()

    assert uncertain["state"] == "uncertain"
    assert uncertain["current_step"] == "gh_executable"
    assert uncertain["steps"][0]["diagnosis"]["impact"]
    assert uncertain["steps"][0]["actions"] == ["Retry"]
    assert retried["state"] == "passed"
    assert len(executor.calls) == 8
