"""Thin authenticated HTTP adapter for local Environment readiness."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from louke.web.environment_service import EnvironmentService

from .projects import _require_human


async def check_environment(request: Request) -> JSONResponse:
    """POST one read-only terminal Environment readiness projection."""
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    service = EnvironmentService(
        request.app.state.workspace_root,
        executor=getattr(request.app.state, "environment_executor", None),
    )
    return JSONResponse(service.check())
