"""``/projects`` page sub-app: projects list, new-project wizard, detail (B3a).

Single inline-HTML page (no Jinja2). The sub-app talks to the upstream
``/api/projects/*`` and ``/api/runtime/*`` sub-apps via :mod:`httpx`. All
upstream calls go through module-level seams (``_fetch_*`` / ``_post_*``) so
tests can patch them without a live server, mirroring the Workbench page.

Routes (relative to the mount path ``/projects``):

    GET  /                         - list active, history, backlog projects.
    GET  /new                      - render the project-creation form.
    POST /new                      - preview a project (calls /api/projects/preview).
    POST /new/confirm/{preview_id} - confirm a preview and redirect to detail.
    GET  /{project_id}             - render the project detail page.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

#: Attribute on ``app.state`` holding the upstream API base URL.
_API_BASE_ATTR: str = "api_base"


def create_app(api_base: str = "") -> Starlette:
    """Return a self-contained Starlette sub-app for the ``/projects`` page.

    Args:
        api_base: Base URL for upstream API calls (e.g. ``"http://testserver"``).
            Empty string means same-origin.

    Returns:
        A Starlette application whose routes are relative to ``/projects``.
    """
    app = Starlette(routes=_routes())
    app.state.api_base = api_base
    return app


def _routes() -> list[Route]:
    """Return the routes for the projects page sub-app."""
    return [
        Route("/", endpoint=projects_index),
        Route("/new", endpoint=new_project_form, methods=["GET", "POST"]),
        Route(
            "/new/confirm/{preview_id}",
            endpoint=confirm_project,
            methods=["POST"],
        ),
        Route("/{project_id}", endpoint=project_detail),
    ]


# -- upstream seams ----------------------------------------------------------


async def _fetch_active(api_base: str) -> list[dict[str, Any]]:
    """Fetch the active-projects list from ``GET {api_base}/api/projects/active``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/active")
        resp.raise_for_status()
        return list(resp.json().get("items", []))


async def _fetch_history(api_base: str) -> list[dict[str, Any]]:
    """Fetch the history-projects list from ``GET {api_base}/api/projects/history``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/history")
        resp.raise_for_status()
        return list(resp.json().get("items", []))


async def _fetch_backlog(api_base: str) -> list[dict[str, Any]]:
    """Fetch the backlog list from ``GET {api_base}/api/projects/backlog``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/backlog")
        resp.raise_for_status()
        return list(resp.json().get("items", []))


async def _fetch_catalog(api_base: str) -> list[dict[str, Any]]:
    """Fetch the workflow catalog from ``GET {api_base}/api/projects/catalog``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/catalog")
        resp.raise_for_status()
        return list(resp.json().get("items", []))


async def _fetch_project(api_base: str, project_id: str) -> dict[str, Any]:
    """Fetch a single project from ``GET {api_base}/api/projects/{id}``.

    Raises:
        httpx.HTTPError: if the upstream call fails (including 404).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/{project_id}")
        resp.raise_for_status()
        return dict(resp.json())


async def _fetch_graph(api_base: str, project_id: str) -> dict[str, Any]:
    """Fetch the project's graph from ``GET {api_base}/api/projects/{id}/graph``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{api_base}/api/projects/{project_id}/graph")
        resp.raise_for_status()
        return dict(resp.json())


async def _fetch_events(
    api_base: str, run_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Fetch events from ``GET {api_base}/api/runtime/runs/{run_id}/events?limit=``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{api_base}/api/runtime/runs/{run_id}/events",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return list(resp.json().get("items", []))


async def _post_preview(
    api_base: str,
    *,
    story: str,
    release_version: str,
    definition_id: str,
    definition_version: str,
) -> dict[str, Any]:
    """POST a preview to ``{api_base}/api/projects/preview``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/api/projects/preview",
            json={
                "story": story,
                "release_version": release_version,
                "definition_id": definition_id,
                "definition_version": definition_version,
            },
        )
        resp.raise_for_status()
        return dict(resp.json())


async def _post_confirm(api_base: str, preview_id: str) -> dict[str, Any]:
    """POST a confirm to ``{api_base}/api/projects/confirm``.

    Raises:
        httpx.HTTPError: if the upstream call fails.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/api/projects/confirm",
            json={"preview_id": preview_id},
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


def _truncate(text: str, max_len: int = 12) -> str:
    """Return ``text`` truncated to ``max_len`` chars with a trailing ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# -- endpoints ---------------------------------------------------------------


async def projects_index(request: Request) -> Response:
    """GET /: render the projects list with Active, History and Backlog sections."""
    api_base = _api_base(request)
    active, err1 = await _safe_fetch(_fetch_active, api_base)
    history, err2 = await _safe_fetch(_fetch_history, api_base)
    backlog, err3 = await _safe_fetch(_fetch_backlog, api_base)
    error = err1 or err2 or err3
    return HTMLResponse(_render_index(active, history, backlog, error=error))


async def _safe_fetch(fetch: "Any", api_base: str) -> tuple[list[dict[str, Any]], str]:
    """Return ``(items, error)`` from ``fetch(api_base)``, never raising.

    Args:
        fetch: An async seam function taking ``api_base``.
        api_base: The upstream API base URL.

    Returns:
        A tuple of the fetched items (empty on failure) and an error string
        (empty on success).
    """
    try:
        return await fetch(api_base), ""
    except Exception as exc:
        return [], str(exc)


async def new_project_form(request: Request) -> Response:
    """GET /new: render the creation form. POST /new: preview and render confirm form."""
    api_base = _api_base(request)
    if request.method == "GET":
        return await _render_new_form(api_base)
    return await _handle_new_preview(api_base, await request.body())


async def _render_new_form(api_base: str) -> Response:
    """Render the new-project form, fetching the catalog for the select."""
    catalog, error = await _safe_fetch(_fetch_catalog, api_base)
    return HTMLResponse(_render_new(catalog, preview=None, error=error))


async def _handle_new_preview(api_base: str, body: bytes) -> Response:
    """POST /new: call upstream preview and re-render with the confirm form."""
    form = _parse_form(body)
    try:
        preview = await _post_preview(
            api_base,
            story=form.get("story", ""),
            release_version=form.get("release_version", ""),
            definition_id=form.get("workflow_definition_id", ""),
            definition_version=form.get("workflow_version", ""),
        )
    except Exception as exc:
        catalog, _ = await _safe_fetch(_fetch_catalog, api_base)
        return HTMLResponse(_render_new(catalog, preview=None, error=str(exc)))
    return HTMLResponse(_render_new([], preview=preview, error=""))


async def confirm_project(request: Request) -> Response:
    """POST /new/confirm/{preview_id}: confirm and redirect to the detail page."""
    api_base = _api_base(request)
    preview_id = request.path_params["preview_id"]
    try:
        project = await _post_confirm(api_base, preview_id)
    except Exception as exc:
        return HTMLResponse(
            _render_new([], preview=None, error=str(exc)), status_code=200
        )
    project_id = project.get("project_id", "")
    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


async def project_detail(request: Request) -> Response:
    """GET /{project_id}: render the project header, graph and events timeline."""
    api_base = _api_base(request)
    project_id = request.path_params["project_id"]
    try:
        project = await _fetch_project(api_base, project_id)
    except Exception as exc:
        return HTMLResponse(_render_detail_not_found(project_id, str(exc)))
    run_id = str(project.get("run_id", ""))
    graph: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    try:
        graph = await _fetch_graph(api_base, project_id)
    except Exception:
        pass
    try:
        events = await _fetch_events(api_base, run_id)
    except Exception:
        pass
    return HTMLResponse(_render_detail(project, graph, events))


# -- HTML renderers ----------------------------------------------------------


_PAGE_STYLE = """\
    body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; color: #111; }
    h1 { font-size: 24px; } h2 { font-size: 18px; margin-top: 24px; }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; margin: 8px 0; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 6px; background: #f3f4f6; font-size: 12px; }
    .badge-waiting_for_human { background: #fef3c7; color: #92400e; }
    .badge-active { background: #dcfce7; color: #166534; }
    .badge-completed { background: #dbeafe; color: #1e40af; }
    .muted { color: #6b7280; }
    .error { color: #b91c1c; margin: 12px 0; }
    form { margin: 16px 0; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; max-width: 480px; }
    label { display: block; margin: 8px 0 4px; font-size: 13px; }
    input, textarea, select { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; }
    button { margin-top: 12px; padding: 8px 14px; background: #111; color: white; border: 0; border-radius: 6px; cursor: pointer; }
    ul { list-style: none; padding: 0; } li { padding: 6px 0; border-bottom: 1px solid #f3f4f6; }
    .graph-node { padding: 4px 0; }
    .graph-completed { color: #166534; } .graph-current { color: #1e40af; font-weight: bold; }
    .graph-waiting_for_human { color: #92400e; } .graph-pending { color: #6b7280; }
"""


def _render_index(
    active: list[dict[str, Any]],
    history: list[dict[str, Any]],
    backlog: list[dict[str, Any]],
    *,
    error: str,
) -> str:
    """Return the inline HTML for the projects list page."""
    active_html = _section_cards(active, linkable=True) or _empty("active")
    history_html = _section_cards(history, linkable=True) or _empty("history")
    backlog_html = _section_backlog(backlog) or _empty("backlog")
    error_html = f'<div class="error">{_esc(error)}</div>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke projects</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>Projects <a class="badge" href="/projects/new">+ New</a></h1>
  {error_html}
  <section>
    <h2>Active</h2>
    {active_html}
  </section>
  <section>
    <h2>History</h2>
    {history_html}
  </section>
  <section>
    <h2>Backlog</h2>
    {backlog_html}
  </section>
</body>
</html>
"""


def _empty(section: str) -> str:
    """Return the empty-state message HTML for a section."""
    return f'<p class="muted">No {section} projects.</p>'


def _section_cards(projects: list[dict[str, Any]], *, linkable: bool) -> str:
    """Return the HTML for a list of project cards."""
    return "".join(_project_card(p, linkable=linkable) for p in projects)


def _project_card(project: dict[str, Any], *, linkable: bool) -> str:
    """Return the HTML card for a single project summary."""
    project_id = _esc(project.get("project_id", ""))
    name = _esc(project.get("name", ""))
    status = _esc(project.get("run_status", project.get("status", "")))
    current_step = _esc(project.get("current_step", ""))
    release_version = _esc(project.get("release_version", ""))
    workflow_definition_id = _esc(project.get("workflow_definition_id", ""))
    link = f'<a href="/projects/{project_id}">{name}</a>' if linkable else name
    return f"""<div class="card">
  <div>{link} <span class="badge">{_esc(status)}</span></div>
  <div class="muted">id: {_truncate(str(project_id))} | step: {current_step} | {release_version} | {workflow_definition_id}</div>
</div>"""


def _section_backlog(entries: list[dict[str, Any]]) -> str:
    """Return the HTML for the backlog section (no links)."""
    return "".join(_backlog_card(e) for e in entries)


def _backlog_card(entry: dict[str, Any]) -> str:
    """Return the HTML card for a single backlog entry."""
    story = _esc(entry.get("story", ""))
    release_version = _esc(entry.get("release_version", ""))
    workflow_definition_id = _esc(entry.get("workflow_definition_id", ""))
    return f"""<div class="card">
  <div>{story}</div>
  <div class="muted">{release_version} | {workflow_definition_id}</div>
</div>"""


def _render_new(
    catalog: list[dict[str, Any]], *, preview: dict[str, Any] | None, error: str
) -> str:
    """Return the inline HTML for the new-project form / preview."""
    error_html = f'<div class="error">{_esc(error)}</div>' if error else ""
    if preview is not None:
        return _render_preview(preview, error_html)
    catalog_options = "".join(
        f'<option value="{_esc(c.get("definition_id", ""))}">{_esc(c.get("label", c.get("definition_id", "")))}</option>'
        for c in catalog
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke new project</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>New project</h1>
  {error_html}
  <form method="post" action="/projects/new">
    <label for="story">Story</label>
    <textarea id="story" name="story" rows="4" required></textarea>
    <label for="release_version">Release version</label>
    <input id="release_version" name="release_version" type="text" placeholder="v0.12.0" required />
    <label for="workflow_definition_id">Workflow</label>
    <select id="workflow_definition_id" name="workflow_definition_id">
      {catalog_options}
    </select>
    <label for="workflow_version">Workflow version</label>
    <input id="workflow_version" name="workflow_version" type="text" value="1" required />
    <button type="submit">Preview</button>
  </form>
</body>
</html>
"""


def _render_preview(preview: dict[str, Any], error_html: str) -> str:
    """Return the inline HTML for the preview + confirm form."""
    preview_id = _esc(preview.get("preview_id", ""))
    excerpt = _esc(preview.get("story_excerpt", ""))
    release_version = _esc(preview.get("release_version", ""))
    definition_id = _esc(preview.get("workflow_definition_id", ""))
    definition_version = _esc(preview.get("workflow_version", ""))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke preview project</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>Preview</h1>
  {error_html}
  <div class="card">
    <div><strong>{excerpt}</strong></div>
    <div class="muted">{release_version} | {definition_id} v{definition_version}</div>
  </div>
  <form method="post" action="/projects/new/confirm/{preview_id}">
    <input type="hidden" name="preview_id" value="{preview_id}" />
    <button type="submit">Confirm</button>
  </form>
</body>
</html>
"""


def _render_detail(
    project: dict[str, Any], graph: dict[str, Any], events: list[dict[str, Any]]
) -> str:
    """Return the inline HTML for the project detail page."""
    project_id = _esc(project.get("project_id", ""))
    name = _esc(project.get("name", ""))
    status = _esc(project.get("status", ""))
    run_id = _esc(project.get("run_id", ""))
    release_version = _esc(project.get("release_version", ""))
    workflow_definition_id = _esc(project.get("workflow_definition_id", ""))
    current_step = _esc(graph.get("current_step", ""))
    graph_html = _render_graph(graph)
    events_html = _render_events(events) or '<p class="muted">No events.</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke {name}</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>{name}</h1>
  <p>id: {_truncate(str(project_id))} | run: {_truncate(str(run_id))} | {release_version} | {workflow_definition_id}</p>
  <p>status: <span class="badge">{_esc(status)}</span> | current step: <span class="badge">{current_step}</span></p>
  <section>
    <h2>Graph</h2>
    {graph_html}
  </section>
  <section>
    <h2>Events</h2>
    {events_html}
  </section>
</body>
</html>
"""


def _render_graph(graph: dict[str, Any]) -> str:
    """Return a simple ASCII-list rendering of the workflow graph nodes."""
    nodes = graph.get("nodes", [])
    if not nodes:
        return '<p class="muted">No graph available.</p>'
    items = "".join(_render_graph_node(n) for n in nodes)
    return f"<ul>{items}</ul>"


def _render_graph_node(node: dict[str, Any]) -> str:
    """Return the HTML list item for a single graph node."""
    step_id = _esc(node.get("step_id", ""))
    label = _esc(node.get("label", node.get("step_id", "")))
    state = _esc(node.get("state", ""))
    return f'<li class="graph-node graph-{state}">{label} <span class="muted">({step_id}, {state})</span></li>'


def _render_events(events: list[dict[str, Any]]) -> str:
    """Return the HTML list for the events timeline."""
    if not events:
        return ""
    items = "".join(_render_event(e) for e in events)
    return f"<ul>{items}</ul>"


def _render_event(event: dict[str, Any]) -> str:
    """Return the HTML list item for a single event."""
    event_type = _esc(event.get("type", ""))
    occurred_at = _esc(event.get("occurred_at", ""))
    sequence = _esc(event.get("sequence", ""))
    return f"<li>{occurred_at} #{sequence} {event_type}</li>"


def _render_detail_not_found(project_id: str, error: str) -> str:
    """Return the inline HTML for a not-found project detail page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke project not found</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>Project not found</h1>
  <div class="error">Project {_esc(project_id)} not found. {_esc(error)}</div>
  <p><a href="/projects">Back to projects</a></p>
</body>
</html>
"""
