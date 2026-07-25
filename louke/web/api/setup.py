"""``/api/setup`` Starlette sub-app: first-user setup endpoints.

Exposes the first-principal flow as a JSON HTTP API. The first user is written
to the workspace user store so setup state survives a server restart. The v2
Setup manifest (``.louke/web-setup-state.json``) is the single source of truth
for Setup status; the legacy wizard-state endpoints remain for backward
compatibility.

Endpoints:
    GET  /status       - return the v2 Setup manifest projection.
    POST /first-user   - create the first local human principal.
    GET  /state        - return the persisted Setup Wizard state (legacy).
    POST /state        - overwrite the persisted Setup Wizard state (legacy).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from louke.web.csrf_middleware import issue_for_session, verify_token
from louke.web.setup_projection import read as read_projection
from louke.web.setup_state import SetupStatus, try_read_manifest
from louke.web.store import ProjectStore, ValidationError

from ._common import install_error_handlers, json_body, require_str


def create_app(workspace_root: str | Path | None = None) -> Starlette:
    """Return a self-contained Starlette sub-app for ``/api/setup``.

    Returns:
        A Starlette application whose routes are relative to ``/api/setup``.
    """
    app = Starlette(routes=_routes())
    app.state.workspace_root = Path(workspace_root or ".").resolve()
    install_error_handlers(app)
    return app


def _routes() -> list[Route]:
    """Return the routes for the setup sub-app."""
    return [
        Route("/status", endpoint=get_status),
        Route("/first-user", endpoint=create_first_user, methods=["POST"]),
        Route("/model-checks", endpoint=post_model_check, methods=["POST"]),
        Route("/model-checks/{check_id}", endpoint=get_model_check, methods=["GET"]),
        Route("/state", endpoint=get_state, methods=["GET"]),
        Route("/state", endpoint=post_state, methods=["POST"]),
    ]


def _store(request: Request) -> ProjectStore:
    """Return the workspace store shared with serve and web authentication."""
    return ProjectStore(request.app.state.workspace_root)


def _workspace_root(request: Request) -> Path:
    """Return the workspace root path from the app state."""
    return Path(request.app.state.workspace_root)


def _principal_id(name: str) -> str:
    """Return a stable local principal id derived from the username."""
    return f"prin_{hashlib.sha256(name.encode()).hexdigest()[:12]}"


def _session_id(request: Request) -> str:
    """Extract a stable session identifier from the request.

    Uses the session cookie value if present, otherwise falls back
    to the request's remote address+port combination so pre-auth
    sessions still get a stable id for CSRF token issuance.
    """
    from louke.web.auth import SESSION_COOKIE

    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        return cookie
    client = request.client
    if client is not None:
        return f"preauth:{client.host}:{client.port}"
    return "preauth:anonymous"


async def get_status(request: Request) -> JSONResponse:
    """AC-FR0301-01: return the v2 Setup manifest projection.

    Returns:
        ``200`` with the v2 manifest shape per interfaces §IF-SETUP-01:
        ``{workspace_id, revision, status, first_user, model_check,
        available_actions, continue_url, csrf_token}``.
    """
    workspace_root = _workspace_root(request)
    manifest = try_read_manifest(workspace_root)
    workspace_id = manifest.workspace_id if manifest else ""
    body = read_projection(workspace_root, workspace_id=workspace_id)

    # Resolve ``first_user.name`` from the user store when a first
    # principal is recorded in the manifest.
    first_user = body.get("first_user")
    if first_user and first_user.get("principal_id"):
        users = _store(request).list_users()
        if users:
            first_user["name"] = users[0]["username"]

    # Issue a CSRF token bound to the current session + revision.
    revision = body.get("revision", 0)
    body["csrf_token"] = issue_for_session(
        session_id=_session_id(request),
        revision=revision,
    )
    return JSONResponse(body)


async def create_first_user(request: Request) -> JSONResponse:
    """AC-FR0201-01: create the first local human principal.

    Body:
        ``{"name": str, "credential": str, "expected_revision": int}``.

    Returns:
        ``201`` with ``{principal_id, name, setup_revision, status,
        continue_url}``.

    Raises:
        HTTPException 403: If the CSRF token is missing or invalid.
        HTTPException 409: If a first user already exists.
    """
    csrf_token = request.headers.get("X-Louke-CSRF", "")
    if not csrf_token or not verify_token(
        token=csrf_token,
        session_id=_session_id(request),
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    payload = await json_body(request)
    name = require_str(payload, "name")
    credential = require_str(payload, "credential")
    expected_revision = payload.get("expected_revision", 0)
    store = _store(request)
    workspace_root = _workspace_root(request)
    if store.list_users():
        raise HTTPException(status_code=409, detail="first user already exists")
    try:
        store.create_user(name, credential)
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    from louke.web.first_user import principal_id_for
    from louke.web.setup_state import (
        SetupManifest,
        write_manifest,
    )

    manifest = SetupManifest(
        workspace_id="",
        revision=expected_revision,
        status=SetupStatus.PENDING_USER,
    )
    advanced = manifest.advance_to_pending_model(
        first_principal_id=principal_id_for(name),
        expected_revision=expected_revision,
    )
    write_manifest(workspace_root, advanced)
    return JSONResponse(
        {
            "principal_id": _principal_id(name),
            "name": name,
            "setup_revision": advanced.revision,
            "status": advanced.status.value,
            "continue_url": "/setup",
        },
        status_code=201,
    )


# ---------------------------------------------------------------------------
# IF-SETUP-03: real OpenCode model check
# ---------------------------------------------------------------------------


def _model_check_payload(
    result: Any, *, setup_revision: int, continue_url: str | None
) -> dict[str, Any]:
    """Shape an OpenCode probe result as the IF-SETUP-03 ``ModelCheck`` object."""
    return {
        "check_id": result.check_id,
        "revision": result.revision,
        "state": result.state,
        "current_model_id": result.current_model_id,
        "attempted_models": [
            {"model_id": probe.model_id, "result": probe.state}
            for probe in result.attempted
        ],
        "diagnosis": result.diagnosis,
        "observed_at": result.observed_at,
        "deadline_at": None,
        "retry_allowed": result.state in ("failed", "uncertain"),
        "setup_revision": setup_revision,
        "continue_url": continue_url,
    }


async def post_model_check(request: Request) -> JSONResponse:
    """AC-FR0201-01 / AC-FR0301-01: run a real OpenCode model check.

    Body:
        ``{"expected_revision": int}``.

    Returns:
        ``202`` with the ``ModelCheck`` object. On ``passed`` the v2
        manifest is atomically completed and ``continue_url`` points at the
        Workbench Projects activity; on ``failed``/``uncertain`` the latest
        non-secret diagnosis is persisted and Setup stays ``pending_model``.

    Raises:
        HTTPException 403: missing/invalid CSRF token.
        HTTPException 409: no first user yet, or a stale ``expected_revision``.
    """
    from dataclasses import replace

    from louke.web import opencode_probe
    from louke.web.setup_state import (
        ModelCheck,
        SetupStatus,
        try_read_manifest,
        write_manifest,
    )

    csrf_token = request.headers.get("X-Louke-CSRF", "")
    if not csrf_token or not verify_token(
        token=csrf_token,
        session_id=_session_id(request),
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    workspace_root = _workspace_root(request)
    manifest = try_read_manifest(workspace_root)
    if manifest is None or manifest.first_principal_id is None:
        raise HTTPException(
            status_code=409, detail="first user must be created before a model check"
        )

    payload = await json_body(request)
    expected_revision = payload.get("expected_revision", manifest.revision)
    if expected_revision != manifest.revision:
        raise HTTPException(
            status_code=409,
            detail=(
                f"stale revision: expected {expected_revision}, "
                f"current {manifest.revision}"
            ),
        )

    result = opencode_probe.run_check()

    if result.state == "passed":
        completed = manifest.complete(
            model_check_state="passed",
            model_check_id=result.check_id,
            model_check_revision=result.revision,
            model_id=result.current_model_id,
            diagnosis=None,
            observed_at=result.observed_at,
            expected_revision=manifest.revision,
        )
        write_manifest(workspace_root, completed)
        return JSONResponse(
            _model_check_payload(
                result,
                setup_revision=completed.revision,
                continue_url="/workbench?activity=projects",
            ),
            status_code=202,
        )

    # Failed / uncertain: persist the latest non-secret diagnosis and keep
    # Setup pending_model so the page can show an actionable Retry.
    snapshot = ModelCheck(
        check_id=result.check_id,
        revision=result.revision,
        state=result.state,
        model_id=result.current_model_id,
        diagnosis=result.diagnosis,
        observed_at=result.observed_at,
    )
    updated = replace(
        manifest,
        status=SetupStatus.PENDING_MODEL,
        model_check=snapshot,
        revision=manifest.revision + 1,
    )
    write_manifest(workspace_root, updated)
    return JSONResponse(
        _model_check_payload(
            result, setup_revision=updated.revision, continue_url=None
        ),
        status_code=202,
    )


async def get_model_check(request: Request) -> JSONResponse:
    """AC-FR0201-02: read the most recent model check by id.

    Returns:
        ``200`` with the ``ModelCheck`` object when ``check_id`` matches the
        persisted snapshot; ``404`` otherwise.
    """
    from louke.web.setup_state import try_read_manifest

    check_id = request.path_params["check_id"]
    manifest = try_read_manifest(_workspace_root(request))
    model_check = manifest.model_check if manifest else None
    if model_check is None or model_check.check_id != check_id:
        raise HTTPException(status_code=404, detail="model check not found")
    payload = model_check.to_dict()
    payload["setup_revision"] = manifest.revision
    payload["retry_allowed"] = model_check.state in ("failed", "uncertain")
    payload["continue_url"] = None
    return JSONResponse(payload)


_ALLOWED_STEPS: frozenset[str] = frozenset(
    {
        "identity",
        "repository",
        "dependencies",
        "review",
        "applying",
        "complete",
    }
)


def _validate_state(payload: Any) -> dict[str, Any]:
    """Coerce and validate the wizard-state payload."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="state must be an object")
    current_step = payload.get("current_step") or "identity"
    if current_step not in _ALLOWED_STEPS:
        raise HTTPException(
            status_code=400, detail=f"invalid current_step: {current_step}"
        )
    completed_raw = payload.get("completed_steps") or []
    if not isinstance(completed_raw, list):
        raise HTTPException(status_code=400, detail="completed_steps must be a list")
    completed = [c for c in completed_raw if c in _ALLOWED_STEPS]
    blocking_raw = payload.get("blocking_items") or []
    if not isinstance(blocking_raw, list):
        raise HTTPException(status_code=400, detail="blocking_items must be a list")
    blocking = [str(b) for b in blocking_raw]
    selections_raw = payload.get("selections") or {}
    if not isinstance(selections_raw, dict):
        raise HTTPException(status_code=400, detail="selections must be an object")
    selections = {str(k): str(v) for k, v in selections_raw.items()}
    return {
        "current_step": current_step,
        "completed_steps": completed,
        "blocking_items": blocking,
        "selections": selections,
    }


async def get_state(request: Request) -> JSONResponse:
    """GET /api/setup/state: return the persisted Setup Wizard state.

    Returns:
        ``200`` with the persisted state dict, or an empty default if no
        state has been recorded yet.
    """
    state = _store(request).read_setup_state() or {}
    return JSONResponse(_validate_state(state))


async def post_state(request: Request) -> JSONResponse:
    """POST /api/setup/state: overwrite the persisted Setup Wizard state.

    Body: ``{"current_step": str, "completed_steps": list, ...}``.

    Returns:
        ``200`` with the normalized state.
    """
    payload = await json_body(request)
    normalized = _validate_state(payload)
    _store(request).write_setup_state(normalized)
    return JSONResponse(normalized)
