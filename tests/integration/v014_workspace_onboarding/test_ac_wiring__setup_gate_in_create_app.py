"""Create-app wiring keeps Project creation fail-closed until readiness.

AC-FR0601-02, AC-FR1001-01, AC-FR1101-01, AC-FR1501-01
"""

from __future__ import annotations

from pathlib import Path

from tests.integration.v014_workspace_onboarding.test_ac_fr0101_0301_0201__if_setup01_02_03 import (
    _app,
    _headers,
    _model_result,
)
from tests.test_web_server import authenticate


def test_create_app_wires_preview_to_the_aggregate_readiness_gate(
    tmp_path: Path,
) -> None:
    """AC-FR0601-02/AC-FR1001-01/AC-FR1101-01/AC-FR1501-01: blocked preview."""
    # AC-FR0601-02 / AC-FR1001-01 / AC-FR1101-01 / AC-FR1501-01
    client = _app(tmp_path, lambda _: _model_result("failed"))
    authenticate(client, username="fixture-human", password="secret")

    response = client.post(
        "/api/projects/preview",
        headers={**_headers(client), "Idempotency-Key": "blocked-preview"},
        json={"story": "fixture story", "release_version": "0.14.1"},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "ENVIRONMENT_GATE_BLOCKED"
