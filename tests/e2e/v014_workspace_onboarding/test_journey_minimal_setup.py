"""E2E journeys for the public Login readiness and Register entry.

AC-FR0201-01, AC-FR0201-02, AC-FR0301-01, AC-FR0401-01

The Login page owns explicit registration and runs the real OpenCode CLI
probe plus GitHub/Git readiness.  Only the external ``gh`` and ``opencode``
process boundaries are controlled by the fixture; Login/Register and the
readiness projection remain the product surface under test.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path


def _seed_model_config(workspace: Path) -> None:
    """Give the real Login model probe one configured concrete candidate."""
    path = workspace / ".louke" / "models.json"
    path.write_text(
        json.dumps(
            {
                "$schema": "louke://models-config",
                "version": 1,
                "aliases": {"minimax-m3": "ark/minimax-m3"},
                "assignments": {"roles": {"A": "minimax-m3"}, "agents": {}},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _block_gh_auth(workspace: Path) -> str:
    """Make only the external gh auth boundary fail, preserving gh version."""
    original = workspace.gh_bin.read_text(encoding="utf-8")
    workspace.gh_bin.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        '  printf "%s\\n" "gh version 2.89.0 (stand-in)"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "auth" ] && [ "$2" = "status" ]; then\n'
        '  printf "%s\\n" "github.com"\n'
        '  printf "%s\\n" "authentication unavailable"\n'
        "  exit 1\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    workspace.gh_bin.chmod(workspace.gh_bin.stat().st_mode | stat.S_IEXEC)
    return original


def _restore_gh_auth(workspace: Path, original: str) -> None:
    """Restore the fixture's successful external gh stand-in."""
    workspace.gh_bin.write_text(original, encoding="utf-8")
    workspace.gh_bin.chmod(workspace.gh_bin.stat().st_mode | stat.S_IEXEC)


def _block_opencode(workspace: Path) -> str:
    """Make the external OpenCode model probe fail without stubbing Louke."""
    original = workspace.opencode_bin.read_text(encoding="utf-8")
    workspace.opencode_bin.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "models" ]; then\n'
        '  printf "%s\\n" "ark/minimax-m3"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "run" ]; then\n'
        '  printf "%s\\n" "model unreachable" >&2\n'
        "  exit 1\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    workspace.opencode_bin.chmod(workspace.opencode_bin.stat().st_mode | stat.S_IEXEC)
    return original


def _restore_opencode(workspace: Path, original: str) -> None:
    """Restore the successful external OpenCode CLI stand-in."""
    workspace.opencode_bin.write_text(original, encoding="utf-8")
    workspace.opencode_bin.chmod(workspace.opencode_bin.stat().st_mode | stat.S_IEXEC)


def test_login_readiness_warning_keeps_forms_usable_and_retry_is_fresh(
    browser_page, live_server
):
    """AC-FR0201-02/AC-FR0301-01: blocked readiness warns without disabling auth."""
    # AC-FR0201-02 / AC-FR0301-01
    page, base_url = browser_page
    _, workspace, opencode = live_server
    _seed_model_config(workspace.root)
    original_gh = _block_gh_auth(workspace)
    try:
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        page.locator("#readiness-warning").wait_for(state="visible")

        warning = page.locator("#readiness-warning").inner_text()
        assert "gh_auth_scopes" in warning
        assert "Authenticate" in warning or "Retry" in warning
        assert page.locator("#login-username").is_enabled()
        page.locator("#tab-register").click()
        assert page.locator("#register-username").is_enabled()
        assert page.locator("#register-password").is_enabled()

        _restore_gh_auth(workspace, original_gh)
        page.locator("#readiness-retry").click()
        page.wait_for_function(
            "() => document.querySelector('#readiness-status')?.textContent.includes('passed')"
        )
        assert page.locator("#readiness-warning").is_hidden()
        assert any(
            entry.get("kind") == "run" and "--model" in entry.get("argv", [])
            for entry in opencode.read_ledger()
        )
    finally:
        _restore_gh_auth(workspace, original_gh)


def test_login_model_failure_exposes_actionable_diagnosis_without_blocking_auth(
    browser_page, live_server
):
    """AC-NFR0201-02: real model failure becomes a redacted Login warning."""
    # AC-NFR0201-02
    page, base_url = browser_page
    _, workspace, _ = live_server
    _seed_model_config(workspace.root)
    original_opencode = _block_opencode(workspace)
    try:
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        page.locator("#readiness-warning").wait_for(state="visible")

        warning = page.locator("#readiness-warning").inner_text()
        assert "opencode_model" in warning
        assert "Login readiness cannot verify a working OpenCode model" in warning
        assert "Retry" in warning
        assert "model unreachable" not in page.inner_text("body")
        assert page.locator("#login-submit").is_enabled()
        page.locator("#tab-register").click()
        assert page.locator("#register-submit").is_enabled()
    finally:
        _restore_opencode(workspace, original_opencode)


def test_login_register_is_explicit_and_workbench_uses_login(browser_page, live_server):
    """AC-FR0401-01: Login/Register form the public user entry journey."""
    # AC-FR0401-01
    page, base_url = browser_page

    page.goto(f"{base_url}/workbench", wait_until="domcontentloaded")
    page.wait_for_url("**/login?next=/workbench")
    assert page.locator("#tab-login").is_visible()
    assert page.locator("#tab-register").is_visible()

    page.locator("#tab-register").click()
    page.locator("#register-username").fill("login-human")
    page.locator("#register-password").fill("test-secret")
    page.locator("#register-submit").click()
    page.wait_for_url("**/workbench?activity=projects")
    assert "projects" in page.url
