"""Read-only Git workspace and canonical main readiness checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .environment_commands import CommandExecutor


def check_repository(
    executor: CommandExecutor, workspace: Path
) -> list[dict[str, Any]]:
    """Return terminal repository and remote-main Environment steps."""
    worktree = executor.run(
        ("git", "rev-parse", "--is-inside-work-tree"), cwd=workspace, timeout=15
    )
    root = executor.run(
        ("git", "rev-parse", "--show-toplevel"), cwd=workspace, timeout=15
    )
    origin = executor.run(
        ("git", "remote", "get-url", "origin"), cwd=workspace, timeout=15
    )
    if any(item.timed_out for item in (worktree, root, origin)):
        return [
            _failure(
                "repository_binding", "uncertain", "Git repository read timed out."
            )
        ]
    repository = parse_github_origin(origin.stdout.strip())
    if (
        worktree.returncode != 0
        or worktree.stdout.strip().lower() != "true"
        or root.returncode != 0
        or Path(root.stdout.strip()).resolve() != workspace.resolve()
        or repository is None
    ):
        return [
            _failure(
                "repository_binding",
                "blocked",
                "This workspace needs a GitHub origin binding.",
            )
        ]
    local = executor.run(
        ("git", "rev-parse", "--verify", "refs/heads/main"), cwd=workspace, timeout=15
    )
    remote = executor.run(
        ("git", "ls-remote", "--heads", "origin", "main"), cwd=workspace, timeout=15
    )
    if local.timed_out or remote.timed_out:
        return [
            _passed("repository_binding", repository),
            _failure(
                "canonical_main", "uncertain", "Canonical main could not be read."
            ),
        ]
    local_sha, remote_sha = local.stdout.strip(), remote_sha_from(remote.stdout)
    if (
        local.returncode != 0
        or remote.returncode != 0
        or not valid_sha(local_sha)
        or local_sha != remote_sha
    ):
        return [
            _passed("repository_binding", repository),
            _failure("canonical_main", "blocked", "Local main must match origin/main."),
        ]
    return [
        _passed("repository_binding", repository),
        _passed("canonical_main", {"main_sha": local_sha}),
    ]


def parse_github_origin(value: str) -> dict[str, str] | None:
    """Parse a clean GitHub HTTPS or SSH origin identity."""
    match = re.match(
        r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$", value
    )
    if match is None:
        return None
    return {"host": "github.com", "owner": match.group(1), "name": match.group(2)}


def remote_sha_from(output: str) -> str | None:
    """Return the SHA from one ``git ls-remote`` line."""
    value = output.strip().split(None, 1)
    return value[0] if value and valid_sha(value[0]) else None


def valid_sha(value: str) -> bool:
    """Return whether ``value`` is a plausible Git revision."""
    return bool(re.fullmatch(r"[0-9a-fA-F]{7,64}", value))


def _passed(step_id: str, observed: dict[str, Any]) -> dict[str, Any]:
    """Return a passed Environment step."""
    return {
        "id": step_id,
        "state": "passed",
        "observed": observed,
        "missing": [],
        "diagnosis": None,
        "actions": [],
    }


def _failure(step_id: str, state: str, impact: str) -> dict[str, Any]:
    """Return a user-visible terminal repository failure."""
    return {
        "id": step_id,
        "state": state,
        "observed": None,
        "missing": [step_id],
        "diagnosis": {"object": step_id, "impact": impact},
        "actions": ["Retry"],
    }
