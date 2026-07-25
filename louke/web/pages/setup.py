"""IF-SETUP-01 / IF-SETUP-02: Two-context Setup page.

The locked v0.14-004 baseline replaces the retired six-step Setup Wizard
(``identity -> repository -> dependencies -> review -> applying ->
complete``) with a two-context Setup page:

  1. ``pending_user``  -> the first-user creation form.
  2. ``pending_model`` -> the OpenCode model-check view with a Retry entry.

On ``complete`` the page redirects to ``/workbench?activity=projects``.
The retired per-step routes ``/setup/repository/``, ``/setup/dependencies/``,
``/setup/review/`` and ``/setup/applying/`` are **not registered** and
return 404.

Composition root: ``louke.web.app`` registers :func:`setup_root` directly at
``/setup`` (``GET`` and ``POST``). The page is served from a plain ``Route``
rather than a ``Mount`` so ``/setup`` resolves without a trailing-slash
redirect (the Setup journeys assert the canonical ``/setup`` URL).

The page is fully server-rendered and server-driven: both the first-user form
and the model-check Retry control are plain HTML forms that ``POST`` back to
``/setup``. The handler mutates the v2 manifest and answers with a ``303``
redirect, so each human action is a single deterministic navigation (no
client-side fetch/reload race). A session-bound CSRF token is embedded in each
form and verified on ``POST``.
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ..auth import SESSION_COOKIE
from ..csrf_middleware import issue_for_session, verify_token
from ..setup_state import (
    ModelCheck,
    SetupStatus,
    try_read_manifest,
    write_manifest,
)

#: Where a finished Setup sends the Human.
_PROJECTS_CONTINUE_URL = "/workbench?activity=projects"

#: The canonical Setup page URL (no trailing slash).
_SETUP_URL = "/setup"

#: Diagnosis fields rendered for a failed/uncertain model check
#: (interfaces §IF-SETUP-03 ``ModelCheck.diagnosis``). The display labels
#: double as the accessible, non-secret field names the contract requires.
_DIAGNOSIS_FIELDS: tuple[tuple[str, str], ...] = (
    ("object", "Object"),
    ("known_facts", "Known facts"),
    ("impact", "Impact"),
    ("recovery_url", "Recovery url"),
)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _resolve_session_id(request: Request) -> tuple[str, bool]:
    """Return ``(session_id, needs_cookie)`` for CSRF binding.

    Reuses the opaque Setup session cookie when present; otherwise mints a new
    pre-auth identifier that the caller must set as a cookie so the same
    identifier is seen when the form is posted back. The identifier carries no
    credential and is not an authenticated session (interfaces §1, §IF-SETUP-02).
    """
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        return cookie, False
    return f"preauth.{secrets.token_hex(16)}", True


def _set_session_cookie(response: Response, session_id: str) -> None:
    """Set the opaque pre-auth Setup session cookie on ``response``."""
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=600,
    )


# ---------------------------------------------------------------------------
# Test seams (production implementations call the real API / projection)
# ---------------------------------------------------------------------------


async def _fetch_setup_status(
    api_base: str, *, request: Request | None = None
) -> dict[str, Any]:
    """IF-SETUP-01: Fetch the Setup projection from the backend API.

    Test seam: tests patch this with ``patch.object(setup_page,
    "_fetch_setup_status", ...)`` to feed the real projection derived
    from an on-disk v2 manifest. The production implementation reads the
    same projection the ``GET /api/setup/status`` endpoint returns.

    Args:
        api_base: Upstream API base URL (unused; the projection is read
            from the bound workspace).
        request: The current request, used to resolve the workspace root.

    Returns:
        The Setup projection dict (``workspace_id``, ``revision``,
        ``status``, ``first_user``, ``model_check``, ``available_actions``,
        ``continue_url``).
    """
    from ..setup_projection import read as read_projection
    from ..store import ProjectStore

    workspace_root = Path(request.app.state.workspace_root)
    manifest = try_read_manifest(workspace_root)
    workspace_id = manifest.workspace_id if manifest else ""
    body = read_projection(workspace_root, workspace_id=workspace_id)

    first_user = body.get("first_user")
    if first_user and first_user.get("principal_id"):
        users = ProjectStore(workspace_root).list_users()
        if users:
            first_user["name"] = users[0]["username"]
    return body


async def _post_first_user(
    api_base: str, *, name: str, credential: str
) -> dict[str, Any]:
    """IF-SETUP-02: Submit the first-user creation form to the backend API.

    Test seam retained for contract symmetry; production calls
    ``POST /api/setup/first-user``. The server-rendered page performs the
    first-user creation inline (see :func:`_create_first_user_from_form`) so
    the human action is a single deterministic navigation; this client seam is
    kept for tooling that drives the JSON API directly.

    Args:
        api_base: Upstream API base URL (``""`` for same-origin).
        name: The first user's display name.
        credential: The first user's credential.

    Returns:
        The decoded JSON response body from the first-user endpoint.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/api/setup/first-user",
            json={"name": name, "credential": credential},
        )
        resp.raise_for_status()
        return dict(resp.json())


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _diagnosis_html(diagnosis: dict[str, Any]) -> str:
    """Render a non-secret, actionable diagnosis as a definition list.

    Each contract field (``object``, ``known_facts``, ``impact``,
    ``recovery_url``) is shown under an accessible label; values are escaped
    as plain text so provider output can never inject markup (interfaces §1
    Untrusted text/URL).
    """
    rows = []
    for key, label in _DIAGNOSIS_FIELDS:
        value = str(diagnosis.get(key, "") or "")
        rows.append(
            f'<div class="diagnosis-row"><dt>{escape(label)}</dt>'
            f"<dd>{escape(value)}</dd></div>"
        )
    return f'<dl class="diagnosis">{"".join(rows)}</dl>'


def _model_check_html(model_check: dict[str, Any] | None) -> str:
    """Render the model-check context for ``pending_model``.

    Shows the current check state and, for a failed or uncertain check, the
    actionable diagnosis. The wording deliberately avoids ``complete`` and
    ``passed`` so a failed check is never reinterpreted as finished
    (acceptance AC-NFR0201-02 Runtime authority).
    """
    if not model_check:
        return (
            '<p class="setup-hint">No model check has run yet. Start the '
            "check to verify a working OpenCode model.</p>"
        )
    state = str(model_check.get("state", "") or "")
    model_id = str(model_check.get("model_id", "") or "")
    parts = [
        f'<p class="model-state">Model check state: <strong>{escape(state)}</strong></p>'
    ]
    if model_id:
        parts.append(f'<p class="model-id">Model: {escape(model_id)}</p>')
    diagnosis = model_check.get("diagnosis")
    if state in ("failed", "uncertain") and isinstance(diagnosis, dict):
        parts.append(_diagnosis_html(diagnosis))
    return "".join(parts)


def _render_pending_user(
    projection: dict[str, Any],
    csrf_token: str,
    *,
    name: str = "",
    error: str = "",
) -> str:
    """Render the first-user creation form (``pending_user`` context).

    The form posts back to ``/setup``; the handler creates the first user and
    redirects, so submitting is a single deterministic navigation. The submitted
    ``name`` is preserved on error (interfaces §7).
    """
    error_html = (
        f'<p class="setup-error" role="alert">{escape(error)}</p>' if error else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up Louke</title>
<style>{_SETUP_STYLES}</style></head>
<body>
<main class="setup-card" data-setup-context="pending_user">
  <h1>Create the first user</h1>
  <p class="setup-lede">Louke needs one local human account to finish Setup.</p>
  <form id="setup-first-user-form" action="{_SETUP_URL}" method="post">
    <input type="hidden" name="csrf_token" value="{escape(csrf_token, quote=True)}">
    <label class="setup-field">Name
      <input name="name" type="text" autocomplete="username" value="{escape(name, quote=True)}" required>
    </label>
    <label class="setup-field">Credential
      <input name="credential" type="password" autocomplete="new-password" required>
    </label>
    <button type="submit" name="create_first_user" value="1">Create first user</button>
    {error_html}
  </form>
</main>
</body></html>"""


def _render_pending_model(projection: dict[str, Any], csrf_token: str) -> str:
    """Render the OpenCode model-check view (``pending_model`` context).

    The Retry control is a plain form that posts back to ``/setup``; the
    handler runs the real model check and redirects (to the Workbench Projects
    activity on success, back to ``/setup`` otherwise).
    """
    model_check = projection.get("model_check")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up Louke</title>
<style>{_SETUP_STYLES}</style></head>
<body>
<main class="setup-card" data-setup-context="pending_model">
  <h1>Verify an OpenCode model</h1>
  <p class="setup-lede">Setup runs one minimal real model request to confirm a
     working OpenCode model. Nothing is finished until a model check succeeds.</p>
  <section class="model-check" aria-live="polite">
    {_model_check_html(model_check)}
  </section>
  <form id="setup-model-check-form" action="{_SETUP_URL}" method="post">
    <input type="hidden" name="csrf_token" value="{escape(csrf_token, quote=True)}">
    <button type="submit" name="retry" value="1">Retry model check</button>
  </form>
</main>
</body></html>"""


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


async def setup_root(request: Request) -> Response:
    """IF-SETUP-01 / IF-SETUP-02: serve the two-context Setup page at ``/setup``.

    ``GET`` renders the context matching the v2 manifest projection:

    - ``pending_user`` -> 200 HTML first-user creation form.
    - ``pending_model`` -> 200 HTML model-check view with a Retry entry; a
      failed/uncertain check shows ``object``, ``known_facts``, ``impact`` and
      ``recovery_url``.
    - ``complete`` -> 303 redirect to ``/workbench?activity=projects``.

    ``POST`` processes the server-driven forms (first-user creation or model
    check) and answers with a 303 redirect, so each human action is a single
    deterministic navigation. No retired six-step routes or markers are
    rendered.
    """
    if request.method == "POST":
        return await _handle_setup_post(request)
    return await _handle_setup_get(request)


async def _handle_setup_get(request: Request) -> Response:
    """Render the Setup context for a ``GET`` request."""
    projection = await _fetch_setup_status("", request=request)
    status = projection.get("status", "")

    if status == "complete":
        continue_url = projection.get("continue_url") or _PROJECTS_CONTINUE_URL
        return RedirectResponse(url=continue_url, status_code=303)

    session_id, needs_cookie = _resolve_session_id(request)
    csrf_token = issue_for_session(
        session_id=session_id, revision=projection.get("revision", 0)
    )

    if status == "pending_model":
        response: Response = HTMLResponse(
            _render_pending_model(projection, csrf_token)
        )
    else:
        response = HTMLResponse(_render_pending_user(projection, csrf_token))

    if needs_cookie:
        _set_session_cookie(response, session_id)
    return response


async def _handle_setup_post(request: Request) -> Response:
    """Process a server-driven Setup form and redirect."""
    form = await request.form()
    session_id = request.cookies.get(SESSION_COOKIE, "")
    csrf_token = str(form.get("csrf_token", ""))
    if not csrf_token or not verify_token(token=csrf_token, session_id=session_id):
        # Fail closed: an invalid CSRF token re-renders Setup without mutation.
        return RedirectResponse(url=_SETUP_URL, status_code=303)

    if "create_first_user" in form:
        return await _create_first_user_from_form(request, form)
    if "retry" in form:
        return _run_model_check_from_form(request)
    return RedirectResponse(url=_SETUP_URL, status_code=303)


async def _create_first_user_from_form(request: Request, form: Any) -> Response:
    """Create the first user from the posted form, then redirect to ``/setup``.

    On success the manifest advances to ``pending_model`` and the redirect
    re-renders the model-check context. On a validation/conflict error the
    first-user form is re-rendered with the submitted name preserved
    (interfaces §7).
    """
    from ..first_user import create_first_user
    from ..setup_state import SetupStateError
    from ..store import ProjectStore, ValidationError

    name = str(form.get("name", "") or "")
    credential = str(form.get("credential", "") or "")
    workspace_root = Path(request.app.state.workspace_root)
    manifest = try_read_manifest(workspace_root)
    workspace_id = manifest.workspace_id if manifest else ""
    expected_revision = manifest.revision if manifest else 0

    try:
        create_first_user(
            workspace_root,
            workspace_id=workspace_id,
            name=name,
            credential=credential,
            expected_revision=expected_revision,
            store=ProjectStore(workspace_root),
        )
    except (SetupStateError, ValidationError) as exc:
        projection = await _fetch_setup_status("", request=request)
        session_id, needs_cookie = _resolve_session_id(request)
        csrf_token = issue_for_session(
            session_id=session_id, revision=projection.get("revision", 0)
        )
        response = HTMLResponse(
            _render_pending_user(projection, csrf_token, name=name, error=str(exc))
        )
        if needs_cookie:
            _set_session_cookie(response, session_id)
        return response

    return RedirectResponse(url=_SETUP_URL, status_code=303)


def _run_model_check_from_form(request: Request) -> Response:
    """Run the real model check from the posted form, then redirect.

    On ``passed`` the manifest is atomically completed and the redirect targets
    the Workbench Projects activity. On ``failed``/``uncertain`` the latest
    non-secret diagnosis is persisted and the redirect returns to ``/setup`` so
    the page shows the actionable diagnosis and a Retry entry.
    """
    from .. import opencode_probe

    workspace_root = Path(request.app.state.workspace_root)
    manifest = try_read_manifest(workspace_root)
    if manifest is None or manifest.first_principal_id is None:
        return RedirectResponse(url=_SETUP_URL, status_code=303)

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
        return RedirectResponse(url=_PROJECTS_CONTINUE_URL, status_code=303)

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
    return RedirectResponse(url=_SETUP_URL, status_code=303)


# ---------------------------------------------------------------------------
# Composition root
# ---------------------------------------------------------------------------


def create_app() -> Starlette:
    """Return the two-context Setup page sub-app.

    Only ``/`` is registered for ``GET``; retired six-step routes naturally
    404. Used by the page unit tests; ``louke.web.app`` wires
    :func:`setup_root` directly at ``/setup`` (``GET`` + ``POST``) so the
    server-driven forms resolve without a trailing-slash redirect.
    """
    return Starlette(
        routes=[
            Route("/", endpoint=setup_root, methods=["GET"]),
        ],
    )


# ---------------------------------------------------------------------------
# Static assets (styles)
# ---------------------------------------------------------------------------

_SETUP_STYLES = """
:root { color-scheme: light; --ink:#1d1d1f; --muted:#6b6b6b; --line:#e3e3e3;
  --accent:#050505; --error:#b42318; }
* { box-sizing: border-box; }
body { margin:0; min-height:100dvh; display:grid; place-items:center;
  padding:24px; color:var(--ink);
  font:15px/1.5 Inter, ui-sans-serif, -apple-system, "Segoe UI", sans-serif;
  background:#f7f7f8; }
.setup-card { width:min(100%, 460px); padding:32px; background:#fff;
  border:1px solid var(--line); border-radius:14px; }
.setup-card h1 { margin:0 0 8px; font-size:20px; }
.setup-lede { margin:0 0 20px; color:var(--muted); }
.setup-field { display:block; margin-bottom:14px; font-weight:600; }
.setup-field input { display:block; width:100%; margin-top:6px; padding:10px 12px;
  font-weight:400; border:1px solid var(--line); border-radius:8px; }
button[type="submit"] { min-height:40px; padding:0 18px; border:0; border-radius:8px;
  color:#fff; background:var(--accent); font-weight:600; cursor:pointer; }
button[type="submit"]:disabled { opacity:.5; cursor:default; }
.setup-error { color:var(--error); }
.model-check { margin-bottom:18px; }
.model-state { margin:0 0 6px; }
.model-id { margin:0 0 12px; color:var(--muted); }
.diagnosis { margin:12px 0 0; padding:14px; border:1px solid var(--line);
  border-radius:10px; background:#fafafa; }
.diagnosis-row { display:grid; grid-template-columns:120px 1fr; gap:8px;
  padding:4px 0; }
.diagnosis-row dt { color:var(--muted); font-weight:600; }
.diagnosis-row dd { margin:0; overflow-wrap:anywhere; }
"""
