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

Composition root: ``louke.web.app`` imports ``create_app`` and mounts it
at ``/setup`` (``app.py:82``, ``app.py:341``); it sets
``app.state.workspace_root`` on the returned instance so the page can read
the on-disk v2 Setup projection.

The page is server-rendered HTML with progressive enhancement: the form and
Retry controls submit through the public ``/api/setup/*`` JSON API (fetching
a fresh session-bound CSRF token first), then re-read ``/setup`` so the
two-context state always reflects the persisted manifest.
"""

from __future__ import annotations

import secrets
from html import escape
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ..auth import SESSION_COOKIE

#: Where a finished Setup sends the Human.
_PROJECTS_CONTINUE_URL = "/workbench?activity=projects"

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


def _session_id_for(request: Request) -> str:
    """Return a stable session identifier for CSRF binding.

    Mirrors ``louke.web.api.setup._session_id``: the opaque session cookie
    value when present, otherwise a transport fallback. The Setup page sets
    the cookie (see :func:`_ensure_session_cookie`) so the identifier stays
    stable across the browser requests that issue and redeem CSRF tokens.
    """
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        return cookie
    client = request.client
    if client is not None:
        return f"preauth:{client.host}:{client.port}"
    return "preauth:anonymous"


def _ensure_session_cookie(request: Request, response: Response) -> None:
    """Set an opaque pre-auth Setup session cookie when one is absent.

    The cookie gives the browser a stable session identity so the CSRF token
    issued by ``GET /api/setup/status`` and redeemed by the first-user /
    model-check mutations resolve to the same session. It carries no
    credential and is not an authenticated session; ``current_user`` fails
    closed on it until the first user rotates it (interfaces §1, §IF-SETUP-02).
    """
    if request.cookies.get(SESSION_COOKIE, ""):
        return
    response.set_cookie(
        SESSION_COOKIE,
        f"preauth.{secrets.token_hex(16)}",
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
    same projection the ``GET /api/setup/status`` endpoint returns and
    attaches a session-bound CSRF token.

    Args:
        api_base: Upstream API base URL (unused; the projection is read
            from the bound workspace).
        request: The current request, used to resolve the workspace root
            and session identity.

    Returns:
        The Setup projection dict (``workspace_id``, ``revision``,
        ``status``, ``first_user``, ``model_check``, ``available_actions``,
        ``continue_url``) plus a ``csrf_token``.
    """
    from ..csrf_middleware import issue_for_session
    from ..setup_projection import read as read_projection
    from ..setup_state import try_read_manifest
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

    body["csrf_token"] = issue_for_session(
        session_id=_session_id_for(request),
        revision=body.get("revision", 0),
    )
    return body


async def _post_first_user(
    api_base: str, *, name: str, credential: str
) -> dict[str, Any]:
    """IF-SETUP-02: Submit the first-user creation form to the backend API.

    Test seam; production calls ``POST /api/setup/first-user``. The page's
    browser flow performs this call client-side (so it can carry the live
    session cookie and a freshly issued CSRF token); this server-side seam
    is retained for contract symmetry and tooling that drives the API
    directly.

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
    parts = [f'<p class="model-state">Model check state: <strong>{escape(state)}</strong></p>']
    if model_id:
        parts.append(f'<p class="model-id">Model: {escape(model_id)}</p>')
    diagnosis = model_check.get("diagnosis")
    if state in ("failed", "uncertain") and isinstance(diagnosis, dict):
        parts.append(_diagnosis_html(diagnosis))
    return "".join(parts)


def _render_pending_user(projection: dict[str, Any]) -> str:
    """Render the first-user creation form (``pending_user`` context)."""
    revision = projection.get("revision", 0)
    csrf_token = projection.get("csrf_token", "") or ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up Louke</title>
<style>{_SETUP_STYLES}</style></head>
<body>
<main class="setup-card" data-setup-context="pending_user">
  <h1>Create the first user</h1>
  <p class="setup-lede">Louke needs one local human account to finish Setup.</p>
  <form id="setup-first-user-form" action="/api/setup/first-user" method="post"
        data-revision="{escape(str(revision))}" data-csrf="{escape(csrf_token, quote=True)}">
    <label class="setup-field">Name
      <input name="name" type="text" autocomplete="username" required>
    </label>
    <label class="setup-field">Credential
      <input name="credential" type="password" autocomplete="new-password" required>
    </label>
    <button type="submit" name="create_first_user">Create first user</button>
    <p class="setup-error" role="alert" hidden></p>
  </form>
</main>
<script>{_FIRST_USER_SCRIPT}</script>
</body></html>"""


def _render_pending_model(projection: dict[str, Any]) -> str:
    """Render the OpenCode model-check view (``pending_model`` context)."""
    revision = projection.get("revision", 0)
    csrf_token = projection.get("csrf_token", "") or ""
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
  <form id="setup-model-check-form" data-revision="{escape(str(revision))}"
        data-csrf="{escape(csrf_token, quote=True)}">
    <button type="submit" name="retry" value="retry">Retry model check</button>
    <p class="setup-status" role="status" hidden></p>
    <p class="setup-error" role="alert" hidden></p>
  </form>
</main>
<script>{_MODEL_CHECK_SCRIPT}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


async def setup_root(request: Request) -> Response:
    """IF-SETUP-01: Render the two-context Setup page at ``/``.

    - ``pending_user`` -> 200 HTML with the first-user creation form.
    - ``pending_model`` -> 200 HTML with the model-check view and a Retry
      entry; a failed/uncertain check shows ``object``, ``known_facts``,
      ``impact`` and ``recovery_url``.
    - ``complete`` -> 303 redirect to ``/workbench?activity=projects``.

    The handler reads the v2 manifest projection (via ``_fetch_setup_status``)
    and renders the matching context. No retired six-step routes or markers
    (``Runtime dependencies``, ``/setup/repository/``, etc.) are rendered.
    """
    projection = await _fetch_setup_status("", request=request)
    status = projection.get("status", "")

    if status == "complete":
        continue_url = projection.get("continue_url") or _PROJECTS_CONTINUE_URL
        return RedirectResponse(url=continue_url, status_code=303)

    if status == "pending_model":
        response: Response = HTMLResponse(_render_pending_model(projection))
    else:
        response = HTMLResponse(_render_pending_user(projection))

    _ensure_session_cookie(request, response)
    return response


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


# ---------------------------------------------------------------------------
# Static assets (styles + progressive-enhancement scripts)
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
.setup-status { color:var(--muted); }
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

_FIRST_USER_SCRIPT = """
(function () {
  const form = document.getElementById('setup-first-user-form');
  if (!form) return;
  const errorEl = form.querySelector('.setup-error');
  const submit = form.querySelector('button[type="submit"]');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    submit.disabled = true;
    const name = form.querySelector('input[name="name"]').value;
    const credential = form.querySelector('input[name="credential"]').value;
    try {
      const status = await fetch('/api/setup/status').then((r) => r.json());
      const resp = await fetch('/api/setup/first-user', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Louke-CSRF': status.csrf_token || '',
          'Idempotency-Key': (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
        },
        body: JSON.stringify({
          name: name,
          credential: credential,
          expected_revision: status.revision || 0,
        }),
      });
      if (resp.ok) {
        window.location.reload();
        return;
      }
      const detail = await resp.json().catch(() => ({}));
      errorEl.textContent = detail.message || detail.error || ('Request failed (' + resp.status + ')');
      errorEl.hidden = false;
    } catch (err) {
      errorEl.textContent = 'Could not reach the server.';
      errorEl.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
})();
"""

_MODEL_CHECK_SCRIPT = """
(function () {
  const form = document.getElementById('setup-model-check-form');
  if (!form) return;
  const errorEl = form.querySelector('.setup-error');
  const statusEl = form.querySelector('.setup-status');
  const submit = form.querySelector('button[type="submit"]');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    statusEl.hidden = false;
    statusEl.textContent = 'Checking model…';
    submit.disabled = true;
    try {
      const status = await fetch('/api/setup/status').then((r) => r.json());
      const resp = await fetch('/api/setup/model-checks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Louke-CSRF': status.csrf_token || '',
          'Idempotency-Key': (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
        },
        body: JSON.stringify({ expected_revision: status.revision || 0 }),
      });
      const check = await resp.json().catch(() => ({}));
      if (resp.ok && check.state === 'passed') {
        window.location.href = check.continue_url || '/workbench?activity=projects';
        return;
      }
      window.location.reload();
    } catch (err) {
      errorEl.textContent = 'Could not reach the server.';
      errorEl.hidden = false;
      statusEl.hidden = true;
      submit.disabled = false;
    }
  });
})();
"""
