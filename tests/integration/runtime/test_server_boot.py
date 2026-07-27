"""S7 (#180): installed-wheel ``lk serve`` boot smoke.

gap-analysis §4 Batch 5 / §3 P0-3: prove that a clean venv which installed
the built wheel can actually boot ``lk serve`` and serve ``/health``. The
source tree masks packaging bugs because Python sees files on disk; a clean
wheel install has no such fallback, so a missing runtime dependency or a
broken console script fails here regardless of how the source tree looks.

Scope:
- Build the wheel, install it in a throwaway venv.
- Spawn ``lk serve --host 127.0.0.1 --port <free> --project-root <tmp>`` as
  a background subprocess.
- Poll ``/health`` until it returns 200 or the ready timeout is exceeded.
- Assert the health payload and the setup-only redirect.
- Kill the server and wait for it even if an assertion fails (try/finally).

The server is always started in setup-only mode because the temp project
root has no ``.louke/project/project.toml`` and no first principal; this is
the same boot path a fresh user sees, and the path the gap-analysis §3 P0-1
exit condition mandates for the v0.12.1 release gate.
"""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest


def free_port() -> int:
    """Bind a transient socket to discover a free TCP port for the server.

    Closes the socket before returning so ``lk serve`` can rebind. There is
    a small TOCTOU window between close and rebind, but it is acceptable for
    a hermetic integration smoke; the alternative (binding port 0 and
    reading uvicorn's chosen port from stdout) is far more fragile.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def wait_for_health(base_url: str, *, timeout: float = 30.0) -> dict:
    """Poll ``{base_url}/health`` until it returns 200 or ``timeout`` passes.

    Args:
        base_url: The server base URL (e.g. ``http://127.0.0.1:PORT``).
        timeout: Maximum seconds to wait for readiness.

    Returns:
        The parsed JSON health payload on success.

    Raises:
        TimeoutError: If ``/health`` does not return 200 within ``timeout``.
    """
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(
        f"/health did not return 200 within {timeout}s at {base_url} "
        f"(last error: {last_error!r})"
    )


def get_status(
    base_url: str, path: str, *, timeout: float = 5.0
) -> tuple[int, str | None]:
    """Issue a GET and return ``(status_code, location_header_or_None)``.

    Uses :mod:`http.client` directly so redirects are NOT followed; the
    caller asserts on the 303 target. ``urllib``'s opener-based redirect
    suppression is more convoluted and error-prone than a raw HTTP call
    for this single-purpose probe.

    Args:
        base_url: The server base URL (e.g. ``http://127.0.0.1:PORT``).
        path: The request path (e.g. ``/``).
        timeout: Per-request timeout in seconds.

    Returns:
        A ``(status_code, location)`` tuple where ``location`` is the value
        of the ``Location`` response header, or ``None`` if absent.
    """
    parsed = urlparse(base_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        location = resp.getheader("Location")
        resp.read()  # drain so the connection can be reused/closed cleanly
        return resp.status, location
    finally:
        conn.close()


class _ServerProcess:
    """Context manager wrapping a background ``lk serve`` subprocess.

    Guarantees the process is terminated on exit even when assertions fail.
    Uses SIGTERM first, then SIGKILL if the process does not exit within a
    short grace period, and always waits to reap the zombie.
    """

    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc

    def terminate(self, *, grace_seconds: float = 5.0) -> int:
        """Terminate the server, escalating SIGTERM -> SIGKILL if needed.

        Args:
            grace_seconds: Seconds to wait after SIGTERM before SIGKILL.

        Returns:
            The process exit code after termination.
        """
        if self._proc.poll() is not None:
            return self._proc.returncode
        self._proc.send_signal(signal.SIGTERM)
        try:
            self._proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=grace_seconds)
        return self._proc.returncode


def start_lk_serve(*, venv_dir: Path, port: int, project_root: Path) -> _ServerProcess:
    """Spawn ``lk serve`` in the given venv as a background subprocess.

    Args:
        venv_dir: The clean venv directory (must contain ``bin/lk``).
        port: The TCP port to bind.
        project_root: A throwaway directory used as the louke project root;
            the server will auto-create a minimal project.toml here and
            enter setup-only mode.

    Returns:
        A :class:`_ServerProcess` wrapping the spawned subprocess.
    """
    lk_bin = venv_dir / "bin" / "lk"
    env = _venv_env(venv_dir)
    proc = subprocess.Popen(
        [
            str(lk_bin),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--project-root",
            str(project_root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return _ServerProcess(proc)


def _venv_env(venv_dir: Path) -> dict[str, str]:
    """Return an env that isolates PATH to the given venv's binaries.

    Starts from :func:`subprocess_env` so the venv python can resolve
    ``libpythonX.Y.dylib`` via ``DYLD_LIBRARY_PATH`` on macOS standalone
    CPython builds (uv-managed interpreters). The ``lk`` console script
    invokes the venv python, so without the dylib path the spawned server
    SIGABRTs before binding its port. ``PYTHONPATH`` is stripped so the
    spawned ``lk`` cannot accidentally import from the source tree; the
    installed wheel is the only source of ``louke``.
    """
    from tests.integration.runtime.conftest import subprocess_env

    env = subprocess_env()
    venv_bin = str(venv_dir / "bin")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONPATH", None)
    return env


@pytest.fixture()
def running_lk_serve(built_wheel: Path, clean_venv: tuple[Path, Path], tmp_path: Path):
    """Start ``lk serve`` from a clean wheel install; yield ``(base_url, proc)``.

    Builds the wheel, installs it in a clean venv, spawns ``lk serve`` in
    setup-only mode on a free port, waits for ``/health`` to go green, and
    yields the base URL. On teardown the server is always terminated and
    reaped, even if the test body raised.
    """
    from tests.integration.runtime.conftest import install_wheel

    venv_dir, venv_python = clean_venv
    install_wheel(venv_python, built_wheel)

    port = free_port()
    project_root = tmp_path / "project_root"
    project_root.mkdir(parents=True, exist_ok=True)

    server = start_lk_serve(venv_dir=venv_dir, port=port, project_root=project_root)
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_for_health(base_url)
        yield base_url, server
    finally:
        server.terminate()


class TestInstalledLkServeBoot:
    """S7 (#180): the installed wheel's ``lk serve`` boots and serves HTTP."""

    def test_installed_lk_serve_starts_and_health_200(self, running_lk_serve) -> None:
        """``/health`` returns 200 from a clean-wheel ``lk serve`` boot.

        This is the gap-analysis §3 P0-1 exit condition: the installed
        wheel must actually start a server, not just install files. A
        missing runtime dependency (uvicorn, starlette) or a broken
        console-script entry point fails here.
        """
        base_url, _server = running_lk_serve
        payload = wait_for_health(base_url, timeout=5.0)
        assert payload.get("status") == "ok", (
            f"/health payload missing status=ok: {payload!r}"
        )

    def test_installed_lk_serve_health_has_spec_id(self, running_lk_serve) -> None:
        """``/health`` payload carries the v0.12 spec id.

        Proves the server is serving the real louke app (not a stub) and
        that the installed package's project store resolved its spec id.
        """
        base_url, _server = running_lk_serve
        payload = wait_for_health(base_url, timeout=5.0)
        assert "spec_id" in payload, (
            f"/health payload missing spec_id field: {payload!r}"
        )
        assert payload["spec_id"], "spec_id must be a non-empty string"

    def test_installed_lk_serve_unauthenticated_root_redirects_to_login(
        self, running_lk_serve
    ) -> None:
        """GET ``/`` on a fresh install returns the public Login entry."""
        base_url, _server = running_lk_serve
        status, location = get_status(base_url, "/")
        assert status == 303, (
            f"expected 303 redirect from unauthenticated /, got {status}; "
            f"location={location!r}"
        )
        assert location == "/login?next=/", (
            "expected unauthenticated / to redirect exactly to the public "
            f"Login entry '/login?next=/', got location={location!r}"
        )
