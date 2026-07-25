"""AC-FR0901-01 / AC-FR1201-01 / AC-FR1601-01 — IF-PROJECT-STATUS-01/UI-01.

Cross-module: ``Workbench Presentation`` × ``Runtime Projection`` ×
``ATDD Checkpoint`` × ``Failure Routing``.

The three ATDD Project Status routes — status, checkpoint detail,
checkpoint action — must:

1. be present in the production ``create_app()`` composition root;
2. be served from the real handler module
   (``louke.web.api.project_status``), not from a test-owned app;
3. shape the response as IF-PROJECT-STATUS-01 specifies.

The stubs currently raise ``NotImplementedError("IF-PROJECT-STATUS-01")``
inside their own module; the route registration is the responsibility of
``louke/web/app.py`` and must not 404 even though the handler body
itself is unimplemented (because the real implementation by Devon
inherits the same wiring).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path


from louke.web.api import project_status
from louke.web.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_ac_fr0901_01_projection_module_exposes_three_handlers() -> None:
    """AC-FR0901-01: ``project_status`` module exports the three route handlers."""
    for name in ("project_status", "checkpoint_detail", "checkpoint_action"):
        assert hasattr(project_status, name), (
            f"AC-FR0901-01: louke.web.api.project_status must export {name!r}"
        )
        fn = getattr(project_status, name)
        assert inspect.iscoroutinefunction(fn), (
            f"AC-FR0901-01: {name} must be an async handler (Starlette "
            f"expects ``async def`` route handlers)."
        )


def test_ac_fr0901_01_routes_registered_against_production_create_app() -> None:
    """AC-FR0901-01 / AC-FR1201-01: routes exist on the real composition root.

    We use the project's own ``create_app`` and assert each required
    path pattern is registered.
    """
    app = create_app(project_root=str(REPO_ROOT))

    # The routes use Starlette ``{name}`` placeholders; we accept either the
    # literal pattern string or its compiled repr.
    route_path_patterns = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if path and path.startswith("/api/projects/"):
            route_path_patterns.add(path)

    required_prefixes = (
        "/api/projects/{project_id}/status",
        "/api/projects/{project_id}/status/checkpoints/",
    )
    matched = {}
    for needle in required_prefixes:
        matched[needle] = any(path.startswith(needle) for path in route_path_patterns)

    for prefix, ok in matched.items():
        assert ok, (
            f"AC-FR1201-01: create_app() must register an ATDD route "
            f"starting with {prefix!r}; "
            f"observed routes={sorted(route_path_patterns)}"
        )


def test_ac_fr0901_01_handler_stubs_raise_if_token() -> None:
    """AC-FR0901-01: each handler raises NotImplementedError with the IF token.

    Even though the route is registered, the handler must mark its
    unimplemented state with the IF-PROJECT-STATUS-01 token so that any
    request reaches ``IF-VALID-RED-01`` with correct attribution.
    """
    src = Path(project_status.__file__).read_text(encoding="utf-8")
    matches = re.findall(
        r"""NotImplementedError\(["']IF-PROJECT-STATUS-01["']\)""",
        src,
    )
    assert len(matches) == 3, (
        f"AC-FR0901-01: each of project_status/checkpoint_detail/"
        f"checkpoint_action must raise NotImplementedError with "
        f"IF-PROJECT-STATUS-01; found {len(matches)} literal(s)."
    )


def test_ac_fr0901_01_app_py_imports_only_declares_routes() -> None:
    """AC-FR0901-01: ``app.py`` only imports+registers ATDD handlers.

    The ATDD-related diff of ``app.py`` (per interfaces.md §8) must
    consist solely of (a) an import statement pulling the three
    handler functions, and (b) three ``Route(...)`` registrations.
    No handler bodies, no business logic.
    """
    src = (REPO_ROOT / "louke" / "web" / "app.py").read_text(encoding="utf-8")

    # The ATDD diff is identified by marker imports. We trust that any
    # pre-existing handlers (e.g. health, readiness) that exist on
    # v0.14-004 are not part of this Spec's concern.
    atdd_imports_present = all(
        name in src
        for name in (
            "checkpoint_action",
            "checkpoint_detail",
            "project_status",
        )
    )
    assert atdd_imports_present, (
        "AC-FR0901-01: app.py must import project_status, "
        "checkpoint_detail, checkpoint_action from "
        "``louke.web.api.project_status``."
    )

    # The ATDD handlers are wired as ``endpoint=project_status``, etc.
    # but NOT defined in app.py itself.
    for forbidden in (
        "async def project_status",
        "async def checkpoint_detail",
        "async def checkpoint_action",
        "def project_status",
        "def checkpoint_detail",
        "def checkpoint_action",
    ):
        assert forbidden not in src, (
            f"AC-FR0901-01: app.py must not define handler body for "
            f"{forbidden!r}; route registrations only."
        )


def test_ac_fr1201_01_app_handlers_unwrapped_through_atddcheck_route() -> None:
    """AC-FR1201-01: routes exist with both GET and POST methods where required.

    The status route is GET, the action route is POST. A missing method
    would silently 405 at runtime.
    """
    app = create_app(project_root=str(REPO_ROOT))

    status_route = next(
        (
            route
            for route in app.router.routes
            if getattr(route, "path", "") == "/api/projects/{project_id}/status"
        ),
        None,
    )
    assert status_route is not None, (
        "AC-FR1201-01: status route must be discoverable on the app"
    )
    methods = set(getattr(status_route, "methods", set()) or set())
    assert "GET" in methods, (
        f"AC-FR1201-01: status route must allow GET; got methods={methods}"
    )

    action_route = next(
        (
            route
            for route in app.router.routes
            if getattr(route, "path", "").startswith(
                "/api/projects/{project_id}/status/checkpoints/"
            )
            and getattr(route, "path", "").endswith("/actions/{action_id}")
        ),
        None,
    )
    assert action_route is not None, "AC-FR1201-01: action route must be discoverable"
    methods = set(getattr(action_route, "methods", set()) or set())
    assert "POST" in methods, (
        f"AC-FR1201-01: action route must allow POST; got methods={methods}"
    )
