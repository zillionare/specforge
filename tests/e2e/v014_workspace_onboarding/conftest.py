"""Shared pytest configuration for v0.14-004 workspace-onboarding e2e tests.

These tests run against an installed wheel + live Web server (``lk serve``)
through a real Chromium browser, per test-plan §2.1 e2e layer.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.v014_workflow_reflow.harness import (
    build_isolated_workspace,
    server_command,
    start_opencode_standin,
    wait_for_health,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "v014_004_e2e: v0.14-004 workspace-onboarding end-to-end test",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if "tests/e2e/v014_workspace_onboarding" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.chromium_e2e)
            item.add_marker(pytest.mark.v014_004_e2e)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


@pytest.fixture
def live_server(tmp_path: Path):
    """Start ``lk serve`` from the product interpreter and OpenCode stand-in."""
    product_python = os.environ.get("LOUKE_E2E_SERVER_PYTHON", sys.executable)
    workspace = build_isolated_workspace(tmp_path)
    opencode = start_opencode_standin(tmp_path)

    orig_path = os.environ.get("PATH", "")
    gh_dir = str(workspace.gh_bin.parent)
    os.environ["PATH"] = os.pathsep.join([gh_dir, orig_path] if orig_path else [gh_dir])
    os.environ["LOUKE_GH_LEDGER_PATH"] = str(workspace.gh_ledger)
    os.environ["LOUKE_GH_OWNER"] = "zillionare"
    os.environ["LOUKE_OPENCODE_BASE_URL"] = opencode.base_url
    os.environ["LOUKE_OPENCODE_BACKEND"] = "real"
    os.environ["LOUKE_OPENCODE_USE_SERVER_DEFAULT"] = "1"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    cmd = server_command(product_python, str(workspace.root), port=port)
    server_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )

    try:
        wait_for_health(base_url, timeout=30)
        yield base_url, workspace, opencode
    finally:
        if server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait(timeout=5)
        opencode.stop()
        os.environ["PATH"] = orig_path
        os.environ.pop("LOUKE_GH_LEDGER_PATH", None)
        os.environ.pop("LOUKE_GH_OWNER", None)
        os.environ.pop("LOUKE_OPENCODE_BASE_URL", None)
        os.environ.pop("LOUKE_OPENCODE_BACKEND", None)
        os.environ.pop("LOUKE_OPENCODE_USE_SERVER_DEFAULT", None)
        workspace.cleanup()
        import shutil

        if workspace.bare_remote.exists():
            shutil.rmtree(workspace.bare_remote, ignore_errors=True)


@pytest.fixture
def browser_page(live_server):
    """Return a Playwright Chromium page bound to the live server."""
    if not _chromium_available():
        pytest.skip(
            "Chromium or Playwright is not installed; "
            "run: python -m playwright install chromium (AC-NFR0301-01)"
        )
    from playwright.sync_api import sync_playwright

    base_url = live_server[0]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(15000)
        yield page, base_url
        browser.close()
