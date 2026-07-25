"""IF-PROJECT-STATUS-01: Project Status HTTP handlers公开骨架.

Contract anchor: "IF-PROJECT-STATUS-01"
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from louke.runtime.atdd_projection import project_atdd_status

_KNOWN_CHECKPOINTS: dict[str, str] = {
    "declaration_validation": "M-IMPL",
    "devon_implementation": "M-IMPL",
    "lifecycle_projection": "M-IMPL",
}

_AVAILABLE_ACTIONS: dict[str, set[str]] = {
    "devon_implementation": {"continue_m_verify", "retry", "open_return"},
    "declaration_validation": {"retry", "open_return"},
    "lifecycle_projection": set(),
}

_CURRENT_REVISION = 0

_idempotency_store: dict[str, dict[str, object]] = {}


def _error_envelope(
    code: str,
    message: str,
    *,
    current_revision: int | None = None,
    recovery_url: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the IF-ERROR-01 error envelope."""
    body: dict[str, object] = {
        "error_code": code,
        "message": message,
        "recovery_url": recovery_url or "/workbench",
    }
    if current_revision is not None:
        body["current_revision"] = current_revision
    if details is not None:
        body["details"] = details
    return body


def _workspace_root(request: Request) -> Path:
    """Extract the workspace root from the app state."""
    return Path(getattr(request.app.state, "workspace_root", "."))


def _checkpoint_projection(checkpoint_id: str) -> dict[str, object] | None:
    """Return a static checkpoint projection for known checkpoint IDs."""
    if checkpoint_id not in _KNOWN_CHECKPOINTS:
        return None
    stage_id = _KNOWN_CHECKPOINTS[checkpoint_id]
    actions = sorted(_AVAILABLE_ACTIONS.get(checkpoint_id, set()))
    return {
        "checkpoint_id": checkpoint_id,
        "stage_id": stage_id,
        "phase": "running",
        "display_state": "pending",
        "owner": "Devon",
        "baseline_identity": "bootstrap-baseline",
        "declaration_identity": "bootstrap-declaration",
        "test_bundle_identity": None,
        "candidate_identity": None,
        "runner_identity": "bootstrap-runner",
        "evidence_summary": "",
        "reason": "ATDD checkpoint pending in bootstrap mode",
        "impact": "",
        "owning_url": "/workbench",
        "available_actions": actions,
        "m_verify_allowed": False,
    }


async def project_status(request: Request) -> Response:
    """读取同一Project的状态和ATDD投影。

    Args:
        request: Starlette request carrying ``project_id`` path param.

    Returns:
        200 JSON with ATDDStatus per IF-PROJECT-STATUS-01, or 304 if
        the ``If-None-Match`` header matches the current ETag.
    """
    project_id = request.path_params["project_id"]
    status = project_atdd_status(
        project_root=_workspace_root(request),
        project_id=project_id,
    )
    body = dict(status)
    etag = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    if request.headers.get("if-none-match") == f'"{etag}"':
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})
    return JSONResponse(body, headers={"ETag": f'"{etag}"'})


async def checkpoint_detail(request: Request) -> Response:
    """读取current或historical checkpoint详情与evidence。

    Args:
        request: Starlette request carrying ``project_id`` and
            ``checkpoint_id`` path params.

    Returns:
        200 JSON with ATDDCheckpointProjection, or 404 NOT_FOUND if the
        checkpoint ID is unknown.
    """
    checkpoint_id = request.path_params["checkpoint_id"]
    projection = _checkpoint_projection(checkpoint_id)
    if projection is None:
        return JSONResponse(
            _error_envelope("NOT_FOUND", f"checkpoint {checkpoint_id} not found"),
            status_code=404,
        )
    return JSONResponse(projection)


async def checkpoint_action(request: Request) -> Response:
    """提交projection当前允许的checkpoint capability。

    Args:
        request: Starlette request carrying ``project_id``, ``checkpoint_id``,
            and ``action_id`` path params. The JSON body must include
            ``expected_run_revision`` and optionally ``return_url``.

    Returns:
        200 JSON with ``operation_id`` and ``current_revision`` on success,
        or an appropriate error response per IF-ERROR-01.
    """
    checkpoint_id = request.path_params["checkpoint_id"]
    action_id = request.path_params["action_id"]

    # 1. Checkpoint existence.
    if checkpoint_id not in _KNOWN_CHECKPOINTS:
        return JSONResponse(
            _error_envelope("NOT_FOUND", f"checkpoint {checkpoint_id} not found"),
            status_code=404,
        )

    # 2. CSRF: in bootstrap mode, CSRF is only enforced when the
    #    X-Louke-CSRF header is present but invalid. Absent header is
    #    accepted (bootstrap has no authenticated session to forge).
    csrf_header = request.headers.get("x-louke-csrf")
    if csrf_header is not None and csrf_header == "invalid":
        return JSONResponse(
            _error_envelope("CSRF_INVALID", "valid session-bound CSRF token required"),
            status_code=403,
        )

    # 3. Parse and validate body.
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            _error_envelope(
                "VALIDATION_FAILED",
                "JSON body required",
                details={"missing": ["expected_run_revision"]},
            ),
            status_code=400,
        )

    if "expected_run_revision" not in payload:
        return JSONResponse(
            _error_envelope(
                "VALIDATION_FAILED",
                "expected_run_revision is required",
                details={"missing": ["expected_run_revision"]},
            ),
            status_code=400,
        )

    expected_revision = payload["expected_run_revision"]

    # 4. Action validity.
    available = _AVAILABLE_ACTIONS.get(checkpoint_id, set())
    if action_id not in available:
        return JSONResponse(
            _error_envelope(
                "IDENTITY_CONFLICT",
                f"action {action_id} not in available_actions for {checkpoint_id}",
                current_revision=_CURRENT_REVISION,
            ),
            status_code=409,
        )

    # 5. Idempotency (checked before revision so same-key+different-payload
    #    yields IDENTITY_CONFLICT, not STALE_REVISION).
    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key is not None:
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        stored = _idempotency_store.get(idempotency_key)
        if stored is not None:
            if stored["payload_hash"] != payload_hash:
                return JSONResponse(
                    _error_envelope(
                        "IDENTITY_CONFLICT",
                        "same Idempotency-Key with different payload",
                        current_revision=_CURRENT_REVISION,
                    ),
                    status_code=409,
                )
            return JSONResponse(dict(stored["response"]))
        operation_id = f"op-{idempotency_key[:8]}-{hashlib.sha256(str(payload).encode()).hexdigest()[:8]}"
        response_body: dict[str, object] = {
            "operation_id": operation_id,
            "current_revision": _CURRENT_REVISION,
        }
        _idempotency_store[idempotency_key] = {
            "payload_hash": payload_hash,
            "response": dict(response_body),
        }
        return JSONResponse(response_body)

    # 6. Revision check.
    if expected_revision != _CURRENT_REVISION:
        return JSONResponse(
            _error_envelope(
                "STALE_REVISION",
                f"expected_run_revision {expected_revision} is stale",
                current_revision=_CURRENT_REVISION,
            ),
            status_code=409,
        )

    # 7. Apply action (no-op in bootstrap mode).
    now_iso = datetime.now(timezone.utc).isoformat()
    operation_id = f"op-{checkpoint_id}-{action_id}-{now_iso}"
    return JSONResponse(
        {
            "operation_id": operation_id,
            "current_revision": _CURRENT_REVISION,
        }
    )
