"""Synchronous composition of the local Environment readiness checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .environment_commands import CommandExecutor, SubprocessCommandExecutor
from .github_readiness import check_github
from .repository_readiness import check_repository

CANONICAL_STEPS = (
    "gh_executable",
    "gh_auth_scopes",
    "repository_binding",
    "canonical_main",
)


class EnvironmentService:
    """Run read-only local readiness checks for New Project."""

    def __init__(
        self, workspace_root: str | Path, *, executor: CommandExecutor | None = None
    ) -> None:
        """Bind a workspace and optional test command executor."""
        self.workspace_root = Path(workspace_root).resolve()
        self.executor = executor or SubprocessCommandExecutor()

    def check(self) -> dict[str, Any]:
        """Run all readiness reads and return one terminal projection.

        Returns:
            A terminal ``passed``, ``blocked`` or ``uncertain`` Environment
            projection. This method never changes Git or GitHub state.
        """
        steps = check_github(self.executor, self.workspace_root)
        if all(step["state"] == "passed" for step in steps):
            steps.extend(check_repository(self.executor, self.workspace_root))
        steps = _complete_steps(steps)
        state = _state(steps)
        return {
            "state": state,
            "current_step": next(
                (step["id"] for step in steps if step["state"] != "passed"), None
            ),
            "steps": steps,
            "story_input_enabled": state == "passed",
            "preview_enabled": state == "passed",
            "create_enabled": state == "passed",
        }


def _complete_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill unexecuted trailing steps as blocked without inventing authority."""
    known = {step["id"] for step in steps}
    return [
        *steps,
        *[
            {
                "id": step_id,
                "state": "blocked",
                "observed": None,
                "missing": ["previous readiness step"],
                "diagnosis": {
                    "object": step_id,
                    "impact": "Resolve the earlier readiness failure, then retry.",
                },
                "actions": ["Retry"],
            }
            for step_id in CANONICAL_STEPS
            if step_id not in known
        ],
    ]


def _state(steps: list[dict[str, Any]]) -> str:
    """Return the terminal aggregate state for ordered steps."""
    if any(step["state"] == "uncertain" for step in steps):
        return "uncertain"
    return "passed" if all(step["state"] == "passed" for step in steps) else "blocked"
