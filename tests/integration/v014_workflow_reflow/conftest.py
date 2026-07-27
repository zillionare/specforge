"""Shared pytest configuration for v0.14-001 entry-slice integration tests.

Starts the installed ``lk serve`` as a subprocess against an isolated
workspace with a bare Git remote, stand-in ``gh`` and stand-in OpenCode
HTTP server.  No internal Python calls, direct SQLite writes, or service
construction are used; all progression goes through public HTTP endpoints.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Generator, Iterator
from typing import BinaryIO, Callable

import pytest

from tests.fixtures.v014_workflow_reflow.harness import (
    IsolatedWorkspace,
    OpenCodeStandIn,
    build_isolated_workspace,
    server_command,
    start_opencode_standin,
    wait_for_health,
)


_MAX_SERVER_LOG_BYTES = 64 * 1024
_SERVER_LOG_TAIL_LINES = 40


def _pump_bounded_log(source: BinaryIO, path: Path) -> None:
    """Drain a process stream and retain only its last bounded bytes on disk."""
    path.touch()
    with path.open("r+b") as destination:
        while chunk := source.read(8192):
            destination.seek(0, os.SEEK_END)
            destination.write(chunk)
            if destination.tell() > _MAX_SERVER_LOG_BYTES:
                destination.seek(-_MAX_SERVER_LOG_BYTES, os.SEEK_END)
                retained = destination.read(_MAX_SERVER_LOG_BYTES)
                destination.seek(0)
                destination.truncate()
                destination.write(retained)
            destination.flush()


@dataclass
class _ServerLogs:
    """Bounded file-backed stdout/stderr capture for one ``lk serve`` process."""

    stdout_path: Path
    stderr_path: Path
    pumps: tuple[threading.Thread, threading.Thread]

    def close(self) -> None:
        """Join stream pumps after the child has stopped."""
        for pump in self.pumps:
            pump.join(timeout=5)

    def tail(self) -> str:
        """Return the last bounded lines from both server streams."""
        chunks: list[str] = []
        for label, path in (("stdout", self.stdout_path), ("stderr", self.stderr_path)):
            text = (
                path.read_text(encoding="utf-8", errors="replace")
                if path.exists()
                else ""
            )
            lines = text.splitlines()[-_SERVER_LOG_TAIL_LINES:]
            chunks.append(f"[{label}]\n" + ("\n".join(lines) or "<empty>"))
        return "\n".join(chunks)


def _start_server_logs(process: subprocess.Popen[bytes], tmp_path: Path) -> _ServerLogs:
    """Start bounded file-backed drains for a process opened with pipe streams."""
    if process.stdout is None or process.stderr is None:
        raise RuntimeError(
            "lk serve subprocess must be started with stdout=subprocess.PIPE and "
            "stderr=subprocess.PIPE so server logs can be captured; got "
            f"stdout={process.stdout!r}, stderr={process.stderr!r}"
        )
    stdout_stream: BinaryIO = process.stdout
    stderr_stream: BinaryIO = process.stderr
    stdout_path = tmp_path / "lk-serve.stdout.log"
    stderr_path = tmp_path / "lk-serve.stderr.log"
    stdout_pump = threading.Thread(
        target=_pump_bounded_log, args=(stdout_stream, stdout_path), daemon=True
    )
    stderr_pump = threading.Thread(
        target=_pump_bounded_log, args=(stderr_stream, stderr_path), daemon=True
    )
    stdout_pump.start()
    stderr_pump.start()
    return _ServerLogs(stdout_path, stderr_path, (stdout_pump, stderr_pump))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "v014_entry: v0.14-001 public-entry-slice integration test",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/integration/v014_workflow_reflow" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.v014_entry)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _launch_server(
    tmp_path, mode: str = "default"
) -> tuple[
    str,
    IsolatedWorkspace,
    OpenCodeStandIn,
    subprocess.Popen[bytes],
    _ServerLogs,
    dict[str, str],
]:
    """Build workspace, start OpenCode stand-in and lk serve subprocesses."""
    workspace = build_isolated_workspace(tmp_path)
    opencode = start_opencode_standin(tmp_path, mode=mode)

    orig_path = os.environ.get("PATH", "")
    orig_runtime_mode = os.environ.get("LOUKE_RUNTIME_MODE", "")
    gh_dir = str(workspace.gh_bin.parent)
    os.environ["PATH"] = os.pathsep.join([gh_dir, orig_path] if orig_path else [gh_dir])
    os.environ["LOUKE_GH_OWNER"] = "zillionare"
    os.environ["LOUKE_OPENCODE_BASE_URL"] = opencode.base_url
    os.environ["LOUKE_OPENCODE_BACKEND"] = "real"
    os.environ["LOUKE_OPENCODE_USE_SERVER_DEFAULT"] = "1"
    # This synthetic host has no project-local runtime. Select the installed
    # test runner explicitly rather than relying on a removed implicit fallback.
    os.environ["LOUKE_RUNTIME_MODE"] = "global"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    python = os.environ.get("LOUKE_E2E_SERVER_PYTHON", sys.executable)
    cmd = server_command(python, str(workspace.root), port=port)
    server_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    logs = _start_server_logs(server_proc, tmp_path)
    orig_env = {
        "PATH": orig_path,
        "LOUKE_RUNTIME_MODE": orig_runtime_mode,
    }
    return base_url, workspace, opencode, server_proc, logs, orig_env


def _teardown(
    server_proc: subprocess.Popen[bytes],
    opencode: OpenCodeStandIn,
    workspace: IsolatedWorkspace,
    logs: _ServerLogs,
    orig_env: dict[str, str],
) -> None:
    unexpected_exit = server_proc.poll()
    terminated_by_fixture = False
    if unexpected_exit is None:
        try:
            server_proc.terminate()
            terminated_by_fixture = True
        except ProcessLookupError:
            # The process exited in the narrow poll/terminate race. Treat it
            # as an unexpected exit after closing the bounded log pumps.
            pass
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=5)
    logs.close()
    opencode.stop()
    os.environ["PATH"] = orig_env.get("PATH", "")
    os.environ.pop("LOUKE_GH_OWNER", None)
    os.environ.pop("LOUKE_OPENCODE_BASE_URL", None)
    os.environ.pop("LOUKE_OPENCODE_BACKEND", None)
    os.environ.pop("LOUKE_OPENCODE_USE_SERVER_DEFAULT", None)
    if orig_env.get("LOUKE_RUNTIME_MODE"):
        os.environ["LOUKE_RUNTIME_MODE"] = orig_env["LOUKE_RUNTIME_MODE"]
    else:
        os.environ.pop("LOUKE_RUNTIME_MODE", None)
    workspace.cleanup()
    if workspace.bare_remote.exists():
        shutil.rmtree(workspace.bare_remote, ignore_errors=True)
    if unexpected_exit is not None or not terminated_by_fixture:
        raise RuntimeError(
            f"lk serve exited unexpectedly with code {server_proc.returncode}; "
            f"server log tail:\n{logs.tail()}"
        )


@pytest.fixture
def live_server(tmp_path) -> Iterator[tuple[str, IsolatedWorkspace, OpenCodeStandIn]]:
    """Start ``lk serve`` with the default OpenCode stand-in (valid Go result).

    Yields ``(base_url, workspace, opencode_stand_in)``.
    """
    base_url, workspace, opencode, proc, logs, orig_env = _launch_server(
        tmp_path, "default"
    )
    try:
        wait_for_health(base_url, timeout=30, process=proc, log_tail=logs.tail)
        yield base_url, workspace, opencode
    finally:
        _teardown(proc, opencode, workspace, logs, orig_env)


@pytest.fixture
def live_server_factory(
    tmp_path,
) -> Generator[
    Callable[[str], tuple[str, IsolatedWorkspace, OpenCodeStandIn]], None, None
]:
    """Return a factory that starts ``lk serve`` with a given stand-in mode.

    Usage::

        def test_malformed(live_server_factory):
            base_url, workspace, oc = live_server_factory("malformed")
            ...

    The caller is responsible for cleanup via the returned context.
    """
    created: list[
        tuple[
            subprocess.Popen[bytes],
            OpenCodeStandIn,
            IsolatedWorkspace,
            _ServerLogs,
            dict,
        ]
    ] = []

    def _make(mode: str = "default") -> tuple[str, IsolatedWorkspace, OpenCodeStandIn]:
        base_url, workspace, opencode, proc, logs, orig_env = _launch_server(
            tmp_path, mode
        )
        created.append((proc, opencode, workspace, logs, orig_env))
        wait_for_health(base_url, timeout=30, process=proc, log_tail=logs.tail)
        return base_url, workspace, opencode

    yield _make

    for proc, opencode, workspace, logs, orig_env in created:
        _teardown(proc, opencode, workspace, logs, orig_env)
