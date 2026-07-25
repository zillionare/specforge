"""IF-SETUP-01 / IF-SETUP-02: Two-context Setup page (interface stub).

This file is an **Archer interface stub** (Archer.md §5.3.5).  Devon
replaces the ``raise NotImplementedError`` bodies with real rendering
logic; the function signatures, route registration and composition-root
contract (``create_app``) are **locked** by ``interfaces.md``.

The locked v0.14-004 baseline replaces the retired six-step Setup Wizard
(``identity -> repository -> dependencies -> review -> applying ->
complete``) with a two-context Setup page:

  1. ``pending_user``  -> the first-user creation form.
  2. ``pending_model`` -> the OpenCode model-check view with Retry.

On ``complete`` the page redirects to ``/workbench?activity=projects``.
The retired per-step routes ``/setup/repository/``, ``/setup/dependencies/``,
``/setup/review/`` and ``/setup/applying/`` are **not registered** and
return 404.

Composition root: ``louke.web.app`` imports ``create_app`` and mounts it
at ``/setup`` (``app.py:82``, ``app.py:341``).
"""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


# ---------------------------------------------------------------------------
# Test seams (production implementations call the real API)
# ---------------------------------------------------------------------------


async def _fetch_setup_status(
    api_base: str, *, request: Request | None = None
) -> dict[str, Any]:
    """IF-SETUP-01: Fetch the Setup projection from the backend API.

    Test seam: tests patch this with ``patch.object(setup_page,
    "_fetch_setup_status", ...)`` to feed the real projection derived
    from an on-disk v2 manifest.  The production implementation calls
    ``GET /api/setup/status``.

    If a future implementation reads the projection directly from the
    bound workspace (``request.app.state.workspace_root``) and drops
    this seam, the test patch degrades to a no-op.
    """
    raise NotImplementedError("IF-SETUP-01")


async def _post_first_user(
    api_base: str, *, name: str, credential: str
) -> dict[str, Any]:
    """IF-SETUP-02: Submit the first-user creation form to the backend API.

    Test seam; production calls ``POST /api/setup/first-user``.
    """
    raise NotImplementedError("IF-SETUP-02")


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


async def setup_root(request: Request) -> Response:
    """IF-SETUP-01: Render the two-context Setup page at ``/``.

    Devon implements:

    - ``pending_user`` -> 200 HTML with the first-user creation form
      (``input[name="name"]``, ``input[name="credential"]``).
    - ``pending_model`` -> 200 HTML with the model-check view and a
      Retry entry; failure diagnosis shows ``object``, ``known_facts``,
      ``impact`` and ``recovery_url``.
    - ``complete`` -> 302/303 redirect to ``/workbench?activity=projects``.

    The handler reads the v2 manifest projection (via ``_fetch_setup_status``
    or directly from ``request.app.state.workspace_root``) and renders
    the appropriate context.  No retired six-step routes or markers
    (``Runtime dependencies``, ``/setup/repository/``, etc.) may appear.
    """
    raise NotImplementedError("IF-SETUP-01")


# ---------------------------------------------------------------------------
# Composition root
# ---------------------------------------------------------------------------


def create_app() -> Starlette:
    """Return the two-context Setup page sub-app.

    Only ``/`` is registered; retired six-step routes naturally 404.
    ``louke.web.app`` mounts this at ``/setup`` and sets
    ``app.state.workspace_root`` on the returned instance.
    """
    return Starlette(
        routes=[
            Route("/", endpoint=setup_root, methods=["GET"]),
        ],
    )
