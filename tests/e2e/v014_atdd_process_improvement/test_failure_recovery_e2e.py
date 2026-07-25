"""E2E: ATDD Project Status failure-recovery journey for v0.14-005.

Cross-module: Workbench Presentation × Runtime Projection ×
Failure Routing × Runtime Facts.

These tests assert the **final contract behaviour** per IF-ERROR-01
only — no ``in (..., 500)`` dual-mode placeholder. Today (stub
state), handler raises ``NotImplementedError("IF-PROJECT-STATUS-01")``
→ 500 + sanitised body. Each test below asserts the documented
status code + JSON body with closed error_code enum — the stub
returning 500 makes every assertion FAIL with the AC token in the
message, forming valid RED per IF-VALID-RED-01.

Once Devon implements correctly, each assertion flips GREEN.

Contracts covered (per IF-ERROR-01):
  * unknown action id        → 409 IDENTITY_CONFLICT + recovery_url
  * stale expected_run_revision → 409 STALE_REVISION +
    current_revision + recovery_url
  * status + workbench route pair must share composition root
  * missing CSRF token        → 403 CSRF_INVALID
  * Idempotency-Key replay same payload → 200 + same operation_id
  * Idempotency-Key replay different payload → 409 IDENTITY_CONFLICT
  * unknown checkpoint id   → 404 NOT_FOUND
  * missing expected_run_revision → 400 VALIDATION_FAILED

Closed error-code enum per IF-ERROR-01:
  400 VALIDATION_FAILED,
  401 AUTH_REQUIRED,
  403 PERMISSION_DENIED | CSRF_INVALID | SCOPE_DENIED,
  404 NOT_FOUND,
  409 STALE_REVISION | IDENTITY_CONFLICT | COOLDOWN |
      OPERATION_UNCERTAIN,
  428 CONTRACT_NOT_ACTIVE.
"""

from __future__ import annotations


# Fixtures ``shielded_complete_workspace`` and ``shielded_app_client``
# are defined in this directory's ``conftest.py``; they reach the
# real ``create_app(project_root=...)`` composition root through a
# seeded tmp workspace.


# Closed error-code enum per IF-ERROR-01.
_CLOSED_ERROR_CODES: frozenset[str] = frozenset(
    {
        "VALIDATION_FAILED",
        "AUTH_REQUIRED",
        "PERMISSION_DENIED",
        "CSRF_INVALID",
        "SCOPE_DENIED",
        "NOT_FOUND",
        "STALE_REVISION",
        "IDENTITY_CONFLICT",
        "COOLDOWN",
        "OPERATION_UNCERTAIN",
        "CONTRACT_NOT_ACTIVE",
    }
)


def _assert_closed_error_code(body: dict, *, expected_code: str, ac: str) -> None:
    """Assert the body uses the documented closed error_code enum."""
    code = body.get("error_code")
    assert code in _CLOSED_ERROR_CODES, (
        f"{ac} / IF-ERROR-01: error_code must be one of the closed "
        f"enum {sorted(_CLOSED_ERROR_CODES)!r}; got {code!r}."
    )
    assert code == expected_code, (
        f"{ac} / IF-ERROR-01: error_code must be {expected_code!r}; "
        f"got {code!r}. Body={body!r}"
    )


def _assert_json_error_envelope(body: dict, *, ac: str) -> None:
    """Assert the body exposes the documented error envelope keys.

    Per IF-ERROR-01 the JSON error body is
    ``{error_code, message, current_revision, recovery_url, details}``.
    """
    for required in ("error_code", "message", "recovery_url"):
        assert required in body, (
            f"{ac} / IF-ERROR-01: error body missing required key "
            f"{required!r}; got keys={sorted(body.keys())!r}"
        )


def test_e2e_unknown_action_id_yields_closed_error_code(shielded_app_client) -> None:
    """Forged action id must yield 409 IDENTITY_CONFLICT (per IF-ERROR-01).

    The projection's ``available_actions`` defines the documented
    actions; a forged id must be rejected with 409 IDENTITY_CONFLICT.
    Silent 2xx success would be a contract violation.

    Stub raises 500 → assertion FAILs with AC-FR1201-01 / AC-FR0901-01
    token → valid RED.
    """
    response = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/invented_action",
        json={"expected_run_revision": 0, "return_url": "/workbench"},
    )

    assert response.status_code == 409, (
        "AC-FR1201-01 / IF-ERROR-01: forged action id must yield "
        f"409 IDENTITY_CONFLICT; got {response.status_code} Body="
        f"{response.text[:200]!r}. Stub raising 500 is RED; "
        "correct implementation returns 409 with closed error_code."
    )
    body = response.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(
        body, expected_code="IDENTITY_CONFLICT", ac="AC-FR1201-01"
    )


def test_e2e_stale_expected_run_revision_yields_409_stale_revision(
    shielded_app_client,
) -> None:
    """POST with stale expected_run_revision → 409 STALE_REVISION.

    Per IF-ERROR-01 closed enum: ``409 STALE_REVISION|IDENTITY_CONFLICT
    |COOLDOWN|OPERATION_UNCERTAIN``. A POST with
    ``expected_run_revision=999`` (a stale value past the current
    projection revision) must be rejected with 409 STALE_REVISION,
    and the body must carry ``current_revision`` and
    ``recovery_url`` for the user to recover.

    Stub raises 500 → FAIL with AC-FR1201-01 / AC-FR0901-01 → RED.
    """
    response = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json={"expected_run_revision": 999, "return_url": "/workbench"},
    )

    assert response.status_code == 409, (
        "AC-FR1201-01 / IF-ERROR-01: stale expected_run_revision "
        f"must yield 409 STALE_REVISION; got {response.status_code} "
        f"Body={response.text[:200]!r}. Stub 500 is RED; correct "
        "impl returns 409 + STALE_REVISION + current_revision "
        "+ recovery_url."
    )
    body = response.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(body, expected_code="STALE_REVISION", ac="AC-FR1201-01")
    assert "current_revision" in body, (
        f"AC-FR1201-01 / IF-ERROR-01: STALE_REVISION body must "
        f"carry current_revision; got keys={sorted(body.keys())!r}"
    )


def test_e2e_status_and_workbench_route_pair_is_consistent(shielded_app_client) -> None:
    """Status + workbench route pair share composition root.

    After a fresh Setup-complete workspace, ``GET /status`` reaches
    the handler (returning 200 + ATDDStatus) and ``GET /workbench``
    renders 200 — both through the same composition root. This is
    the user-visible coupling contract: divergence between the API
    surface and Workbench surface breaks the Project Status UI.

    The /status half is RED today (stub); the /workbench half is
    GREEN (Workbench exists). The combined test FAILs until
    ``/status`` returns 200.
    """
    status = shielded_app_client.get("/api/projects/demo/status")
    workbench = shielded_app_client.get("/workbench?activity=projects&project=demo")

    assert status.status_code == 200, (
        "AC-FR1201-01: /api/projects/demo/status must return 200 + "
        f"ATDDStatus; got {status.status_code}. Stub raises 500 → "
        "RED."
    )
    assert workbench.status_code == 200, (
        "AC-FR1201-01: /workbench must render in the same workspace; "
        f"got {workbench.status_code}"
    )


def test_e2e_checkpoint_action_without_csrf_header_is_rejected(
    shielded_app_client,
) -> None:
    """Invalid CSRF token -> 403 CSRF_INVALID.

    Per IF-ERROR-01: ``403 PERMISSION_DENIED|CSRF_INVALID|SCOPE_DENIED``.
    A POST to ``/api/projects/<id>/status/checkpoints/<cid>/actions/<aid>``
    with an invalid CSRF token must be rejected with 403 CSRF_INVALID.

    Stub raises 500 -> FAIL with AC-FR1201-01 / AC-FR0901-01 -> RED.
    """
    response = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json={"expected_run_revision": 0, "return_url": "/workbench"},
        headers={"X-Louke-CSRF": "invalid"},
    )

    assert response.status_code == 403, (
        "AC-FR1201-01 / IF-ERROR-01: missing CSRF must yield 403 "
        f"CSRF_INVALID; got {response.status_code} Body="
        f"{response.text[:200]!r}"
    )
    body = response.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(body, expected_code="CSRF_INVALID", ac="AC-FR1201-01")


def test_e2e_idempotency_replay_same_payload_yields_same_operation(
    shielded_app_client,
) -> None:
    """Same Idempotency-Key + same payload → same operation_id.

    Per IF-ERROR-01: ``同key同payload返回同operation``. Two POSTs
    with the same ``Idempotency-Key`` and the same body must return
    the same ``operation_id``. A second side-effect would be a
    concurrency violation.

    Stub raises 500 → both calls FAIL with AC-FR1201-01 token.
    """
    headers = {"Idempotency-Key": "shield-red-test-key-001"}
    payload = {"expected_run_revision": 0, "return_url": "/workbench"}
    first = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json=payload,
        headers=headers,
    )
    second = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 200, (
        "AC-FR1201-01 / IF-ERROR-01: first idempotent POST must "
        f"return 200; got {first.status_code}. Stub 500 → RED."
    )
    assert second.status_code == 200, (
        "AC-FR1201-01 / IF-ERROR-01: second idempotent POST (same "
        f"key/payload) must return 200 with same operation_id; got "
        f"{second.status_code}."
    )
    first_op = first.json().get("operation_id")
    second_op = second.json().get("operation_id")
    assert first_op is not None and second_op is not None, (
        f"AC-FR1201-01 / IF-ERROR-01: idempotent responses must "
        f"carry operation_id; first={first.json()!r} second="
        f"{second.json()!r}"
    )
    assert first_op == second_op, (
        f"AC-FR1201-01 / IF-ERROR-01: same Idempotency-Key + same "
        f"payload must yield same operation_id; got first={first_op!r} "
        f"second={second_op!r}"
    )


def test_e2e_idempotency_replay_different_payload_yields_409(
    shielded_app_client,
) -> None:
    """Same Idempotency-Key + different payload → 409 IDENTITY_CONFLICT.

    Per IF-ERROR-01: ``同key异payload或stale为409且无第二副作用``.
    The second POST with the same key but different body must be
    rejected with 409 IDENTITY_CONFLICT, and the first call's
    side-effect must remain (no second side-effect).

    Stub raises 500 → RED.
    """
    headers = {"Idempotency-Key": "shield-red-test-key-002"}
    payload_a = {"expected_run_revision": 0, "return_url": "/workbench"}
    payload_b = {"expected_run_revision": 1, "return_url": "/workbench"}

    first = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json=payload_a,
        headers=headers,
    )
    second = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json=payload_b,
        headers=headers,
    )

    assert first.status_code == 200, (
        "AC-FR1201-01 / IF-ERROR-01: first idempotent POST must "
        f"return 200; got {first.status_code}. Stub 500 → RED."
    )
    assert second.status_code == 409, (
        "AC-FR1201-01 / IF-ERROR-01: second POST with same key but "
        "different payload must yield 409 IDENTITY_CONFLICT (no "
        f"second side-effect); got {second.status_code}"
    )
    body = second.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(
        body, expected_code="IDENTITY_CONFLICT", ac="AC-FR1201-01"
    )


def test_e2e_unknown_checkpoint_id_yields_404_not_found(shielded_app_client) -> None:
    """Unknown checkpoint id → 404 NOT_FOUND.

    Per IF-ERROR-01: ``404 NOT_FOUND`` is in the closed enum. The
    handler must reject an unknown checkpoint id with 404 NOT_FOUND
    and a documented error envelope.

    Stub raises 500 → RED.
    """
    response = shielded_app_client.get(
        "/api/projects/demo-project/status/checkpoints/this_id_does_not_exist"
    )

    assert response.status_code == 404, (
        "AC-FR1201-01 / IF-ERROR-01: unknown checkpoint id must "
        f"yield 404 NOT_FOUND; got {response.status_code} Body="
        f"{response.text[:200]!r}"
    )
    body = response.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(body, expected_code="NOT_FOUND", ac="AC-FR1201-01")


def test_e2e_missing_expected_run_revision_yields_400(shielded_app_client) -> None:
    """Missing ``expected_run_revision`` → 400 VALIDATION_FAILED.

    Per IF-ERROR-01: ``400 VALIDATION_FAILED``. The body must
    reject an action POST that omits ``expected_run_revision`` with
    400 VALIDATION_FAILED and reference the missing field in the
    error details.

    Stub raises 500 → RED.
    """
    response = shielded_app_client.post(
        "/api/projects/demo-project/status/checkpoints/devon_implementation/actions/continue_m_verify",
        json={"return_url": "/workbench"},  # missing expected_run_revision
    )

    assert response.status_code == 400, (
        "AC-FR1201-01 / IF-ERROR-01: missing expected_run_revision "
        f"must yield 400 VALIDATION_FAILED; got {response.status_code} "
        f"Body={response.text[:200]!r}"
    )
    body = response.json()
    _assert_json_error_envelope(body, ac="AC-FR1201-01")
    _assert_closed_error_code(
        body, expected_code="VALIDATION_FAILED", ac="AC-FR1201-01"
    )
    import json

    assert "expected_run_revision" in json.dumps(body), (
        f"AC-FR1201-01 / IF-ERROR-01: 400 details must reference "
        f"expected_run_revision; got {body!r}"
    )
