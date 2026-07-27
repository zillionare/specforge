"""``/migration`` page sub-app: legacy workspace adoption wizard (B3c).

Single inline-HTML page (no Jinja2). Renders four sections:

- **Preview**: a form (``workspace_path``) that calls upstream
  ``GET /api/migration/preview`` and re-renders with the categorized preview
  (additions, conversions, preserved, conflicts, unsupported), the recommended
  mode and a mode-override radio.
- **Confirm**: a form (``workspace_path`` + ``mode``) that calls upstream
  ``POST /api/migration/confirm`` and re-renders with an "applied" message.
- **Rollback**: a form (``workspace_path``) that calls upstream
  ``POST /api/migration/rollback`` and re-renders with a "rolled back" message.
- **Legacy**: a read-only history entry lookup form.

Upstream HTTP calls go through module-level seams (``_fetch_preview``,
``_post_confirm``, ``_post_rollback``) so tests can patch them without a live
    server, mirroring the Login and Workbench surfaces.

Routes (relative to the sub-app mount root)::

    GET  /         - migration page shell with all four sections.
    POST /preview  - generate a preview and re-render.
    POST /confirm  - confirm a migration and re-render.
    POST /rollback - roll back a migration and re-render.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

#: Attribute on ``app.state`` holding the upstream API base URL.
_API_BASE_ATTR: str = "api_base"

#: Attribute on ``app.state`` holding the latest preview result (dict or None).
_PREVIEW_ATTR: str = "last_preview"

#: Attribute on ``app.state`` holding the latest confirm result message.
_CONFIRM_MSG_ATTR: str = "confirm_message"

#: Attribute on ``app.state`` holding the latest rollback result message.
_ROLLBACK_MSG_ATTR: str = "rollback_message"

#: Attribute on ``app.state`` holding the latest user-facing error.
_ERROR_ATTR: str = "page_error"


def create_app(api_base: str = "") -> Starlette:
    """Return a self-contained Starlette sub-app for the migration page.

    Args:
        api_base: Base URL for upstream API calls (e.g.
            ``"http://testserver"``). Empty string means same-origin.

    Returns:
        A Starlette application whose routes are relative to the mount root.
        ``app.state.api_base`` holds the upstream base URL.
    """
    app = Starlette(routes=_routes())
    app.state.api_base = api_base
    return app


def _routes() -> list[Route]:
    """Return the routes for the migration page sub-app."""
    return [
        Route("/", endpoint=migration_index),
        Route("/preview", endpoint=preview, methods=["POST"]),
        Route("/confirm", endpoint=confirm, methods=["POST"]),
        Route("/rollback", endpoint=rollback, methods=["POST"]),
    ]


# -- upstream seams ----------------------------------------------------------


async def _fetch_preview(api_base: str, workspace_path: str) -> dict[str, Any]:
    """Fetch a migration preview from ``GET {api_base}/api/migration/preview``.

    Args:
        api_base: Upstream API base URL.
        workspace_path: The workspace root to preview.

    Returns:
        The preview dict with keys ``additions``, ``conversions``,
        ``preserved``, ``conflicts``, ``unsupported``, ``recommended_mode``,
        ``available_modes`` and ``old_bytes_modified``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{api_base}/api/migration/preview",
            params={"workspace_path": workspace_path},
        )
        resp.raise_for_status()
        return dict(resp.json())


async def _post_confirm(
    api_base: str, workspace_path: str, mode: str
) -> dict[str, Any]:
    """POST a migration confirm to ``{api_base}/api/migration/confirm``.

    Args:
        api_base: Upstream API base URL.
        workspace_path: The workspace root being confirmed.
        mode: The migration mode (``"local"`` or ``"global"``).

    Returns:
        The confirm result dict with ``workspace_path``, ``committed`` and
        ``has_restore_point``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/api/migration/confirm",
            json={"workspace_path": workspace_path, "mode": mode},
        )
        resp.raise_for_status()
        return dict(resp.json())


async def _post_rollback(api_base: str, workspace_path: str) -> dict[str, Any]:
    """POST a migration rollback to ``{api_base}/api/migration/rollback``.

    Args:
        api_base: Upstream API base URL.
        workspace_path: The workspace root being rolled back.

    Returns:
        The rollback result dict with ``workspace_path`` and ``rolled_back``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/api/migration/rollback",
            json={"workspace_path": workspace_path},
        )
        resp.raise_for_status()
        return dict(resp.json())


# -- helpers -----------------------------------------------------------------


def _api_base(request: Request) -> str:
    """Return the upstream API base URL stored on ``app.state``."""
    return str(getattr(request.app.state, _API_BASE_ATTR, ""))


def _parse_form(body: bytes) -> dict[str, str]:
    """Parse a urlencoded form body into a flat ``{field: value}`` dict.

    Avoids python-multipart; we only handle application/x-www-form-urlencoded.
    """
    pairs = parse_qs(body.decode("utf-8", errors="replace"))
    return {key: (vals[0] if vals else "") for key, vals in pairs.items()}


def _esc(text: Any) -> str:
    """Return an HTML-escaped version of ``text``."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# -- endpoints ---------------------------------------------------------------


async def migration_index(request: Request) -> Response:
    """GET /: render the migration page shell with all four sections.

    Reads the latest preview / confirm / rollback / error values stashed on
    ``app.state`` by the POST handlers so a re-render shows the latest result.
    """
    return _render_page(request.app.state)


async def preview(request: Request) -> Response:
    """POST /preview: call upstream preview and re-render the page.

    On success, stashes the preview dict on ``app.state`` so the re-rendered
    page shows the categorized preview and mode selector. On failure, stashes
    a user-facing error message. Always returns status 200.
    """
    api_base = _api_base(request)
    workspace_path = _parse_form(await request.body()).get("workspace_path", "")
    state = request.app.state
    try:
        result = await _fetch_preview(api_base, workspace_path)
    except Exception as exc:
        _reset_results(state)
        setattr(state, _ERROR_ATTR, str(exc))
        return _render_page(state)
    setattr(state, _PREVIEW_ATTR, result)
    setattr(state, _CONFIRM_MSG_ATTR, "")
    setattr(state, _ROLLBACK_MSG_ATTR, "")
    setattr(state, _ERROR_ATTR, "")
    return _render_page(state)


async def confirm(request: Request) -> Response:
    """POST /confirm: call upstream confirm and re-render with applied message.

    Re-renders the full page (including the latest preview, if any) so the
    user sees the applied message alongside the forms. Always returns 200.
    """
    api_base = _api_base(request)
    form = _parse_form(await request.body())
    workspace_path = form.get("workspace_path", "")
    mode = form.get("mode", "local")
    state = request.app.state
    try:
        await _post_confirm(api_base, workspace_path, mode)
    except Exception as exc:
        setattr(state, _CONFIRM_MSG_ATTR, "")
        setattr(state, _ERROR_ATTR, str(exc))
        return _render_page(state)
    message = f"Migration applied for {workspace_path} (mode={mode})."
    setattr(state, _CONFIRM_MSG_ATTR, message)
    setattr(state, _ERROR_ATTR, "")
    return _render_page(state)


async def rollback(request: Request) -> Response:
    """POST /rollback: call upstream rollback and re-render with rolled-back message.

    Re-renders the full page so the user sees the rolled-back message alongside
    the forms. Always returns 200.
    """
    api_base = _api_base(request)
    workspace_path = _parse_form(await request.body()).get("workspace_path", "")
    state = request.app.state
    try:
        await _post_rollback(api_base, workspace_path)
    except Exception as exc:
        setattr(state, _ROLLBACK_MSG_ATTR, "")
        setattr(state, _ERROR_ATTR, str(exc))
        return _render_page(state)
    message = f"Migration rolled back for {workspace_path}."
    setattr(state, _ROLLBACK_MSG_ATTR, message)
    setattr(state, _ERROR_ATTR, "")
    return _render_page(state)


def _render_page(state: Any) -> HTMLResponse:
    """Render the page from the latest preview/confirm/rollback/error on state."""
    return HTMLResponse(
        _render(
            preview=getattr(state, _PREVIEW_ATTR, None),
            confirm_message=getattr(state, _CONFIRM_MSG_ATTR, ""),
            rollback_message=getattr(state, _ROLLBACK_MSG_ATTR, ""),
            error=getattr(state, _ERROR_ATTR, ""),
        )
    )


def _reset_results(state: Any) -> None:
    """Clear all stashed result attributes on ``state`` (keeps error separate)."""
    setattr(state, _PREVIEW_ATTR, None)
    setattr(state, _CONFIRM_MSG_ATTR, "")
    setattr(state, _ROLLBACK_MSG_ATTR, "")


# -- HTML renderers ----------------------------------------------------------


_PAGE_STYLE = """\
    body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; color: #111; }
    h1 { font-size: 24px; } h2 { font-size: 18px; margin-top: 24px; }
    .muted { color: #6b7280; }
    .error { color: #b91c1c; margin: 12px 0; }
    .ok { color: #166534; margin: 12px 0; }
    form { margin: 16px 0; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; max-width: 480px; }
    label { display: block; margin: 8px 0 4px; font-size: 13px; }
    input, select { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; }
    button { margin-top: 12px; padding: 8px 14px; background: #111; color: white; border: 0; border-radius: 6px; cursor: pointer; }
    ul { list-style: none; padding: 0; } li { padding: 6px 0; border-bottom: 1px solid #f3f4f6; }
"""


def _render(
    *,
    preview: dict[str, Any] | None,
    confirm_message: str,
    rollback_message: str,
    error: str,
) -> str:
    """Return the inline HTML for the migration page shell.

    Args:
        preview: The latest preview dict, or ``None`` when no preview exists.
        confirm_message: The latest confirm result message (empty if none).
        rollback_message: The latest rollback result message (empty if none).
        error: A user-facing error message (empty if none).
    """
    error_html = f'<div class="error">{_esc(error)}</div>' if error else ""
    preview_section = _render_preview_section(preview)
    confirm_section = _render_confirm_section(confirm_message)
    rollback_section = _render_rollback_section(rollback_message)
    legacy_section = _render_legacy_section()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke migration</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>Legacy workspace migration</h1>
  {error_html}
  {preview_section}
  {confirm_section}
  {rollback_section}
  {legacy_section}
</body>
</html>
"""


def _render_preview_section(preview: dict[str, Any] | None) -> str:
    """Return the ``<section>`` for the preview form and categorized result.

    Args:
        preview: The latest preview dict, or ``None`` when no preview exists.
    """
    result_html = _render_preview_result(preview) if preview else ""
    return f"""<section class="preview">
    <h2>Preview</h2>
    <form method="post" action="/preview">
      <label for="workspace_path">Workspace path</label>
      <input id="workspace_path" name="workspace_path" type="text" required />
      <button type="submit">Generate preview</button>
    </form>
    {result_html}
  </section>"""


def _render_preview_result(preview: dict[str, Any]) -> str:
    """Return the categorized preview result block plus the mode selector.

    Renders each category (additions, conversions, preserved, conflicts,
    unsupported) as a list, then the recommended mode and a mode-override
    radio bound to the confirm form.
    """
    recommended = _esc(preview.get("recommended_mode", ""))
    available = preview.get("available_modes", ())
    mode_radios = "".join(_render_mode_radio(str(m), recommended) for m in available)
    categories = "".join(
        _render_category(label, preview.get(key, ()))
        for key, label in _PREVIEW_CATEGORIES
    )
    return f"""<div class="preview-result">
      {categories}
      <p>Recommended mode: <strong>{recommended}</strong></p>
      <div class="mode-select">
        <span>Mode override:</span>
        {mode_radios}
      </div>
    </div>"""


#: Ordered (preview-key, display-label) pairs for the categorized result.
_PREVIEW_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("additions", "Additions"),
    ("conversions", "Conversions"),
    ("preserved", "Preserved"),
    ("conflicts", "Conflicts"),
    ("unsupported", "Unsupported"),
)


def _render_category(label: str, items: Any) -> str:
    """Return a category block with a heading and a list of item names."""
    item_list = list(items) if items else []
    if not item_list:
        return f'<p class="muted">{_esc(label)}: none</p>'
    entries = "".join(f"<li>{_esc(it)}</li>" for it in item_list)
    return f"<div><h3>{_esc(label)}</h3><ul>{entries}</ul></div>"


def _render_mode_radio(mode: str, recommended: str) -> str:
    """Return a radio input for a mode, checked when it is recommended."""
    checked = " checked" if mode == recommended else ""
    return (
        f'<label><input type="radio" name="mode" value="{_esc(mode)}"'
        f"{checked} /> {_esc(mode)}</label>"
    )


def _render_confirm_section(confirm_message: str) -> str:
    """Return the ``<section>`` for the confirm form and applied message."""
    msg_html = (
        f'<div class="ok">Migration applied: {_esc(confirm_message)}</div>'
        if confirm_message
        else ""
    )
    return f"""<section class="confirm">
    <h2>Confirm</h2>
    <form method="post" action="/confirm">
      <label for="confirm_workspace_path">Workspace path</label>
      <input id="confirm_workspace_path" name="workspace_path" type="text" required />
      <label for="confirm_mode">Mode</label>
      <select id="confirm_mode" name="mode">
        <option value="local">local</option>
        <option value="global">global</option>
      </select>
      <button type="submit">Confirm migration</button>
    </form>
    {msg_html}
  </section>"""


def _render_rollback_section(rollback_message: str) -> str:
    """Return the ``<section>`` for the rollback form and rolled-back message."""
    msg_html = (
        f'<div class="ok">Rolled back: {_esc(rollback_message)}</div>'
        if rollback_message
        else ""
    )
    return f"""<section class="rollback">
    <h2>Rollback</h2>
    <form method="post" action="/rollback">
      <label for="rollback_workspace_path">Workspace path</label>
      <input id="rollback_workspace_path" name="workspace_path" type="text" required />
      <button type="submit">Roll back migration</button>
    </form>
    {msg_html}
  </section>"""


def _render_legacy_section() -> str:
    """Return the read-only legacy history lookup ``<section>``."""
    return """<section class="legacy">
    <h2>Legacy history</h2>
    <form method="get" action="/legacy">
      <label for="project_id">Project id</label>
      <input id="project_id" name="project_id" type="text" required />
      <button type="submit">Look up legacy entry</button>
    </form>
    <p class="muted">Legacy entries are read-only.</p>
  </section>"""
