"""Canonical unauthenticated Login entry contract.

AC-FR0001-01, AC-FR0001-02, AC-FR0301-02
"""

from __future__ import annotations

from pathlib import Path

from tests.integration.v014_workspace_onboarding.test_ac_fr0101_0301_0201__if_setup01_02_03 import (
    _app,
    _model_result,
)


def test_unauthenticated_user_entry_resolves_to_login(
    tmp_path: Path,
) -> None:
    """AC-FR0001-01/AC-FR0001-02/AC-FR0301-02: public Login is authoritative."""
    # AC-FR0001-01 / AC-FR0001-02 / AC-FR0301-02
    client = _app(tmp_path, lambda _: _model_result("passed"))

    root = client.get("/", follow_redirects=False)
    workbench = client.get("/workbench", follow_redirects=False)

    assert root.status_code == 303
    assert root.headers["location"].startswith("/login")
    assert workbench.status_code == 303
    assert workbench.headers["location"].startswith("/login")
