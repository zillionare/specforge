"""AC-NFR0201-02 — actionable terminal Environment diagnostics."""

from __future__ import annotations

from pathlib import Path

from louke.web.environment_commands import CommandResult
from louke.web.environment_service import EnvironmentService


class FailingExecutor:
    """Controlled external command boundary for real terminal diagnostics."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result

    def run(self, argv: tuple[str, ...], *, cwd: Path, timeout: float) -> CommandResult:
        assert argv == ("gh", "--version")
        assert cwd.is_absolute() and 0 < timeout <= 15
        return self.result


def test_ac_nfr0201_02_blocked_environment_diagnosis_is_actionable_and_non_secret(
    tmp_path: Path,
) -> None:
    """AC-NFR0201-02: command failure yields a public repair action, not stderr."""
    secret = "SECRET_V014004_PROVIDER_TOKEN"
    result = EnvironmentService(
        tmp_path, executor=FailingExecutor(CommandResult(127, stderr=secret))
    ).check()

    step = result["steps"][0]
    assert result["state"] == "blocked"
    assert step["diagnosis"] == {
        "object": "gh_executable",
        "impact": "Install or expose gh, then retry.",
    }
    assert step["actions"] == ["Retry"]
    assert secret not in repr(result)


def test_ac_nfr0201_02_timeout_is_uncertain_with_retry_action(tmp_path: Path) -> None:
    """AC-NFR0201-02: timeout is a terminal uncertain diagnosis with Retry."""
    result = EnvironmentService(
        tmp_path, executor=FailingExecutor(CommandResult(None, timed_out=True))
    ).check()

    step = result["steps"][0]
    assert result["state"] == "uncertain"
    assert step["diagnosis"]["object"] == "gh_executable"
    assert step["diagnosis"]["impact"] == "GitHub CLI response timed out."
    assert step["actions"] == ["Retry"]
