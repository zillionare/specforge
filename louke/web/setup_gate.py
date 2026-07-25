"""Setup Gate: global entry protection until Setup completes.

AC-FR0001-01, AC-FR0001-02, AC-FR0301-02

The gate decides whether a request may proceed to its target handler.
When the persisted Setup manifest is not a valid v2 ``complete``,
only the Setup allowlist is reachable. All other page requests
redirect to ``/setup`` (303); all other API requests return
``428 SETUP_REQUIRED``. The gate never executes the target handler
before redirecting.

When the manifest is missing, corrupt, or has an unknown schema, the
gate fails closed (treats Setup as incomplete).
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from louke.web.setup_state import MANIFEST_VERSION, SetupStatus, try_read_manifest

_API_PREFIX = "/api/"

STATUS_PENDING_USER = SetupStatus.PENDING_USER.value
STATUS_PENDING_MODEL = SetupStatus.PENDING_MODEL.value
STATUS_COMPLETE = SetupStatus.COMPLETE.value
SCHEMA_VERSION = MANIFEST_VERSION
_PAGE_ALLOWLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/setup(/.*)?$"),
    re.compile(r"^/health$"),
    re.compile(r"^/assets/"),
)

_API_ALLOWLIST: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/api/setup/status$")),
    ("POST", re.compile(r"^/api/setup/first-user$")),
    ("POST", re.compile(r"^/api/setup/model-checks(/.*)?$")),
    ("GET", re.compile(r"^/api/setup/model-checks(/.*)?$")),
    ("POST", re.compile(r"^/api/auth/login$")),
)

_STATUS_COMPLETE = SetupStatus.COMPLETE.value


def _is_page_allowlisted(path: str) -> bool:
    """Return ``True`` if *path* matches a page allowlist entry."""
    return any(pattern.match(path) for pattern in _PAGE_ALLOWLIST)


def _is_api_allowlisted(method: str, path: str) -> bool:
    """Return ``True`` if the ``(method, path)`` pair is allowlisted."""
    upper = method.upper()
    return any(
        allowed_method == upper and pattern.match(path)
        for allowed_method, pattern in _API_ALLOWLIST
    )


class SetupGate:
    """Decision function for Setup entry protection.

    The gate is a pure decision object: it does not read cookies,
    Guide state, or executable presence. Only the persisted manifest
    status is authoritative.

    Args:
        workspace_root: Optional workspace root for reading the manifest.
            If omitted, the status must be set via :meth:`set_status`.
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self._workspace_root = Path(workspace_root) if workspace_root else None
        self._status: str = SetupStatus.PENDING_USER.value
        if self._workspace_root is not None:
            manifest = try_read_manifest(self._workspace_root)
            if manifest is not None:
                self._status = manifest.status.value

    @property
    def status(self) -> str:
        """The current Setup status string."""
        return self._status

    def set_status(self, status: str) -> None:
        """Set the current Setup status.

        Args:
            status: One of ``pending_user``, ``pending_model``, ``complete``.
        """
        self._status = status

    def redirect(self, path: str, *, authenticated: bool = False) -> tuple[int, str]:
        """Decide whether a page request should be redirected.

        Args:
            path: The request path.
            authenticated: Whether the caller has an authenticated session.

        Returns:
            A ``(status_code, target_url)`` tuple. When ``status_code``
            is 303, the caller must redirect to ``target_url``. When
            200, the caller may proceed to ``path`` (or the canonical
            Workbench Projects URL for authenticated workbench access).
        """
        if self._status == _STATUS_COMPLETE:
            if path == "/workbench" and authenticated:
                return 200, "/workbench?activity=projects"
            return 200, path
        if _is_page_allowlisted(path):
            return 200, path
        return 303, "/setup"

    def guard_api(self, method: str, path: str) -> tuple[int, dict[str, str]]:
        """Decide whether an API request may proceed.

        Args:
            method: HTTP method.
            path: Request path.

        Returns:
            A ``(status_code, body)`` tuple. When ``status_code`` is
            428, the caller must return the ``body`` as JSON and must
            not execute the target handler. When 200, the caller may
            proceed.
        """
        if self._status == _STATUS_COMPLETE:
            return 200, {}
        if _is_api_allowlisted(method, path):
            return 200, {}
        return 428, {"error": "SETUP_REQUIRED", "setup_url": "/setup"}


class SetupGateMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that wraps :class:`SetupGate` for route protection.

    Args:
        app: The wrapped ASGI application.
        workspace_root: Workspace root containing ``.louke/``.
    """

    def __init__(self, app, workspace_root: str | Path) -> None:
        super().__init__(app)
        self._workspace_root = Path(workspace_root)
        self._gate = SetupGate(workspace_root=workspace_root)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Gate each request before dispatch.

        Args:
            request: The incoming Starlette request.
            call_next: Next middleware/handler callable.

        Returns:
            A redirect (303), a 428 JSON error, or the handler response.
        """
        # Re-read the manifest on every request so the gate observes Setup
        # completion without a server restart. The Setup API/page mutate the
        # manifest in-process; without this refresh a freshly completed Setup
        # would keep redirecting the Human back to ``/setup`` because the gate
        # still held the startup-time status. ``try_read_manifest`` fails
        # closed (``None`` on a corrupt/unknown manifest), in which case the
        # last-known status is retained.
        manifest = try_read_manifest(self._workspace_root)
        if manifest is not None:
            self._gate.set_status(manifest.status.value)

        path = request.url.path
        if path.startswith(_API_PREFIX):
            status_code, body = self._gate.guard_api(request.method, path)
            if status_code == 428:
                return JSONResponse(body, status_code=428)
            return await call_next(request)

        status_code, target = self._gate.redirect(path)
        if status_code == 303:
            return RedirectResponse(url=target, status_code=303)
        return await call_next(request)
