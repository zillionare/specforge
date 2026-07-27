"""``/api/readiness`` Starlette sub-app: workspace readiness endpoint.

Exposes the v0.12 runtime :class:`~louke.runtime.workspace_init.InitWizard`
readiness report as a JSON HTTP API. The sub-app constructs a fresh
``InitWizard`` per request (it is cheap and stateless for readiness checks).

Endpoints:
    GET  /   - return the current readiness report.

Error envelope (shared across v0.12 sub-apps)::

    HTTPException(status_code=4xx/5xx,
                   detail={"error_code": "...", "message": "..."})
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from louke.runtime.workspace_init import (
    ReadinessCheck,
    ReadinessReport,
    ReadinessStatus,
)

from ._common import install_error_handlers
from ..login_readiness import check_login_readiness_async

_COMMAND_TIMEOUT_SECONDS = 5
_CREDENTIALS_RE = re.compile(r"\b(\d+)\s+credentials?\b")
_ENVIRONMENT_RE = re.compile(r"\b(\d+)\s+environment variables?\b")


def create_app(workspace_root: str | Path | None = None) -> Starlette:
    """Return a self-contained Starlette sub-app for ``/api/readiness``.

    Returns:
        A Starlette application whose routes are relative to ``/api/readiness``.
    """
    app = Starlette(routes=_routes())
    app.state.workspace_root = Path(workspace_root or ".").resolve()
    install_error_handlers(app)
    return app


def _routes() -> list[Route]:
    """Return the routes for the readiness sub-app."""
    return [Route("/", endpoint=get_readiness)]


def _build_report(workspace_root: Path) -> ReadinessReport:
    """Return the current workspace readiness report.

    Checks the workspace and its installed OpenCode CLI rather than reporting
    placeholder states. Provider credentials stay local: only their count is
    inspected and no credential values are returned. ``gh`` is verified as
    the Backlog/release-project namespace capability (interfaces.md IF-04
    dependency list).
    """
    opencode_bin = shutil.which("opencode")
    gh_bin = shutil.which("gh")
    return ReadinessReport(
        items=(
            _git_check(workspace_root),
            _store_check(workspace_root),
            _catalog_check(workspace_root),
            _opencode_check(opencode_bin),
            _models_check(opencode_bin, workspace_root),
            _namespace_capability_check(gh_bin),
        )
    )


def _git_check(workspace_root: Path) -> ReadinessCheck:
    """Report both local Git state and whether it is backed by a remote."""
    if not _command_succeeds(
        ["git", "-C", str(workspace_root), "rev-parse", "--git-dir"]
    ):
        return ReadinessCheck(
            name="Git",
            status=ReadinessStatus.BLOCKED,
            diagnosis="No Git repository at the workspace root",
            remediation="Initialize Git or select a repository workspace",
        )
    remotes = _run_command(
        ["git", "-C", str(workspace_root), "remote"]
    ).stdout.splitlines()
    if not remotes:
        return ReadinessCheck(
            name="Git",
            status=ReadinessStatus.DEGRADED,
            diagnosis="Local Git repository present; no remote is configured",
            remediation="Add the GitHub repository remote before publishing",
        )
    return ReadinessCheck(
        name="Git",
        status=ReadinessStatus.READY,
        diagnosis=f"Local Git repository with remote: {remotes[0]}",
        remediation="none",
    )


def _store_check(workspace_root: Path) -> ReadinessCheck:
    """Report whether the persisted Louke store can be accessed."""
    store_dir = workspace_root / ".louke" / "project"
    if store_dir.is_dir():
        return ReadinessCheck(
            "Store", ReadinessStatus.READY, "Runtime store readable", "none"
        )
    return ReadinessCheck(
        "Store", ReadinessStatus.BLOCKED, "Runtime store is missing", "Run lk init"
    )


def _catalog_check(workspace_root: Path) -> ReadinessCheck:
    """Report whether the project metadata used as the workflow catalog exists."""
    catalog = workspace_root / ".louke" / "project" / "project.toml"
    if catalog.is_file():
        return ReadinessCheck(
            "Catalog", ReadinessStatus.READY, "Workflow catalog readable", "none"
        )
    return ReadinessCheck(
        "Catalog", ReadinessStatus.BLOCKED, "Workflow catalog is missing", "Run lk init"
    )


def _opencode_check(opencode_bin: str | None) -> ReadinessCheck:
    """Report whether OpenCode is executable from this server process."""
    if opencode_bin and _command_succeeds([opencode_bin, "--version"]):
        return ReadinessCheck(
            "OpenCode",
            ReadinessStatus.READY,
            f"OpenCode available: {opencode_bin}",
            "none",
        )
    return ReadinessCheck(
        "OpenCode",
        ReadinessStatus.BLOCKED,
        "OpenCode binary is not executable from this server process",
        "Install OpenCode and ensure it is on the server PATH",
    )


def _models_check(opencode_bin: str | None, workspace_root: Path) -> ReadinessCheck:
    """Report whether OpenCode has credentials and can list models."""
    if not opencode_bin:
        return ReadinessCheck(
            "Models",
            ReadinessStatus.BLOCKED,
            "OpenCode is unavailable",
            "Install OpenCode first",
        )
    auth = _run_command([opencode_bin, "auth", "list"], cwd=workspace_root)
    credential_count = _configured_provider_count(auth.stdout)
    if auth.returncode or credential_count == 0:
        return ReadinessCheck(
            "Models",
            ReadinessStatus.BLOCKED,
            "No OpenCode provider credentials are configured",
            "Run opencode auth login or configure a provider environment variable",
        )
    models = _run_command([opencode_bin, "models"], cwd=workspace_root)
    if models.returncode:
        return ReadinessCheck(
            "Models",
            ReadinessStatus.BLOCKED,
            "OpenCode could not list models",
            "Verify provider authentication and network access",
        )
    return ReadinessCheck(
        "Models",
        ReadinessStatus.READY,
        f"OpenCode model catalog available; {credential_count} provider configuration(s)",
        "none",
    )


def _namespace_capability_check(gh_bin: str | None) -> ReadinessCheck:
    """Report whether the Backlog/release-project namespace capability is available.

    Per spec FR-0501-01 the wizard must verify ``Backlog/release-project
    namespace or creation capability``. The conventional local surface for
    this capability is the GitHub CLI (``gh``); if it is missing, the
    user cannot create or mutate the Backlog Project, release projects, or
    release issues until they install it.
    """
    install_link = (
        "Install the GitHub CLI for your platform and "
        "authenticate with `gh auth login`. "
        "See https://docs.github.com/en/github-cli/github-cli/quickstart"
    )
    if gh_bin is None:
        return ReadinessCheck(
            "namespace_capability",
            ReadinessStatus.BLOCKED,
            "gh CLI is not installed on PATH",
            install_link,
        )
    version = _run_command([gh_bin, "--version"])
    if version.returncode != 0:
        return ReadinessCheck(
            "namespace_capability",
            ReadinessStatus.BLOCKED,
            "gh CLI is installed but not executable",
            f"Verify that {gh_bin} runs `gh --version` without error. "
            f"See {install_link.split(' See ')[1]}",
        )
    auth = _run_command([gh_bin, "auth", "status"])
    if auth.returncode != 0:
        return ReadinessCheck(
            "namespace_capability",
            ReadinessStatus.BLOCKED,
            "gh CLI is not authenticated against a GitHub host",
            "Run `gh auth login` and verify `gh auth status` succeeds. "
            f"See {install_link.split(' See ')[1]}",
        )
    return ReadinessCheck(
        "namespace_capability",
        ReadinessStatus.READY,
        f"gh CLI available: {gh_bin}",
        "none",
    )


def _configured_provider_count(output: str) -> int:
    """Return the non-secret credential and environment-provider count."""
    credentials = _CREDENTIALS_RE.search(output)
    environment = _ENVIRONMENT_RE.search(output)
    return sum(int(match.group(1)) for match in (credentials, environment) if match)


def _run_command(
    args: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a fixed diagnostic command without a shell or inherited input."""
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            input="",
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")


def _command_succeeds(args: list[str]) -> bool:
    """Return whether a fixed diagnostic command completes successfully."""
    return _run_command(args).returncode == 0


async def get_readiness(request: Request) -> JSONResponse:
    """AC-FR1801-04: return the current workspace readiness report.

    Returns:
        ``200`` with ``{"items": [ReadinessCheck, ...]}``.
    """
    report = _build_report(request.app.state.workspace_root)
    return JSONResponse({"items": [_check_to_dict(c) for c in report.items]})


async def get_login_readiness(request: Request) -> JSONResponse:
    """Return fresh aggregate OpenCode and GitHub/Git readiness for Login."""
    result = await check_login_readiness_async(
        request.app.state.workspace_root,
        executor=getattr(request.app.state, "environment_executor", None),
        model_checker=getattr(request.app.state, "readiness_model_checker", None),
    )
    return JSONResponse(result)


def _check_to_dict(check: ReadinessCheck) -> dict[str, str]:
    """Return a JSON-serialisable dict for a ``ReadinessCheck``.

    The ``status`` enum is rendered as its name (``READY``/``DEGRADED``/``BLOCKED``)
    so the HTTP response is plain JSON.
    """
    return {
        "name": check.name,
        "status": check.status.name,
        "diagnosis": check.diagnosis,
        "remediation": check.remediation,
    }
