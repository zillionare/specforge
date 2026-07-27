"""lk serve - run the louke Web server with runtime selection.

Behavior:
- Resolve project root by walking up for `.louke/project/project.toml`.
- If project.toml is missing or its current_stage is unrecognized, auto-create a
  minimal project.toml before starting the Login/Workbench app.
- If everything is ready, resolve RuntimeSelector and fail-closed on any
  integrity/version/runtime error (never silently fall back to global).
- Always start uvicorn unless --dry-run is set (for tests).
"""

from __future__ import annotations

import argparse
import atexit
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .runtime.runtime_selector import (
    GlobalModeError,
    IntegrityError,
    InvalidRuntimeError,
    RuntimeMode,
    RuntimeSelector,
    VersionMismatchError,
)
from . import __version__

# Module-level seams so tests can patch without starting a real server.
# `uvicorn_run` is set lazily to the real uvicorn.run on first use; tests
# replace it with a no-op via monkeypatch.
uvicorn_run: Any = None


def create_app(
    project_root: str | Path | None = None,
    *,
    mode: str | None = None,
    allowed_origin: str | None = None,
):
    """Create the Starlette app through the Web composition root.

    This is a thin seam over louke.web.app.create_app so tests can patch it.
    """
    from .web.app import create_app as _create_app

    return _create_app(
        project_root,
        mode=mode,
        allowed_origin=allowed_origin,
    )


_VALID_STAGES = frozenset(
    {
        "M-FOUND",
        "M-SPEC",
        "M-TESTPLAN",
        "M-ARCH",
        "M-LOCK",
        "M-DEV",
        "M-E2E",
        "M-BUGFIX",
        "M-SECURITY",
        "M-MILESTONE",
    }
)

_MINIMAL_PROJECT_TOML = """\
[project]
version = "0.12"
repo = "github.com/zillionare/louke"
project = "louke-v0.12"
project_id = ""
spec_id = "v0.12-001-programmatic-workflow-runtime"
release_branch = "main"

[meta]
created = "{today}"
tag = "unreleased"
current_stage = "M-FOUND"
security_audit = "disabled"
smoke_test_issue = "to be created after M-LOCK"
smoke_test_pr = "to be created after M-LOCK"
pre_commit = "installed (python + base)"
test_framework = "pytest"
acknowledged_orphan_releases = []
"""


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--project-root",
        default="",
        help="louke project root (default: search from current directory upward)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve + dry-run; do not start uvicorn (for tests)",
    )
    parser.add_argument(
        "--opencode-backend",
        default="real",
        choices=["mock", "real"],
        help="OpenCode adapter kind; default real (use mock explicitly for tests)",
    )


def run(args: argparse.Namespace) -> int:
    root = _resolve_project_root(args.project_root)
    project_toml = root / ".louke" / "project" / "project.toml"
    print(f"lk serve: opencode backend = {args.opencode_backend}")

    if not project_toml.exists() or not _current_stage_valid(project_toml):
        created = _ensure_minimal_project_toml(project_toml)
        detail = (
            f"created minimal project.toml at {project_toml}"
            if created
            else f"{project_toml} has unrecognized current_stage"
        )
        print(f"lk serve: {detail}; starting Login/Workbench app")
        return _start_or_dry_run(args, root)

    return _serve_ready(args, root)


def _fail(message: str) -> int:
    print(f"lk serve: {message}", file=sys.stderr)
    return 1


def _serve_ready(args: argparse.Namespace, root: Path) -> int:
    # The mounted Web API resolves its adapter lazily from this environment
    # variable. Keep the CLI selection and the request-serving process on the
    # same backend; otherwise ``--opencode-backend real`` would start a real
    # child but the API would still silently resolve its mock default.
    os.environ["LOUKE_OPENCODE_BACKEND"] = args.opencode_backend
    project_python = _project_venv_python(root)
    using_project_venv = project_python is not None
    legacy_runtime = root / ".louke" / "runtime" / "lk"
    explicit_global = os.environ.get("LOUKE_RUNTIME_MODE", "").lower() == "global"
    runtime_mode = (
        RuntimeMode.LOCAL
        if using_project_venv or legacy_runtime.is_file() or not explicit_global
        else RuntimeMode.GLOBAL
    )
    local_version = __version__ if using_project_venv else "0.12.0"
    selector = RuntimeSelector(
        project_root=str(root),
        mode=runtime_mode,
        declared_version=local_version if runtime_mode == RuntimeMode.LOCAL else "",
        global_version=__version__ if runtime_mode == RuntimeMode.GLOBAL else "",
        local_present=_has_local_runtime(root)
        if runtime_mode == RuntimeMode.LOCAL
        else False,
        actual_version=local_version if runtime_mode == RuntimeMode.LOCAL else None,
        local_executable=str(project_python) if project_python else None,
    )
    try:
        identity = selector.resolve()
    except (
        IntegrityError,
        VersionMismatchError,
        InvalidRuntimeError,
        GlobalModeError,
    ) as exc:
        return _fail(
            f"runtime selection failed: {exc}. Inspect .louke/project/project.toml "
            f"(version/declared) and the local runtime under {root}/.venv. "
            "No global fallback."
        )
    except Exception as exc:
        return _fail(f"unexpected error resolving runtime: {exc}")

    if args.opencode_backend == "real":
        try:
            from .opencode.process import OpenCodeServerProcess
            from .opencode.dispatch import get_default_adapter
            from .opencode.persistence import OpenCodeInstanceStore

            if not os.environ.get("LOUKE_OPENCODE_BASE_URL"):
                proc = OpenCodeServerProcess(
                    host="127.0.0.1",
                    port=0,
                    opencode_bin="opencode",
                    cwd=root,
                )
                base_url = proc.start()
                os.environ["LOUKE_OPENCODE_BASE_URL"] = base_url
                os.environ["LOUKE_OPENCODE_OWNED_PID"] = str(proc.pid or 0)
                atexit.register(proc.stop)
            os.environ.setdefault("OPENCODE_DIRECTORY", str(root))
            os.environ.setdefault("LOUKE_OPENCODE_USE_SERVER_DEFAULT", "1")
            adapter = get_default_adapter(kind="real")
            store = OpenCodeInstanceStore(root)
            instances_file = root / ".louke" / "opencode" / "instances.json"
            if instances_file.exists():
                states = store.recovery_scan(adapter=adapter)
                live = sum(1 for s in states if s.status == "running")
                lost = [s for s in states if s.status == "lost"]
                needs_attention = [s for s in states if s.status == "needs_attention"]
                print(
                    f"lk serve: opencode recovery: live={live} lost={len(lost)} needs_attention={len(needs_attention)}"
                )
                for s in lost:
                    print(
                        f"  lost: instance={s.instance_id} (was at {s.base_url})",
                        file=sys.stderr,
                    )
                for s in needs_attention:
                    print(
                        f"  needs_attention: instance={s.instance_id} (pid alive, not in adapter)",
                        file=sys.stderr,
                    )
            else:
                print(
                    "lk serve: opencode backend=real; no persisted instances to recover"
                )
        except Exception as exc:
            return _fail(
                f"opencode backend 'real' setup failed: {exc}. Pass --opencode-backend=mock to use the deterministic stub. No global fallback."
            )
    else:
        print("lk serve: opencode backend=mock; skipping recovery scan")

    print(
        f'lk serve: runtime = {identity.mode.name}, mode={identity.mode.name.lower()}, version="{identity.version}"'
    )
    print(f"lk serve: effective root = {identity.effective_root}")
    print(f"lk serve: listening on http://{args.host}:{args.port}")
    if args.dry_run:
        _create_served_app(root)
        return 0
    return _run_uvicorn(args, root)


def _has_local_runtime(root: Path) -> bool:
    """Return whether ``root`` contains a v0.13 local runtime.

    v0.13 defines the project-local runtime as ``<CWD>/.venv``. The legacy
    ``.louke/runtime/lk`` check remains only for old v0.12 workspaces and
    tests; it is never searched in a parent directory.
    """
    return (
        _project_venv_python(root) is not None
        or (root / ".louke" / "runtime" / "lk").is_file()
    )


def _project_venv_python(root: Path) -> Path | None:
    """Return the project-local Python executable, without parent lookup."""
    candidates = (
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def _start_or_dry_run(args: argparse.Namespace, root: Path) -> int:
    if args.dry_run:
        _create_served_app(root)
        return 0
    return _run_uvicorn(args, root)


def _run_uvicorn(args: argparse.Namespace, root: Path) -> int:
    runner = uvicorn_run
    if runner is None:
        try:
            import uvicorn

            runner = uvicorn.run
        except ImportError as exc:
            print(
                f"lk serve: missing runtime dependency uvicorn ({exc})", file=sys.stderr
            )
            return 1
    app = _create_served_app(root)
    runner(app, host=args.host, port=args.port, log_level="info")
    return 0


def _runtime_mode_for_root(root: Path) -> str | None:
    """Return the explicitly selected Runtime mode for a served workspace."""
    from .runtime.release_contract import (
        DEVELOPMENT_BOOTSTRAP_MODE,
        is_louke_workspace,
    )

    if is_louke_workspace(root):
        return DEVELOPMENT_BOOTSTRAP_MODE
    return None


def _create_served_app(root: Path):
    """Create a served app with bootstrap mode only for Louke itself."""
    mode = _runtime_mode_for_root(root)
    if mode is None:
        return create_app(root)
    return create_app(root, mode=mode)


def _resolve_project_root(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    discovered = _find_project_root(Path.cwd())
    if discovered is not None:
        return discovered
    return Path.cwd().resolve()


def _find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        project_toml = candidate / ".louke" / "project" / "project.toml"
        if project_toml.exists():
            return candidate
    return None


def _current_stage_valid(project_toml: Path) -> bool:
    try:
        from ._common import _toml_load

        data = _toml_load(project_toml)
    except Exception:
        return False
    stage = str((data.get("meta") or {}).get("current_stage") or "")
    return stage in _VALID_STAGES


def _ensure_minimal_project_toml(project_toml: Path) -> bool:
    """Create a minimal v0.12 project.toml if it does not exist.

    Returns True if a new file was created, False if it already existed
    (but had an unrecognized current_stage).
    """
    if project_toml.exists():
        return False
    project_toml.parent.mkdir(parents=True, exist_ok=True)
    project_toml.write_text(
        _MINIMAL_PROJECT_TOML.format(today=date.today().isoformat()),
        encoding="utf-8",
    )
    return True
