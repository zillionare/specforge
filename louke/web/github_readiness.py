"""Pure GitHub CLI parsing and read-only readiness checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .environment_commands import CommandExecutor

REQUIRED_SCOPES = ("gist", "project", "repo", "workflow")


def check_github(executor: CommandExecutor, workspace: Path) -> list[dict[str, Any]]:
    """Return terminal CLI and auth Environment steps for ``workspace``."""
    executable = executor.run(("gh", "--version"), cwd=workspace, timeout=15)
    version = parse_version(executable.stdout)
    if executable.timed_out:
        return [
            _failure(
                "gh_executable",
                "uncertain",
                ["gh version"],
                "GitHub CLI response timed out.",
            )
        ]
    if executable.returncode != 0 or version is None:
        return [
            _failure(
                "gh_executable",
                "blocked",
                ["gh executable"],
                "Install or expose gh, then retry.",
            )
        ]
    auth = executor.run(("gh", "auth", "status"), cwd=workspace, timeout=15)
    if auth.timed_out:
        return [
            _passed("gh_executable", {"version": version}),
            _failure(
                "gh_auth_scopes",
                "uncertain",
                ["GitHub auth"],
                "GitHub auth response timed out.",
            ),
        ]
    facts = parse_auth_status(auth.stdout, auth.stderr)
    missing = sorted(set(REQUIRED_SCOPES) - facts["scopes"])
    if (
        auth.returncode != 0
        or facts["hosts"] != {"github.com"}
        or len(facts["identities"]) != 1
    ):
        missing = [*missing, "unique github.com identity"]
    if missing:
        return [
            _passed("gh_executable", {"version": version}),
            _failure(
                "gh_auth_scopes",
                "blocked",
                missing,
                "Authenticate gh with the required scopes, then retry.",
            ),
        ]
    return [
        _passed("gh_executable", {"version": version}),
        _passed(
            "gh_auth_scopes",
            {
                "host": "github.com",
                "identity": next(iter(facts["identities"])),
                "scopes": sorted(facts["scopes"]),
            },
        ),
    ]


def parse_version(output: str) -> str | None:
    """Extract a harmless version token from ``gh --version`` output."""
    match = re.search(r"\bgh\s+version\s+([^\s()]+)", output, re.I)
    return match.group(1) if match else None


def parse_auth_status(stdout: str, stderr: str) -> dict[str, set[str]]:
    """Parse real quoted scope output from either CLI output stream."""
    text = "\n".join(value for value in (stdout, stderr) if value)
    hosts = {"github.com"} if "github.com" in text.lower() else set()
    identities = set(
        re.findall(
            r"logged\s+in\s+to\s+github\.com\s+(?:account|as)\s+([A-Za-z0-9._-]+)",
            text,
            re.I,
        )
    )
    scopes: set[str] = set()
    for value in re.findall(r"token scopes?\s*:\s*([^\n]+)", text, re.I):
        scopes.update(
            token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9:_-]*", value)
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        scopes.update(
            str(value).lower()
            for value in payload.get("scopes", [])
            if isinstance(value, str)
        )
    return {"hosts": hosts, "identities": identities, "scopes": scopes}


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


def _failure(
    step_id: str, state: str, missing: list[str], impact: str
) -> dict[str, Any]:
    """Return a visible, actionable terminal Environment failure."""
    return {
        "id": step_id,
        "state": state,
        "observed": None,
        "missing": missing,
        "diagnosis": {"object": step_id, "impact": impact},
        "actions": ["Retry"],
    }
