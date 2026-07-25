"""E2E: ATDD Project Status main-success journey for v0.14-005.

Cross-module: Workbench Presentation × Runtime Projection ×
ATDD Checkpoint.

These tests assert the **final contract behaviour** per
IF-PROJECT-STATUS-01 only. We do NOT use ``in (200, 500)`` dual-mode
placeholders — that pattern accepts any stub response and never
forms a valid RED.

Today (stub state), each route handler raises
``NotImplementedError("IF-PROJECT-STATUS-01")`` and Starlette's
ServerErrorMiddleware sanitises the body to ``"Internal Server
Error"``. The tests below assert 200 + JSON envelope; the stub
returns 500; every assertion FAILs with the AC token in the
message — valid RED per IF-VALID-RED-01.

Once Devon implements the projection, every assertion flips
GREEN.

Failure / recovery variants live in ``test_failure_recovery_e2e``.
"""

from __future__ import annotations


# Fixtures ``shielded_complete_workspace`` and ``shielded_app_client``
# are defined in this directory's ``conftest.py``; they reach the
# real ``create_app(project_root=...)`` composition root through a
# seeded tmp workspace.


_REQUIRED_ATDD_STATUS_KEYS: frozenset[str] = frozenset(
    {
        "stage_id",
        "current_checkpoint_id",
        "checkpoints",
        "baseline_identity",
        "declaration_identity",
        "test_bundle_identity",
        "candidate_identity",
        "runner_identity",
        "closure_summary",
        "attention",
        "m_verify_allowed",
        "observed_at",
        "fresh_until",
    }
)


def _assert_atdd_status_envelope(body: dict) -> None:
    """Validate the parsed JSON body exposes the closed set of ATDDStatus keys."""
    missing = _REQUIRED_ATDD_STATUS_KEYS - set(body.keys())
    assert not missing, (
        f"AC-FR1201-01 / IF-PROJECT-STATUS-01: status body missing "
        f"ATDDStatus keys: {sorted(missing)}; got keys="
        f"{sorted(body.keys())!r}"
    )


def test_e2e_status_route_returns_atdd_projection_envelope(shielded_app_client) -> None:
    """GET /api/projects/<id>/status must return 200 + ATDDStatus JSON.

    Contract: ``louke.web.app.create_app`` registers the route;
    the handler returns ``200 application/json`` ATDDStatus per
    IF-PROJECT-STATUS-01. Stub raises 500 → assertion FAILs with
    AC-FR1201-01 / AC-FR0901-01 token → valid RED.
    """
    response = shielded_app_client.get("/api/projects/demo-project/status")

    assert response.status_code == 200, (
        "AC-FR1201-01 / IF-PROJECT-STATUS-01: GET /status must "
        f"return 200; got {response.status_code}. Stub must raise "
        "(→ RED), correct impl must return 200 + ATDDStatus."
    )
    assert response.headers["content-type"].startswith("application/json"), (
        "AC-FR1201-01 / IF-PROJECT-STATUS-01: GET /status must "
        f"return application/json; got "
        f"{response.headers.get('content-type')!r}"
    )
    _assert_atdd_status_envelope(response.json())


def test_e2e_checkpoint_detail_route_returns_checkpoint_projection(
    shielded_app_client,
) -> None:
    """GET /api/projects/<id>/status/checkpoints/<cid> returns checkpoint projection.

    Contract: ``louke.web.app.create_app`` registers the route;
    the handler returns ``200 application/json`` ATDDCheckpointProjection
    per IF-PROJECT-STATUS-01. Stub raises 500 → FAIL with
    AC-FR1201-01 / AC-FR0901-01.
    """
    response = shielded_app_client.get(
        "/api/projects/demo-project/status/checkpoints/declaration_validation"
    )

    assert response.status_code == 200, (
        "AC-FR1201-01 / IF-PROJECT-STATUS-01: GET /status/checkpoints/"
        f"<cid> must return 200; got {response.status_code} Body="
        f"{response.text[:200]!r}"
    )
    assert response.headers["content-type"].startswith("application/json"), (
        "AC-FR1201-01 / IF-PROJECT-STATUS-01: checkpoint detail must "
        f"return application/json; got "
        f"{response.headers.get('content-type')!r}"
    )
    body = response.json()
    required = {
        "checkpoint_id",
        "stage_id",
        "phase",
        "display_state",
        "owner",
        "baseline_identity",
        "declaration_identity",
        "test_bundle_identity",
        "candidate_identity",
        "runner_identity",
        "evidence_summary",
        "reason",
        "impact",
        "owning_url",
        "available_actions",
        "m_verify_allowed",
    }
    missing = required - set(body.keys())
    assert not missing, (
        f"AC-FR1201-01 / IF-PROJECT-STATUS-01: checkpoint detail "
        f"missing ATDDCheckpointProjection keys: {sorted(missing)}; "
        f"got keys={sorted(body.keys())!r}"
    )


def test_e2e_checkpoint_action_route_applies_action(shielded_app_client) -> None:
    """POST /api/projects/<id>/status/checkpoints/<cid>/actions/<aid> applies action.

    Contract: ``louke.web.app.create_app`` registers the route;
    the handler applies the action (per the projection's
    ``available_actions``) and returns ``200 application/json``
    with operation id and current revision per IF-PROJECT-STATUS-01.
    Stub raises 500 → FAIL with AC-FR1201-01 / AC-FR0901-01.
    """
    response = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json={"expected_run_revision": 0, "return_url": "/workbench"},
    )

    assert response.status_code == 200, (
        "AC-FR1201-01 / IF-PROJECT-STATUS-01: POST checkpoint "
        f"action must return 200 (action applied); got "
        f"{response.status_code}. The route must exist; the handler "
        "must apply the action and return operation_id + current_revision."
    )
    assert response.headers["content-type"].startswith("application/json"), (
        "AC-FR1201-01: action response must be application/json; "
        f"got {response.headers.get('content-type')!r}"
    )
    body = response.json()
    assert "operation_id" in body, (
        f"AC-FR1201-01: action body must carry operation_id; "
        f"got keys={sorted(body.keys())!r}"
    )
    assert "current_revision" in body, (
        f"AC-FR1201-01: action body must carry current_revision; "
        f"got keys={sorted(body.keys())!r}"
    )


def test_e2e_workbench_active_card_url_renders_in_complete_workspace(
    shielded_app_client,
) -> None:
    """Workbench active-card URL renders when Setup is complete.

    This is the one contract that should be GREEN today — the
    Workbench view exists and renders the canonical shell. A
    damage to the Workbench render breaks the user-visible surface
    in the e2e main-success journey.
    """
    response = shielded_app_client.get(
        "/workbench?activity=projects&project=demo-project"
    )
    assert response.status_code == 200, (
        "AC-FR1201-01: Workbench active-card URL must render 200 "
        f"when Setup is complete; got {response.status_code}."
    )
    assert "<title>Louke Workbench</title>" in response.text, (
        "AC-FR1201-01: Workbench must render the canonical shell, "
        f"not a parallel dashboard. Got head={response.text[:200]!r}"
    )
