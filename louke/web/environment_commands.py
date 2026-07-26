"""Bounded command execution for local Environment readiness checks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one bounded argv command.

    Attributes:
        returncode: Process exit status, or ``None`` when timed out.
        stdout: Captured standard output used for protocol parsing.
        stderr: Captured standard error used only for protocol parsing.
        timed_out: Whether the command exceeded its timeout.
    """

    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class CommandExecutor(Protocol):
    """Port for a shell-free bounded command call."""

    def run(self, argv: Sequence[str], *, cwd: Path, timeout: float) -> CommandResult:
        """Run ``argv`` from ``cwd`` without using a shell."""


class SubprocessCommandExecutor:
    """Production adapter for bounded local subprocess calls."""

    def run(self, argv: Sequence[str], *, cwd: Path, timeout: float) -> CommandResult:
        """Execute ``argv`` and convert expected process failures to facts."""
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(timeout, 0.01),
                check=False,
            )
        except OSError as exc:
            return CommandResult(
                127, stderr=f"command unavailable: {exc.strerror or exc}"
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                None,
                _as_text(exc.stdout),
                _as_text(exc.stderr),
                timed_out=True,
            )
        return CommandResult(
            completed.returncode, completed.stdout or "", completed.stderr or ""
        )


def _as_text(value: str | bytes | None) -> str:
    """Convert timeout output to text for internal parsing."""
    return (
        value.decode("utf-8", errors="replace")
        if isinstance(value, bytes)
        else value or ""
    )
