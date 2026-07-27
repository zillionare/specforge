"""Stateless aggregate readiness for Login and New Project."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Protocol

from starlette.concurrency import run_in_threadpool

from .environment_commands import CommandExecutor
from .environment_service import EnvironmentService
from . import opencode_probe
from ..models import resolve_model


class ModelChecker(Protocol):
    """Callable boundary for one selected-model availability probe."""

    def __call__(self, workspace_root: Path) -> opencode_probe.ModelCheckResult:
        """Return a fresh bounded model probe for ``workspace_root``."""


class LoginReadinessService:
    """Compose fresh OpenCode/model and GitHub/Git readiness facts."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        executor: CommandExecutor | None = None,
        model_checker: ModelChecker | None = None,
    ) -> None:
        """Bind a workspace and optional deterministic readiness seams."""
        self.workspace_root = Path(workspace_root).resolve()
        self.executor = executor
        self.model_checker = model_checker

    def check(self) -> dict[str, Any]:
        """Run fresh terminal checks without persisting readiness authority."""
        environment = EnvironmentService(
            self.workspace_root, executor=self.executor
        ).check()
        model = self._check_model()
        steps = [*environment["steps"], _model_step(model)]
        state = _aggregate_state(steps)
        return {
            "state": state,
            "current_step": next(
                (step["id"] for step in steps if step["state"] != "passed"), None
            ),
            "steps": steps,
            "story_input_enabled": state == "passed",
            "preview_enabled": state == "passed",
            "create_enabled": state == "passed",
            "model_check": _model_payload(model),
        }

    def _check_model(self) -> opencode_probe.ModelCheckResult:
        if self.model_checker is not None:
            try:
                return self.model_checker(self.workspace_root)
            except Exception:
                return _uncertain_model_result("the selected-model probe could not run")
        if self.executor is not None:
            return _uncertain_model_result(
                "no selected-model probe evidence was provided"
            )
        candidates = _selected_model_candidates(self.workspace_root)
        if not candidates:
            return _uncertain_model_result("no selected OpenCode model is configured")
        return opencode_probe.run_check(
            candidates=candidates,
            total_deadline_seconds=MODEL_PROBE_DEADLINE_SECONDS,
        )


def _selected_model_candidates(workspace_root: Path) -> list[str]:
    """Return unique configured concrete models before broad discovery."""
    path = workspace_root / ".louke" / "models.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict):
        return []
    values: set[str] = set()
    for group in (assignments.get("roles"), assignments.get("agents")):
        if not isinstance(group, dict):
            continue
        values.update(
            str(value).strip()
            for value in group.values()
            if isinstance(value, str) and value.strip()
        )
    return sorted(
        {
            resolve_model(
                value, root=workspace_root, models=[value], auth=set(), costs={}
            )
            for value in values
        }
    )


MODEL_PROBE_DEADLINE_SECONDS = 20
AGGREGATE_READINESS_TIMEOUT_SECONDS = 30


def _uncertain_model_result(known_facts: str) -> opencode_probe.ModelCheckResult:
    """Return non-authoritative model evidence when no probe can pass."""
    return opencode_probe.ModelCheckResult(
        check_id="",
        revision=1,
        state="uncertain",
        diagnosis={
            "object": "selected OpenCode model",
            "known_facts": known_facts,
            "impact": "New Project cannot verify a working model",
            "recovery_url": "/login",
        },
    )


def _model_step(result: opencode_probe.ModelCheckResult) -> dict[str, Any]:
    """Project a model probe into the common terminal readiness step shape."""
    state = "passed" if result.state == "passed" else result.state
    if state not in {"passed", "uncertain"}:
        state = "blocked"
    diagnosis = result.diagnosis
    if state != "passed" and diagnosis is None:
        diagnosis = {
            "object": "selected OpenCode model",
            "known_facts": "the selected model probe did not pass",
            "impact": "New Project cannot verify a working model",
            "recovery_url": "/login",
        }
    return {
        "id": "opencode_model",
        "state": state,
        "observed": {
            "model_id": result.current_model_id,
            "check_id": result.check_id,
        }
        if result.current_model_id or result.check_id
        else None,
        "missing": [] if state == "passed" else ["selected OpenCode model"],
        "diagnosis": diagnosis,
        "actions": [] if state == "passed" else ["Retry"],
    }


def _model_payload(result: opencode_probe.ModelCheckResult) -> dict[str, Any]:
    """Return a redacted model-check payload for the Login response."""
    return {
        "check_id": result.check_id,
        "revision": result.revision,
        "state": result.state,
        "current_model_id": result.current_model_id,
        "diagnosis": result.diagnosis,
        "observed_at": result.observed_at,
    }


def _aggregate_state(steps: list[dict[str, Any]]) -> str:
    """Return the terminal aggregate state, preserving uncertainty."""
    if any(step["state"] == "uncertain" for step in steps):
        return "uncertain"
    return "passed" if all(step["state"] == "passed" for step in steps) else "blocked"


def check_login_readiness(
    workspace_root: str | Path,
    *,
    executor: CommandExecutor | None = None,
    model_checker: ModelChecker | None = None,
) -> dict[str, Any]:
    """Return one fresh aggregate readiness projection for local Web callers."""
    return LoginReadinessService(
        workspace_root,
        executor=executor,
        model_checker=model_checker,
    ).check()


async def check_login_readiness_async(
    workspace_root: str | Path,
    *,
    executor: CommandExecutor | None = None,
    model_checker: ModelChecker | None = None,
) -> dict[str, Any]:
    """Run aggregate readiness off the event loop with a terminal deadline."""
    try:
        return await asyncio.wait_for(
            run_in_threadpool(
                check_login_readiness,
                workspace_root,
                executor=executor,
                model_checker=model_checker,
            ),
            timeout=AGGREGATE_READINESS_TIMEOUT_SECONDS,
        )
    except Exception:
        return _uncertain_readiness(
            "readiness checks did not complete before the deadline"
        )


def _uncertain_readiness(known_facts: str) -> dict[str, Any]:
    """Return a redacted terminal warning when aggregate probing cannot complete."""
    step = {
        "id": "aggregate_readiness",
        "state": "uncertain",
        "observed": None,
        "missing": ["current readiness evidence"],
        "diagnosis": {
            "object": "Login readiness",
            "known_facts": known_facts,
            "impact": "New Project remains unavailable until readiness can be verified",
            "recovery_url": "/login",
        },
        "actions": ["Retry"],
    }
    return {
        "state": "uncertain",
        "current_step": step["id"],
        "steps": [step],
        "story_input_enabled": False,
        "preview_enabled": False,
        "create_enabled": False,
        "model_check": None,
    }
