"""Authenticated Project preview, creation and status APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from louke.web.auth import SESSION_COOKIE, current_user, same_origin
from louke.web.csrf_middleware import verify_token as verify_csrf_token
from louke.runtime.release_entry import (
    ReleaseEntryService,
    ReleaseRequestConflictError,
    StalePreviewError,
)
from louke.runtime.release_request import PreviewError
from louke.web.login_readiness import check_login_readiness_async
from louke.web.workspace_identity import workspace_label


def _service(request: Request) -> ReleaseEntryService:
    """Return the Runtime-owned release entry service from app state."""
    return request.app.state.release_entry


def _require_human(request: Request, *, csrf_required: bool):
    """Require a valid Human session and, for writes, its bound CSRF token."""
    store = request.app.state.store
    session = request.cookies.get(SESSION_COOKIE)
    user = current_user(store, session)
    if user is None:
        return JSONResponse(_error("AUTH_REQUIRED", "login required"), status_code=401)
    if csrf_required and not same_origin(
        request, getattr(request.app.state, "allowed_origin", None)
    ):
        return JSONResponse(
            _error("ORIGIN_FORBIDDEN", "configured same-origin Origin header required"),
            status_code=403,
        )
    if csrf_required and not verify_csrf_token(
        token=request.headers.get("x-louke-csrf", ""),
        session_id=session,
    ):
        return JSONResponse(
            _error("CSRF_INVALID", "valid session-bound CSRF token required"),
            status_code=403,
        )
    return user


def _required_string(payload: object, field: str) -> str:
    """Return a non-empty string field from a JSON object."""
    value = _required_field(payload, field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_int(payload: object, field: str) -> int:
    """Return an integer field without accepting booleans."""
    value = _required_field(payload, field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _required_field(payload: object, field: str) -> Any:
    """Return a field from a JSON object or raise a client-validation error."""
    if not isinstance(payload, dict):
        raise ValueError("JSON object payload is required")
    return payload.get(field)


def _error(code: str, message: str) -> dict[str, Any]:
    """Return the common API error envelope."""
    return {"error_code": code, "message": message}


def _required_idempotency_key(request: Request) -> str:
    """Return the bounded canonical Idempotency-Key header value."""
    value = request.headers.get("idempotency-key", "").strip()
    if not value:
        raise ValueError("Idempotency-Key header is required")
    if len(value) > 256:
        raise ValueError("Idempotency-Key header is too long")
    return value


def _preview_environment_identity(
    request: Request, environment: dict[str, Any]
) -> dict[str, Any]:
    """Project the verified workspace and repository identity into Preview."""
    steps = {
        str(step.get("id")): step
        for step in environment.get("steps", [])
        if isinstance(step, dict)
    }
    repository = steps.get("repository_binding", {}).get("observed") or {}
    main = steps.get("canonical_main", {}).get("observed") or {}
    return {
        "workspace": {
            "workspace_id": str(getattr(request.app.state, "workspace_id", "")),
            "label": workspace_label(request.app.state.workspace_root),
        },
        "repository": {
            "host": repository.get("host"),
            "owner": repository.get("owner"),
            "name": repository.get("name"),
            "main_sha": main.get("main_sha"),
        },
    }


def _readiness_identity(
    request: Request, environment: dict[str, Any]
) -> dict[str, str]:
    """Return the exact terminal repository facts optimistic Confirm validates."""
    visible = _preview_environment_identity(request, environment)
    repository = visible["repository"]
    values = {
        "workspace_id": visible["workspace"]["workspace_id"],
        "host": repository["host"],
        "owner": repository["owner"],
        "name": repository["name"],
        "main_sha": repository["main_sha"],
    }
    if not all(isinstance(value, str) and value for value in values.values()):
        raise ValueError("terminal readiness has no canonical repository identity")
    return {key: str(value) for key, value in values.items()}


def _project_context_state(request: Request) -> str:
    """Return the persisted project context state (empty/active/conflict).

    Reads ``.louke/project-state.json`` from the workspace root.
    Only a missing file means an empty context. Corrupt, unreadable, non-object,
    and unknown-state files fail closed as ``conflict``.
    """
    workspace_root = Path(request.app.state.workspace_root)
    state_path = workspace_root / ".louke" / "project-state.json"
    if not state_path.is_file():
        return "empty"
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "conflict"
    if not isinstance(raw, dict):
        return "conflict"
    state = raw.get("state")
    return str(state) if state in {"empty", "active", "conflict"} else "conflict"


async def _readiness_for_creation(
    request: Request, *, require_empty_context: bool = True
) -> dict[str, Any] | JSONResponse:
    """Run current readiness and optionally require an empty Project context."""
    env = await check_login_readiness_async(
        request.app.state.workspace_root,
        executor=getattr(request.app.state, "environment_executor", None),
        model_checker=getattr(request.app.state, "readiness_model_checker", None),
    )
    if env["state"] != "passed":
        return JSONResponse(
            _error(
                "ENVIRONMENT_GATE_BLOCKED",
                "Environment gate has not passed; resolve the failing "
                "steps before creating a Project.",
            ),
            status_code=409,
        )
    project_state = _project_context_state(request)
    if require_empty_context and project_state != "empty":
        return JSONResponse(
            _error(
                "PROJECT_CONTEXT_NOT_EMPTY",
                "A Project already exists in this workspace; resolve the "
                "active or conflicting Project before creating a new one.",
            ),
            status_code=409,
        )
    return env


async def preview_project(request: Request) -> JSONResponse:
    """POST ``/api/projects/preview`` after a current readiness read.

    Body:
        ``{story, release_version}``

    Returns:
        ``200 ProjectPreview`` with the environment identity bound, or
        ``409 ENVIRONMENT_GATE_BLOCKED`` / ``PROJECT_CONTEXT_NOT_EMPTY``
        when the gate fails-closed.
    """
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        payload = await request.json()
        story = _required_string(payload, "story")
        release_version = _required_string(payload, "release_version")
        gate = await _readiness_for_creation(request)
        if isinstance(gate, JSONResponse):
            return gate
        readiness_identity = _readiness_identity(request, gate)
        preview = _service(request).preview(
            story,
            release_version,
            readiness_identity,
        )
        preview.update(_preview_environment_identity(request, gate))
    except PreviewError as exc:
        return JSONResponse(_error(exc.code, exc.message), status_code=400)
    except ValueError as exc:
        return JSONResponse(_error("VALIDATION_ERROR", str(exc)), status_code=400)
    return JSONResponse(preview)


async def confirm_project(request: Request) -> JSONResponse:
    """POST ``/api/projects/confirm`` after a current readiness read.

    Body:
        ``{preview_id, expected_preview_revision, request_digest}``

    Header:
        ``Idempotency-Key`` (canonical, preferred over body ``idempotency_key``)

    Returns:
        ``202 ProjectCreation``, or ``409`` when the environment gate or
        stale preview blocks the confirmation.
    """
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        payload = await request.json()
        preview_id = _required_string(payload, "preview_id")
        expected_preview_revision = _required_int(payload, "expected_preview_revision")
        request_digest = _required_string(payload, "request_digest")
        idempotency_key = _required_idempotency_key(request)
        replay = _service(request).replay_ready(
            preview_id,
            expected_preview_revision=expected_preview_revision,
            request_digest=request_digest,
            idempotency_key=idempotency_key,
            actor=user_or_response.username,
        )
        if replay is not None:
            return JSONResponse(replay, status_code=202)
        gate = await _readiness_for_creation(request)
        if isinstance(gate, JSONResponse):
            return gate
        readiness_identity = _readiness_identity(request, gate)
        result = _service(request).confirm(
            preview_id,
            expected_preview_revision=expected_preview_revision,
            request_digest=request_digest,
            idempotency_key=idempotency_key,
            actor=user_or_response.username,
            readiness_identity=readiness_identity,
        )
    except StalePreviewError as exc:
        return JSONResponse(_error("STALE_PREVIEW", str(exc)), status_code=409)
    except ReleaseRequestConflictError as exc:
        return JSONResponse(_error("REQUEST_CONFLICT", str(exc)), status_code=409)
    except (KeyError, ValueError) as exc:
        return JSONResponse(_error("VALIDATION_ERROR", str(exc)), status_code=400)
    return JSONResponse(result, status_code=202)


async def project_creation_status(request: Request) -> JSONResponse:
    """GET the current durable Project creation projection."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        return JSONResponse(_service(request).status(request.path_params["request_id"]))
    except KeyError as exc:
        return JSONResponse(_error("NOT_FOUND", str(exc)), status_code=404)
