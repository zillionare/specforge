from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route

from .auth import (
    SESSION_COOKIE,
    AuthenticatedUser,
    authenticate_user,
    current_user,
    issue_session_cookie,
    register_user,
)
from .bindings import get_bindings_payload, save_bindings_payload
from .documents import (
    get_doc_payload,
    get_wiki_payload,
    mutate_discussion,
    render_preview_payload,
    save_doc_payload,
    save_wiki_payload,
    toggle_status_payload,
)
from .events import EventBroker
from .store import ConflictError, ProjectStore, ValidationError
from .setup_gate import SetupGateMiddleware

from .api.projects import create_app as _create_projects_app
from .api.runtime import create_app as _create_runtime_app
from .api.gates import create_app as _create_gates_app
from .api.bindings import create_app as _create_bindings_app
from .api.opencode import create_app as _create_opencode_app
from .api.project_status import checkpoint_action, checkpoint_detail, project_status
from .api.readiness import create_app as _create_readiness_app
from .api.setup import create_app as _create_setup_app
from .api.migration import create_app as _create_migration_app
from .api.security import create_app as _create_security_app
from .api.discussions import create_app as _create_discussions_app
from .api.v14_releases import (
    confirm_release,
    foundation_status,
    preview_release,
    recheck_release,
    release_status,
)
from .api.v14_scribe import (
    current_project,
    run_action,
    story_artifact,
    story_page,
    task_messages,
    task_read,
    task_reconcile,
    task_reply,
    task_retry,
)
from .api._runtime_store import build_run_store
from louke.runtime.workflow_graph import WorkflowGraphBuilder
from louke.runtime.store import RunNotFoundError, WorkflowRun, WorkflowRunStore

from .pages.setup import setup_root as _setup_page_root
from .pages.projects import create_app as _create_projects_page_app
from .pages.gates import (
    gate_decide as gates_page_decide,
    gate_detail as gates_page_detail,
    gates_index as gates_page_index,
)
from .pages.runs import (
    run_command as runs_page_command,
    run_detail as runs_page_detail,
)
from .pages.migration import create_app as _create_migration_page_app
from .pages.workbench import workbench, projects_compat, project_detail_compat
from .pages.release import release_new_page
from .api.files import files as end_user_files
from .runs.badges import status_badge

projects_app = _create_projects_app()
runtime_app = _create_runtime_app()
gates_app = _create_gates_app()
bindings_app = _create_bindings_app()
opencode_app = _create_opencode_app()
migration_app = _create_migration_app()
security_app = _create_security_app()
discussions_app = _create_discussions_app()

projects_page_app = _create_projects_page_app()
migration_page_app = _create_migration_page_app()


def create_app(
    project_root: str | Path | None = None,
    *,
    setup_only: bool = False,
    mode: str | None = None,
    allowed_origin: str | None = None,
) -> Starlette:
    """Create the Web application for one project workspace.

    Args:
        project_root: Workspace root. Defaults to the current directory.
        setup_only: Whether the root route should redirect to setup.
        mode: Explicit Runtime mode, including Louke-only
            ``development_bootstrap``.
        allowed_origin: Trusted v0.14 mutation origin. If omitted, the
            ``LOUKE_ALLOWED_ORIGIN`` environment setting is used.

    Returns:
        A configured Starlette application.

    Raises:
        ReleaseContractError: If the selected Runtime contract is invalid.
    """
    if project_root is None:
        project_root = Path.cwd()
    readiness_app = _create_readiness_app(project_root)
    setup_app = _create_setup_app(project_root)
    store = ProjectStore(Path(project_root))
    project_runtime_store = build_run_store(
        str(Path(project_root) / ".louke" / "project" / "runtime.sqlite3"),
        workspace_root=project_root,
        mode=mode,
    )
    for sub_app in (projects_app, runtime_app, gates_app, bindings_app):
        sub_app.state._state.clear()
        sub_app.state.runtime_run_store = project_runtime_store
        sub_app.state.v12_run_store = project_runtime_store
    broker = EventBroker()
    app = Starlette(
        debug=False,
        routes=[
            Route("/assets/{asset_path:path}", endpoint=asset_file),
            Route("/login", endpoint=login_page),
            Route("/", endpoint=setup_home_redirect, methods=["GET"]),
            Route("/workbench", endpoint=workbench, methods=["GET"]),
            Route("/models", endpoint=models_page),
            Route("/wiki", endpoint=wiki_index_page),
            Route("/wiki/{page:path}", endpoint=wiki_editor_page),
            Route("/docs/{spec_id:str}/{doc_name:str}", endpoint=doc_editor_page),
            Route("/health", endpoint=health),
            Route("/api/auth/register", endpoint=api_auth_register, methods=["POST"]),
            Route("/api/auth/login", endpoint=api_auth_login, methods=["POST"]),
            Route("/api/auth/logout", endpoint=api_auth_logout, methods=["POST"]),
            Route(
                "/api/v14/releases/preview", endpoint=preview_release, methods=["POST"]
            ),
            Route("/api/releases/preview", endpoint=preview_release, methods=["POST"]),
            Route(
                "/api/v14/releases/confirm", endpoint=confirm_release, methods=["POST"]
            ),
            Route("/api/releases/confirm", endpoint=confirm_release, methods=["POST"]),
            Route(
                "/api/v14/releases/requests/{request_id}/foundation",
                endpoint=foundation_status,
            ),
            Route(
                "/api/releases/requests/{request_id}/foundation",
                endpoint=foundation_status,
            ),
            Route(
                "/api/v14/releases/requests/{request_id}/recheck",
                endpoint=recheck_release,
                methods=["POST"],
            ),
            Route(
                "/api/releases/requests/{request_id}/recheck",
                endpoint=recheck_release,
                methods=["POST"],
            ),
            Route(
                "/api/v14/releases/requests/{request_id}",
                endpoint=release_status,
            ),
            Route("/api/releases/requests/{request_id}", endpoint=release_status),
            Route(
                "/api/v14/projects/{project_id}/current",
                endpoint=current_project,
            ),
            Route(
                "/api/v14/runs/{run_id}/actions",
                endpoint=run_action,
                methods=["POST"],
            ),
            Route(
                "/api/v14/runs/{run_id}/artifacts/{kind}",
                endpoint=story_artifact,
            ),
            Route(
                "/api/v14/runs/{run_id}/tasks/{task_id}",
                endpoint=task_read,
            ),
            Route(
                "/api/v14/runs/{run_id}/tasks/{task_id}/messages",
                endpoint=task_messages,
            ),
            Route(
                "/api/v14/runs/{run_id}/tasks/{task_id}/messages",
                endpoint=task_reply,
                methods=["POST"],
            ),
            Route(
                "/api/v14/runs/{run_id}/tasks/{task_id}/reconcile",
                endpoint=task_reconcile,
                methods=["POST"],
            ),
            Route(
                "/api/v14/runs/{run_id}/tasks/{task_id}/retry",
                endpoint=task_retry,
                methods=["POST"],
            ),
            Route("/api/bindings", endpoint=api_bindings, methods=["GET", "PUT"]),
            Route("/api/wiki", endpoint=api_wiki_index, methods=["GET"]),
            Route("/api/wiki/refresh", endpoint=api_wiki_refresh, methods=["POST"]),
            Route(
                "/api/wiki/{page:path}", endpoint=api_wiki_page, methods=["GET", "PUT"]
            ),
            Route(
                "/api/docs/{spec_id:str}/{doc_name:str}",
                endpoint=api_doc,
                methods=["GET", "PUT"],
            ),
            Route(
                "/api/docs/{spec_id:str}/{doc_name:str}/toggle-status",
                endpoint=api_toggle_status,
                methods=["POST"],
            ),
            Route("/api/specs", endpoint=api_specs, methods=["GET"]),
            Route("/api/files", endpoint=end_user_files, methods=["GET", "POST"]),
            Route(
                "/api/ui/dev-docs/tree", endpoint=api_ui_devdocs_tree, methods=["GET"]
            ),
            Route(
                "/api/ui/settings/runtime",
                endpoint=api_ui_settings_runtime,
                methods=["GET"],
            ),
            Route(
                "/api/ui/wiki/{page:path}", endpoint=api_ui_wiki_page, methods=["GET"]
            ),
            Route("/api/render", endpoint=api_render, methods=["POST"]),
            Route("/api/ui/runs", endpoint=api_ui_runs, methods=["GET"]),
            Route(
                "/api/ui/runs/{run_id}/graph",
                endpoint=api_ui_run_graph,
                methods=["GET"],
            ),
            Route(
                "/api/ui/runs/{run_id}/stages/{stage_id}/artifact",
                endpoint=api_ui_artifact,
                methods=["GET"],
            ),
            Route(
                "/api/discussions/mutate",
                endpoint=api_discussion_mutate,
                methods=["POST"],
            ),
            Route("/api/events", endpoint=api_events, methods=["GET"]),
            Route(
                "/api/projects/{project_id}/status",
                endpoint=project_status,
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/status/checkpoints/{checkpoint_id}",
                endpoint=checkpoint_detail,
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/status/checkpoints/{checkpoint_id}/actions/{action_id}",
                endpoint=checkpoint_action,
                methods=["POST"],
            ),
            # === v0.12 mounts ===
            # Mount order matters: Starlette matches Mounts in declaration order
            # and a wider prefix shadows any longer prefix declared after it.
            # ``/api/runtime/bindings`` MUST precede ``/api/runtime`` or every
            # bindings request is handed to the runtime sub-app (which has no
            # ``bindings`` internal route) and returns 404. See #176.
            Mount("/api/projects", app=projects_app),
            Mount("/api/runtime/bindings", app=bindings_app),
            Mount("/api/runtime", app=runtime_app),
            Mount("/api/gates", app=gates_app),
            Mount("/api/opencode", app=opencode_app),
            Mount("/api/readiness", app=readiness_app),
            Mount("/api/setup", app=setup_app),
            Mount("/api/migration", app=migration_app),
            Mount("/api/security", app=security_app),
            Mount("/api/v12/discussions", app=discussions_app),
            # === v0.12 page sub-apps ===
            # setup/projects/migration use relative internal routes -> mount at
            # their prefix. gates/runs use full-prefix internal routes (their
            # ``{project_id}``/``{run_id}`` path params cannot live in a Mount
            # path), so their routes are registered directly here. The gates
            # routes must precede ``Mount("/projects", ...)`` because that Mount
            # would otherwise match ``/projects/{id}/gates`` at the prefix level
            # and return 404 (no matching internal route).
            Route("/projects/{project_id}/gates", endpoint=gates_page_index),
            Route(
                "/projects/{project_id}/gates/{gate_id}",
                endpoint=gates_page_detail,
            ),
            Route(
                "/projects/{project_id}/gates/{gate_id}/decide",
                endpoint=gates_page_decide,
                methods=["POST"],
            ),
            Route(
                "/projects/{project_id}/requirements/story",
                endpoint=story_page,
            ),
            Route("/projects/new", endpoint=release_new_page, methods=["GET"]),
            # IF-COMPAT-01: legacy /projects and /projects/{id} redirect to
            # the canonical Workbench Projects activity.
            Route("/projects", endpoint=projects_compat, methods=["GET"]),
            Route(
                "/projects/{project_id}",
                endpoint=project_detail_compat,
                methods=["GET"],
            ),
            Route("/runs/{run_id}", endpoint=runs_page_detail),
            Route(
                "/runs/{run_id}/command",
                endpoint=runs_page_command,
                methods=["POST"],
            ),
            # The Setup page is wired as a plain Route (not a Mount) so the
            # canonical ``/setup`` URL resolves without a trailing-slash
            # redirect; the Setup journeys assert ``/setup`` exactly. It handles
            # GET (render) and POST (server-driven first-user / model-check
            # forms). ``setup_root`` reads ``app.state.workspace_root``.
            Route("/setup", endpoint=_setup_page_root, methods=["GET", "POST"]),
            Mount("/projects", app=projects_page_app),
            Mount("/migration", app=migration_page_app),
        ],
    )
    app.state.store = store
    app.state.v12_run_store = project_runtime_store
    app.state.v14_allowed_origin = allowed_origin or os.environ.get(
        "LOUKE_ALLOWED_ORIGIN", ""
    )
    app.state.workspace_root = Path(project_root).resolve()
    app.add_middleware(SetupGateMiddleware, workspace_root=Path(project_root).resolve())
    from louke.runtime.foundation_adapter import ShellFoundationAdapter
    from louke.runtime.release_entry import ReleaseEntryService
    from louke.runtime.scribe_entry import ScribeEntryService
    from louke.runtime.story_entry import StoryEntryService

    project_info = store.project_info().get("project", {})
    workspace_id = str(project_info.get("project") or project_info.get("repo") or "")
    foundation_adapter = ShellFoundationAdapter(
        project_root,
        spec_id=str(
            project_info.get("contract_bundle_entry_spec")
            or "v0.14-001-workflow-reflow-spec"
        ),
    )
    scribe_entry = ScribeEntryService(
        project_runtime_store,
        workspace_root=project_root,
    )
    story_entry = StoryEntryService(
        project_runtime_store,
        foundation_adapter,
        scribe_entry=scribe_entry,
    )
    app.state.v14_release_entry = ReleaseEntryService(
        project_runtime_store,
        foundation_adapter,
        workspace_id=workspace_id,
        story_entry=story_entry,
    )
    app.state.v14_story_entry = story_entry
    app.state.v14_scribe_entry = scribe_entry
    app.state.broker = broker
    app.state.setup_only = setup_only
    return app


async def health(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.store.health_payload())


async def api_ui_settings_runtime(request: Request) -> JSONResponse:
    """Expose the server's runtime identity for the Settings read model."""
    from louke import __version__
    from louke.__main__ import _runtime_mode

    mode = _runtime_mode()
    return JSONResponse(
        {
            "version": __version__,
            "mode": mode,
            "display": f"{__version__} ({mode})",
        }
    )


async def asset_file(request: Request) -> Response:
    asset_name = request.path_params["asset_path"]
    asset_path = (_assets_dir() / asset_name).resolve()
    assets_root = _assets_dir().resolve()
    if (
        not str(asset_path).startswith(str(assets_root))
        or not asset_path.exists()
        or not asset_path.is_file()
    ):
        return JSONResponse({"error": "asset not found"}, status_code=404)
    return FileResponse(asset_path)


async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    store: ProjectStore = request.app.state.store
    user = _current_user(request)
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    next_path = request.query_params.get("next") or "/"
    return HTMLResponse(
        _login_shell(
            lang=_ui_language(request),
            next_path=next_path,
            has_users=bool(store.list_users()),
        )
    )


async def setup_home_redirect(request: Request) -> Response:
    """GET /: redirect to Setup, active Project, or Projects activity.

    v0.14-004: uses the v2 Setup manifest and ``entry_resolver`` to
    pick the canonical destination. When Setup is incomplete, the
    user is redirected to ``/setup``. When Setup is complete, the
    user lands on the active Project Status (if one exists) or the
    Projects activity (empty).

    The legacy ``?legacy=1`` query parameter is retained for
    backward compatibility with older workspaces that have a v2
    ``complete`` manifest but still want the v0.12 home page.

    Args:
        request: The incoming Starlette request.

    Returns:
        A 303 redirect to ``/setup``, an active Project URL, or
        ``/workbench?activity=projects``.
    """
    from .entry_resolver import EntryFacts, resolve_entry
    from .setup_state import try_read_manifest

    workspace_root = Path(getattr(request.app.state, "workspace_root", ".")).resolve()
    manifest = try_read_manifest(workspace_root)
    setup_complete = manifest is not None and manifest.is_complete

    if not setup_complete:
        return RedirectResponse(url="/setup", status_code=303)

    # Setup is complete -- resolve the active project URL.
    active_project_url: str | None = None
    store = getattr(request.app.state, "store", None)
    if store is not None:
        try:
            project_info = store.project_info().get("project", {})
            project_id = project_info.get("project_id") or project_info.get("project")
            if project_id:
                active_project_url = (
                    f"/workbench?activity=projects&project={project_id}"
                )
        except Exception:
            pass

    facts = EntryFacts(
        setup_complete=True,
        active_project_url=active_project_url,
    )
    resolution = resolve_entry(facts)

    if request.query_params.get("legacy") == "1" and resolution.destination != "setup":
        return await home_page(request)

    if resolution.destination == "active_project":
        return RedirectResponse(url=resolution.url, status_code=303)
    if resolution.destination == "projects":
        return RedirectResponse(url=resolution.url, status_code=303)
    return RedirectResponse(url=resolution.url, status_code=303)


async def home_page(request: Request) -> HTMLResponse:
    user = _require_page_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    lang = _ui_language(request)
    spec_id = store.resolve_spec_id()
    body = f"""
    <section class="hero">
      <span class="eyebrow">{_escape(_t(lang, "home.eyebrow"))}</span>
      <h1>louke Web Workbench</h1>
      <p class="lede">{_escape(_t(lang, "home.lede_before"))}<code>{_escape(spec_id)}</code>{_escape(_t(lang, "home.lede_after"))}</p>
    </section>
    <section class="grid cards">
      <a class="card card-link" href="/models">
        <div class="card-kicker">models</div>
        <h2>{_escape(_t(lang, "nav.models"))}</h2>
        <p>{_escape(_t(lang, "home.models_desc"))}</p>
      </a>
      <a class="card card-link" href="/docs/{_escape(spec_id)}/spec">
        <div class="card-kicker">docs</div>
        <h2>{_escape(_t(lang, "nav.docs"))}</h2>
        <p>{_escape(_t(lang, "home.docs_desc"))}</p>
      </a>
       <a class="card card-link" href="/wiki">
         <div class="card-kicker">llm wiki</div>
         <h2>llm wiki</h2>
         <p>{_escape(_t(lang, "home.wiki_desc"))}</p>
       </a>
    </section>
    """
    return HTMLResponse(_page_shell("louke web", store, user, lang, "home", body))


async def models_page(request: Request) -> HTMLResponse:
    user = _require_page_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    lang = _ui_language(request)
    body = f"""
    <header class="page-header">
      <div>
        <span class="eyebrow">Models</span>
        <h1>{_escape(_t(lang, "nav.models"))}</h1>
        <p class="lede">{_escape(_t(lang, "models.lede"))}</p>
        <p class="models-flow">{_escape(_t(lang, "models.flow_hint"))}</p>
      </div>
      <div id="meta" class="meta"></div>
    </header>
    <div id="banner" class="banner" hidden></div>
    <main class="grid models-grid">
      <section class="panel models-panel">
        <h2>{_escape(_t(lang, "models.catalog"))}</h2>
        <div id="model-list" class="model-list"></div>
      </section>
      <section class="panel models-panel">
        <h2>{_escape(_t(lang, "models.roles"))}</h2>
        <div id="role-list" class="binding-list"></div>
      </section>
      <section class="panel models-panel">
        <h2>{_escape(_t(lang, "models.agents"))}</h2>
        <div id="agent-list" class="binding-list"></div>
      </section>
    </main>
    """
    script = _models_page_script(lang)
    return HTMLResponse(
        _page_shell(
            _t(lang, "nav.models"), store, user, lang, "models", body, script=script
        )
    )


async def wiki_index_page(request: Request) -> HTMLResponse:
    user = _require_page_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    lang = _ui_language(request)
    pages = store.list_wiki_pages()
    index_entry = store.read_wiki_index()
    if index_entry is not None:
        # Render the content of .louke/wiki/index.md (maintained by the
        # librarian agent) as the wiki landing page, with the list of
        # wiki pages as a side card.
        from .render import render_markdown_view

        rendered = render_markdown_view(index_entry[0], kind="wiki")
        last_modified = index_entry[1].updated_at or _t(lang, "meta.not_recorded")
        last_modified_by = index_entry[1].last_modified_by or _t(lang, "meta.unknown")
        body = f"""
        <header class="page-header">
          <div>
            <span class="eyebrow">llm wiki</span>
            <h1>llm wiki</h1>
            <p class="lede">{_escape(_t(lang, "wiki.index_lede"))}</p>
          </div>
          <div class="toolbar-actions">
            <input id="new-page" placeholder="guides/getting-started" />
            <button id="create-page">{_escape(_t(lang, "wiki.create_open"))}</button>
          </div>
        </header>
        <section class="grid wiki-layout">
          <article class="card wiki-index-body">
            <div class="wiki-index-content">{rendered.rendered_html}</div>
            <div class="meta">Last modified by {_escape(last_modified_by)} @ {
            _escape(last_modified)
        }</div>
          </article>
          <aside class="card wiki-pages-list">
            <h2>Pages ({len(pages)})</h2>
            <ul class="wiki-pages-ul">
              {
            "".join(
                f'<li><a href="/wiki/{_quote_path(p["page"])}">{_escape(p["page"])}</a></li>'
                for p in pages
            )
            or f'<li class="muted">{_escape(_t(lang, "wiki.empty"))}</li>'
        }
            </ul>
          </aside>
        </section>
        """
    else:
        # No index.md yet — fall back to the legacy "card grid" listing.
        items = []
        for page in pages:
            items.append(
                f'<a class="card card-link wiki-card" href="/wiki/{_quote_path(page["page"])}">'
                f"<h2>{_escape(page['page'])}</h2>"
                f"<p>{_escape(page['updated_at'] or _t(lang, 'meta.not_recorded'))}</p>"
                f"</a>"
            )
        body = f"""
        <header class="page-header">
          <div>
            <span class="eyebrow">llm wiki</span>
            <h1>llm wiki</h1>
            <p class="lede">{_escape(_t(lang, "wiki.index_lede"))}</p>
          </div>
          <div class="toolbar-actions">
            <input id="new-page" placeholder="guides/getting-started" />
            <button id="create-page">{_escape(_t(lang, "wiki.create_open"))}</button>
          </div>
        </header>
        <section class="grid cards">
          {"".join(items) or f'<div class="card"><p>{_escape(_t(lang, "wiki.empty"))}</p></div>'}
        </section>
        """
    script = """
    <script>
    document.getElementById('create-page').addEventListener('click', () => {
      const value = document.getElementById('new-page').value.trim();
      if (!value) return;
      location.href = `/wiki/${value.split('/').map(encodeURIComponent).join('/')}`;
    });
    </script>
    """
    return HTMLResponse(
        _page_shell("wiki", store, user, lang, "wiki", body, script=script)
    )


async def wiki_editor_page(request: Request) -> HTMLResponse:
    user = _require_page_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    lang = _ui_language(request)
    page = request.path_params["page"]
    encoded_page = _quote_path(page)
    body = f"""
    <div id="banner" class="banner" hidden></div>
    <div class="pane-container">
      <div class="pane">
        <div class="pane-bar">
          <span class="pane-title">wiki: {_escape(page)}</span>
          <span class="save-time" id="save-time">Last Saved: --:--:--</span>
          <div class="pane-tools">
            <button class="icon-btn icon-save" id="save-btn" title="Save"></button>
            <button class="icon-btn icon-reload" id="reload-btn" title="Reload"></button>
          </div>
        </div>
        <div class="vditor-mount" id="vditor-0"></div>
      </div>
    </div>
    """
    vditor_head = (
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/vditor/dist/index.css" />'
        '<script src="https://cdn.jsdelivr.net/npm/vditor/dist/index.min.js"></script>'
    )
    script = _wiki_editor_script(
        api_path=f"/api/wiki/{encoded_page}",
        actor_name=user.username,
        lang=lang,
    )
    return HTMLResponse(
        _page_shell(
            f"wiki {page}",
            store,
            user,
            lang,
            "wiki",
            body,
            script=script,
            current_wiki_page=page,
            head_extra=vditor_head,
        )
    )


async def doc_editor_page(request: Request) -> HTMLResponse:
    user = _require_page_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    lang = _ui_language(request)
    spec_id = request.path_params["spec_id"]
    doc_name = request.path_params["doc_name"]
    docs = store.list_spec_documents(spec_id)
    body = """
    <div id="banner" class="banner" hidden><span class="banner-msg"></span><button class="banner-close" type="button">×</button></div>
    <div id="pane-container" class="pane-container"></div>
    """
    script = _editor_page_script(
        spec_id=spec_id,
        doc_name=doc_name,
        docs=docs,
        actor_name=user.username,
        lang=lang,
    )
    vditor_head = (
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/vditor/dist/index.css" />'
        '<script src="https://cdn.jsdelivr.net/npm/vditor/dist/index.min.js"></script>'
    )
    return HTMLResponse(
        _page_shell(
            f"{spec_id} {doc_name}",
            store,
            user,
            lang,
            "docs",
            body,
            script=script,
            current_doc_name=doc_name,
            current_spec_id=spec_id,
            head_extra=vditor_head,
        )
    )


async def api_auth_register(request: Request) -> JSONResponse:
    store: ProjectStore = request.app.state.store
    payload = await request.json()
    try:
        user = register_user(
            store,
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
        )
    except ValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    response = JSONResponse({"ok": True, "username": user.username})
    _set_session_cookie(response, store, user.username)
    return response


async def api_auth_login(request: Request) -> JSONResponse:
    store: ProjectStore = request.app.state.store
    payload = await request.json()
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    # First-run: when no users exist yet (e.g. Setup manifest was seeded
    # directly), the first login attempt auto-registers the principal so
    # the frozen e2e contract ``input[name="name"]`` → login → Projects
    # works without a separate register step.
    if not store.list_users() and username:
        try:
            user = register_user(store, username=username, password=password)
        except ValidationError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        response = JSONResponse({"ok": True, "username": user.username})
        _set_session_cookie(response, store, user.username)
        return response
    try:
        user = authenticate_user(
            store,
            username=username,
            password=password,
        )
    except ValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    response = JSONResponse({"ok": True, "username": user.username})
    _set_session_cookie(response, store, user.username)
    return response


async def api_auth_logout(request: Request) -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return response


async def api_bindings(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    broker: EventBroker = request.app.state.broker
    if request.method == "GET":
        return JSONResponse(get_bindings_payload(store))
    payload = await request.json()
    actor_name = user.username
    try:
        response = save_bindings_payload(store, payload, actor_name)
    except ConflictError as exc:
        broker.publish_nowait(
            "conflict.detected",
            {
                "target": ".louke/models.json",
                "actor_name": actor_name,
                "updated_at": store.read_bindings()[2].updated_at,
            },
        )
        return JSONResponse(
            {"code": "CONFLICT", "message": str(exc), "error": str(exc)},
            status_code=409,
        )
    except ValidationError as exc:
        message = str(exc)
        code = message.split(":", 1)[0] if ":" in message else "VALIDATION_FAILED"
        status = 403 if code == "PATH_NOT_ALLOWED" else 400
        return JSONResponse(
            {"code": code, "message": message, "error": message},
            status_code=status,
        )
    broker.publish_nowait(
        "bindings.updated",
        {
            "updated_at": response["updated_at"],
            "actor_name": response["last_modified_by"],
        },
    )
    return JSONResponse(response)


async def api_wiki_index(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    return JSONResponse({"pages": request.app.state.store.list_wiki_pages()})


async def api_wiki_refresh(request: Request) -> JSONResponse:
    """Trigger a librarian agent run to refresh the wiki.

    Delegates to `lk agent librarian rewrite`, which:
      1. Selects the right compact bundle (M2 merged vs M0/M1 main).
      2. Resolves the model via `--model > --model-from-config > frontmatter`.
      3. Spawns `opencode run --agent librarian [--model X] -- <prompt>`
         where <prompt> is a fully-formed instruction (without -- or a
         prompt, the opencode CLI errors with
         "You must provide a message or a command").

    All stdout/stderr/returncode are emitted to the server log so
    non-zero exits are debuggable without re-running the agent.
    """
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    project_root = store.root

    _logger.info("wiki refresh requested by %s in %s", user.username, project_root)

    # Auto-prepare: if no compact bundle exists, run `lk agent librarian
    # compact` first so the user never has to remember to do it manually.
    # The rewrite subcommand assumes .compact-bundle.md (or the M2 merged
    # bundle) is present; without it, the click would fail with a
    # confusing "compact-bundle missing" error. Running compact inline
    # makes the click work end-to-end.
    wiki_dir = project_root / ".louke" / "wiki"
    bundle_main = wiki_dir / ".compact-bundle.md"
    bundle_merged = wiki_dir / ".compact-bundle-merged.md"
    if not bundle_main.exists() and not bundle_merged.exists():
        if (project_root / ".louke" / "raw").exists():
            _logger.info("auto-running librarian compact (no bundle yet)")
            compact_proc = subprocess.run(
                [sys.executable, "-m", "louke", "agent", "librarian", "compact"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )
            _logger.info(
                "auto-compact finished: returncode=%d (stdout=%d bytes, stderr=%d bytes)",
                compact_proc.returncode,
                len(compact_proc.stdout or ""),
                len(compact_proc.stderr or ""),
            )
            for line in (compact_proc.stdout or "").splitlines():
                _logger.info("auto-compact stdout | %s", line)
            for line in (compact_proc.stderr or "").splitlines():
                _logger.info("auto-compact stderr | %s", line)
            if compact_proc.returncode != 0:
                # If compact fails (e.g. raw/ doesn't exist), surface a clear
                # hint instead of a generic rewrite error.
                _logger.warning(
                    "auto-compact returned non-zero; rewriting with whatever "
                    "is on disk may still succeed or will fail with hint."
                )
        else:
            _logger.warning(
                "no .louke/raw/ directory; skipping auto-compact. Run "
                "`lk agent librarian compact` first to seed raw data."
            )

    # Invoke lk as a Python module via the same interpreter that runs
    # this server. This avoids depending on the `lk` console-script
    # being on PATH — some IDE-launched servers (e.g. Trae CN) strip
    # PATH down to a single entry, and the `lk` script installed by
    # `pip install -e .` into `.venv/bin/` is not visible from there.
    # `python -m louke` always works as long as louke is importable,
    # which it must be (this code is in louke.web).
    cmd = [
        sys.executable,
        "-m",
        "louke",
        "agent",
        "librarian",
        "rewrite",
    ]
    _logger.info("spawning: %s (cwd=%s)", " ".join(cmd), project_root)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        _logger.error("librarian run exceeded 10 minute timeout in %s", project_root)
        return JSONResponse(
            {"error": "librarian run exceeded 10 minute timeout"},
            status_code=504,
        )
    except Exception as exc:
        _logger.exception("failed to spawn lk in %s", project_root)
        return JSONResponse({"error": f"failed to spawn lk: {exc}"}, status_code=500)

    # Log everything so non-zero exits are debuggable from the server log.
    log_fn = _logger.info if proc.returncode == 0 else _logger.error
    log_fn(
        "librarian finished: returncode=%d (stdout=%d bytes, stderr=%d bytes)",
        proc.returncode,
        len(proc.stdout or ""),
        len(proc.stderr or ""),
    )
    if proc.stdout:
        for line in proc.stdout.splitlines():
            log_fn("librarian stdout | %s", line)
    if proc.stderr:
        for line in proc.stderr.splitlines():
            log_fn("librarian stderr | %s", line)
    if proc.returncode != 0:
        _logger.error(
            "librarian run failed (exit %d). Last 80 lines of combined output:",
            proc.returncode,
        )
        combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
        for line in combined.splitlines()[-80:]:
            _logger.error("  %s", line)

    # Record activity so other clients see that the wiki was refreshed.
    index_path = store.wiki_index_path()
    if index_path.exists():
        metadata = store.record_activity(
            "wiki.updated",
            index_path,
            user.username,
            extra={"action": "librarian.refresh", "returncode": proc.returncode},
        )
    else:
        metadata = None

    payload: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:] if proc.stdout else "",
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
    }
    if metadata is not None:
        payload["updated_at"] = metadata.updated_at
        payload["last_modified_by"] = metadata.last_modified_by
    # Surface a clearer hint when the failure is the missing-bundle
    # precondition (so the UI message can guide the user to run
    # `lk agent librarian compact` first).
    if proc.returncode != 0 and proc.stderr and "compact-bundle" in proc.stderr:
        payload["hint"] = (
            "Run `lk agent librarian compact` first to create .compact-bundle.md"
        )
    return JSONResponse(payload)


async def api_wiki_page(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    broker: EventBroker = request.app.state.broker
    page = request.path_params["page"]
    if request.method == "GET":
        try:
            return JSONResponse(get_wiki_payload(store, page))
        except FileNotFoundError:
            if request.headers.get("accept", "").startswith("application/json"):
                return JSONResponse(
                    {
                        "page": page,
                        "path": store.relative_path(store.wiki_page_path(page)),
                        "body_md": "",
                        "rendered_html": "",
                        "version_token": "new",
                        "updated_at": "",
                        "last_modified_by": "",
                    }
                )
            raise
    payload = await request.json()
    actor_name = user.username
    try:
        response = save_wiki_payload(
            store,
            page=page,
            body_md=str(payload.get("body_md") or ""),
            version_token=str(payload.get("version_token") or ""),
            actor_name=actor_name,
        )
    except ConflictError as exc:
        broker.publish_nowait(
            "conflict.detected",
            {
                "target": store.relative_path(store.wiki_page_path(page)),
                "actor_name": actor_name,
                "updated_at": store.latest_activity(
                    store.wiki_page_path(page)
                ).updated_at,
            },
        )
        return JSONResponse({"error": str(exc)}, status_code=409)
    except ValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    broker.publish_nowait(
        "wiki.updated",
        {
            "target": response["path"],
            "updated_at": response["updated_at"],
            "actor_name": response["last_modified_by"],
        },
    )
    return JSONResponse(response)


async def api_doc(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    broker: EventBroker = request.app.state.broker
    spec_id = request.path_params["spec_id"]
    doc_name = request.path_params["doc_name"]
    if request.method == "GET":
        try:
            return JSONResponse(get_doc_payload(store, spec_id, doc_name))
        except (FileNotFoundError, ValidationError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
    payload = await request.json()
    actor_name = user.username
    try:
        response = save_doc_payload(
            store,
            spec_id=spec_id,
            doc_name=doc_name,
            body_md=str(payload.get("body_md") or ""),
            version_token=str(payload.get("version_token") or ""),
            actor_name=actor_name,
            force=bool(payload.get("force")),
        )
    except ConflictError as exc:
        try:
            target = store.relative_path(store.doc_path(spec_id, doc_name))
            updated_at = store.latest_activity(
                store.doc_path(spec_id, doc_name)
            ).updated_at
        except Exception:
            target = ""
            updated_at = ""
        broker.publish_nowait(
            "conflict.detected",
            {"target": target, "actor_name": actor_name, "updated_at": updated_at},
        )
        return JSONResponse({"error": str(exc)}, status_code=409)
    except ValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    broker.publish_nowait(
        "document.updated",
        {
            "target": response["path"],
            "updated_at": response["updated_at"],
            "actor_name": response["last_modified_by"],
        },
    )
    return JSONResponse(response)


async def api_toggle_status(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    spec_id = request.path_params["spec_id"]
    doc_name = request.path_params["doc_name"]
    payload = await request.json()
    fr_id = str(payload.get("fr_id") or "")
    field = str(payload.get("field") or "")
    version_token = str(payload.get("version_token") or "")
    if field not in ("valid", "testable", "decided") or not fr_id:
        return JSONResponse({"error": "invalid fr_id or field"}, status_code=400)
    try:
        response = toggle_status_payload(
            store,
            spec_id=spec_id,
            doc_name=doc_name,
            fr_id=fr_id,
            field=field,
            version_token=version_token,
            actor_name=user.username,
        )
    except ConflictError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except (FileNotFoundError, ValidationError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(response)


async def api_specs(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    return JSONResponse({"specs": store.list_spec_ids()})


async def api_ui_devdocs_tree(request: Request) -> JSONResponse:
    """Return the read-only Markdown tree used by the workbench sidebar."""
    store: ProjectStore = request.app.state.store
    specs: list[dict[str, Any]] = []
    for spec_id in store.list_spec_ids():
        directory = store.specs_dir / spec_id
        documents = [
            {
                "name": path.stem,
                "path": store.relative_path(path),
            }
            for path in sorted(directory.glob("*.md"))
            if path.is_file()
        ]
        specs.append({"spec_id": spec_id, "documents": documents})
    return JSONResponse({"specs": specs})


async def api_ui_wiki_page(request: Request) -> JSONResponse:
    """Read a Wiki page and turn missing pages into an explicit fallback."""
    store: ProjectStore = request.app.state.store
    page = request.path_params["page"]
    try:
        payload = get_wiki_payload(store, page)
    except FileNotFoundError:
        return JSONResponse(
            {
                "unknown": True,
                "display_label": f"未知页面: {page}",
                "page": page,
            },
            status_code=200,
        )
    body = str(payload.get("body_md") or "").encode("utf-8")
    return JSONResponse(
        {**payload, "unknown": False, "sha256": hashlib.sha256(body).hexdigest()}
    )


async def api_render(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    payload = await request.json()
    return JSONResponse(
        render_preview_payload(
            kind=str(payload.get("kind") or ""),
            doc_name=str(payload.get("doc_name") or ""),
            body_md=str(payload.get("body_md") or ""),
        )
    )


_TERMINAL_RUN_STATUSES = frozenset({"completed", "cancelled", "failed", "archived"})
_KNOWN_RUN_STATUSES = frozenset(
    {
        "in_progress",
        "waiting_for_human",
        "completed",
        "cancelled",
        "failed",
        "archived",
        "blocked",
        "needs_attention",
    }
)
_KNOWN_GRAPH_STATES = frozenset(
    {
        "completed",
        "current",
        "waiting_for_human",
        "blocked",
        "failed",
        "pending",
        "skipped_by_definition",
    }
)


def _runtime_store(request: Request) -> WorkflowRunStore:
    """Return the project Runtime store shared by all v0.12 sub-apps."""
    return request.app.state.v12_run_store


def _run_summary(run: WorkflowRun) -> dict[str, Any]:
    """Build the compatibility summary from Runtime fields only."""
    status = str(run.status)
    return {
        "project_id": run.run_id,
        "project_name": run.definition_id,
        "run_id": run.run_id,
        "workflow_definition_id": run.definition_id,
        "workflow_version": run.definition_version,
        "status": status,
        "run_status": status,
        "current_step": run.current_step,
        "updated_at": run.updated_at,
        "status_unknown": status not in _KNOWN_RUN_STATUSES,
    }


def _graph_node_payload(node: Any) -> dict[str, Any]:
    """Return one graph node with an explicit unknown-state fallback."""
    state = node.state
    payload: dict[str, Any] = {
        "stage_id": node.step_id,
        "kind": node.kind,
        "label": node.label,
        "state": state,
        "required": node.required,
        "unknown": state not in _KNOWN_GRAPH_STATES,
        "badges": [status_badge(state)],
    }
    if payload["unknown"]:
        payload["display_label"] = f"unknown stage/status: {node.step_id}"
    return payload


def _graph_payload(graph: Any) -> dict[str, Any]:
    """Return the JSON-safe compatibility graph projection."""
    return {
        "run_id": graph.run_id,
        "definition_id": graph.definition_id,
        "definition_version": graph.definition_version,
        "current_step": graph.current_node_id,
        "revision": graph.revision,
        "nodes": [_graph_node_payload(node) for node in graph.nodes],
        "edges": [
            {
                "edge_id": edge.edge_id,
                "from_step": edge.from_step,
                "to_step": edge.to_step,
                "condition": edge.condition,
            }
            for edge in graph.edges
        ],
    }


async def api_ui_runs(request: Request) -> JSONResponse:
    """Return the current/history projection of Runtime-owned runs."""
    summaries = [_run_summary(run) for run in _runtime_store(request).list_runs()]
    return JSONResponse(
        {
            "current": [
                item
                for item in summaries
                if item["status"] not in _TERMINAL_RUN_STATUSES
            ],
            "history": [
                item for item in summaries if item["status"] in _TERMINAL_RUN_STATUSES
            ],
            "create_project_href": "/projects/new",
        }
    )


async def api_ui_run_graph(request: Request) -> JSONResponse:
    """Return a definition-bound Runtime graph with safe badge fallbacks."""
    run_id = request.path_params["run_id"]
    try:
        graph = WorkflowGraphBuilder(_runtime_store(request)).build(run_id)
    except RunNotFoundError:
        return JSONResponse(
            {"code": "RUN_NOT_FOUND", "message": f"run {run_id} not found"},
            status_code=404,
        )
    return JSONResponse(_graph_payload(graph))


async def api_ui_artifact(request: Request) -> JSONResponse:
    """Return a read-only Runtime event projection for one workflow step."""
    run_id = request.path_params["run_id"]
    stage_id = request.path_params["stage_id"]
    try:
        graph = WorkflowGraphBuilder(_runtime_store(request)).build(run_id)
    except RunNotFoundError:
        return JSONResponse(
            {"code": "RUN_NOT_FOUND", "message": f"run {run_id} not found"},
            status_code=404,
        )
    if stage_id not in {node.step_id for node in graph.nodes}:
        return JSONResponse(
            {"code": "STAGE_NOT_FOUND", "message": f"stage {stage_id} not found"},
            status_code=404,
        )
    event = next(
        (
            item
            for item in reversed(_runtime_store(request).get_events(run_id))
            if item.step_id == stage_id
        ),
        None,
    )
    return JSONResponse(
        {
            "run_id": run_id,
            "stage_id": stage_id,
            "result_kind": event.type if event is not None else "",
            "unknown": event is None,
            "stale": False,
            "digest": event.output_digest if event is not None else "",
            "verdict": event.details.get("result", "") if event is not None else "",
            "required_reviewer": event.details.get("reviewer", "")
            if event is not None
            else "",
            "review_conclusion": event.details.get("conclusion", "")
            if event is not None
            else "",
            "display_label": "runtime event" if event is None else "",
        }
    )


async def api_discussion_mutate(request: Request) -> JSONResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    store: ProjectStore = request.app.state.store
    broker: EventBroker = request.app.state.broker
    payload = await request.json()
    actor_name = user.username
    try:
        response = mutate_discussion(
            store,
            target_kind=str(payload.get("target_kind") or ""),
            target_path=str(payload.get("target_path") or ""),
            version_token=str(payload.get("version_token") or ""),
            actor_name=actor_name,
            action=str(payload.get("action") or ""),
            anchor=dict(payload.get("anchor") or {}),
            payload=dict(payload.get("payload") or {}),
        )
    except ConflictError as exc:
        broker.publish_nowait(
            "conflict.detected",
            {
                "target": str(payload.get("target_path") or ""),
                "actor_name": actor_name,
                "updated_at": "",
            },
        )
        return JSONResponse({"error": str(exc)}, status_code=409)
    except (ValidationError, FileNotFoundError, PermissionError, ValueError) as exc:
        status = 422 if isinstance(exc, PermissionError | ValueError) else 400
        return JSONResponse({"error": str(exc)}, status_code=status)
    event_name = (
        "document.updated" if payload.get("target_kind") == "doc" else "wiki.updated"
    )
    broker.publish_nowait(
        event_name,
        {
            "target": response["path"],
            "updated_at": response["updated_at"],
            "actor_name": response["last_modified_by"],
        },
    )
    return JSONResponse(response)


async def api_events(request: Request) -> StreamingResponse:
    user = _require_api_user(request)
    if isinstance(user, Response):
        return user
    broker: EventBroker = request.app.state.broker
    queue = broker.subscribe()

    async def stream():
        try:
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                event = message["event"]
                data = json.dumps(message["data"], ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n".encode("utf-8")
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _current_user(request: Request) -> AuthenticatedUser | None:
    store: ProjectStore = request.app.state.store
    return current_user(store, request.cookies.get(SESSION_COOKIE))


def _require_page_user(request: Request) -> AuthenticatedUser | Response:
    user = _current_user(request)
    if user is not None:
        return user
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(
        url=f"/login?{urlencode({'next': next_path})}", status_code=303
    )


_logger = logging.getLogger("louke.web")


def _require_api_user(request: Request) -> AuthenticatedUser | Response:
    user = _current_user(request)
    if user is not None:
        return user
    return JSONResponse({"error": "login required"}, status_code=401)


def _ui_language(request: Request) -> str:
    raw = str(request.headers.get("accept-language") or "").strip().lower()
    if not raw:
        return "en"
    for token in raw.split(","):
        code = token.split(";")[0].strip()
        if code.startswith("zh"):
            return "zh"
        if code.startswith("en"):
            return "en"
    return "en"


def _set_session_cookie(response: Response, store: ProjectStore, username: str) -> None:
    """Set the Strict HttpOnly session cookie; CSRF travels in a header."""
    session_cookie = issue_session_cookie(store, username)
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        samesite="strict",
        path="/",
    )


def _page_shell(
    title: str,
    store: ProjectStore,
    user: AuthenticatedUser,
    lang: str,
    section: str,
    body: str,
    script: str = "",
    current_doc_name: str = "",
    current_wiki_page: str = "",
    current_spec_id: str = "",
    head_extra: str = "",
) -> str:
    sidebar = _sidebar_html(
        store, user, lang, section, current_doc_name, current_wiki_page, current_spec_id
    )
    # pane-host class is added dynamically by JS based on pane count and
    # viewport width, not here (so 1 pane keeps the comfortable padding).
    return f"""<!DOCTYPE html>
<html lang="{_escape("zh-CN" if lang == "zh" else "en")}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #fafafa;
      --surface: #ffffff;
      --surface-alt: #f3f4f6;
      --sidebar: #fcfcfc;
      --text: #111111;
      --muted: #6b7280;
      --border: #e5e7eb;
      --border-strong: #d1d5db;
      --accent: #111111;
      --danger: #b91c1c;
      --success: #166534;
      --shadow: 0 1px 2px rgba(17, 24, 39, 0.04);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    a {{ color: inherit; text-decoration: none; }}
    code, pre, textarea, input, .mono {{
      font-family: "SFMono-Regular", ui-monospace, Menlo, Consolas, monospace;
    }}
    code {{
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1px 5px;
    }}
    .app-shell {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      transition: grid-template-columns 0.2s ease;
    }}
    .app-shell.sidebar-collapsed {{
      grid-template-columns: 0 minmax(0, 1fr);
    }}
    .app-shell.sidebar-collapsed .sidebar {{
      overflow: hidden;
      padding: 0;
      border-right: 0;
      min-width: 0;
      width: 0;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      align-self: start;
      height: 100vh;
      min-width: 0;
      overflow: auto;
      padding: 20px 16px;
      background: var(--sidebar);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
    }}
    .sidebar-toggle {{
      position: fixed;
      top: 12px;
      left: 248px;
      z-index: 100;
      width: 28px;
      height: 28px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      color: var(--muted);
      transition: left 0.2s ease;
    }}
    .app-shell.sidebar-collapsed .sidebar-toggle {{
      left: 8px;
    }}
    .brand-card {{
      padding: 10px;
      margin-bottom: 12px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }}
    .brand {{
      display: block;
      padding: 6px 4px;
    }}
    .brand-title {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .brand-subtitle {{
      padding: 4px 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .spec-select {{
      margin: 4px 10px 10px;
      width: calc(100% - 20px);
      padding: 5px 8px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      font: inherit;
      font-size: 12px;
      cursor: pointer;
    }}
    .user-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 4px;
      margin-top: 6px;
      border-top: 1px solid var(--border);
      padding-top: 8px;
    }}
    .user-name {{
      font-weight: 600;
      font-size: 14px;
    }}
    .ghost-button {{
      background: transparent;
      color: var(--muted);
      border: 0;
      padding: 6px 10px;
      font-size: 13px;
      border-radius: 8px;
      cursor: pointer;
      min-height: 32px;
    }}
    .ghost-button:hover {{
      background: var(--surface-alt);
      color: var(--text);
    }}
    .nav-link-row {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    .nav-link-row > a {{ flex: 1; }}
    .wiki-refresh-btn {{
      background: transparent;
      border: 0;
      padding: 4px 8px;
      border-radius: 6px;
      color: var(--muted);
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
    }}
    .wiki-refresh-btn:hover {{
      background: var(--surface-alt);
      color: var(--text);
    }}
    .wiki-refresh-btn[data-busy="1"] {{
      opacity: 0.7;
      cursor: wait;
      animation: wiki-refresh-spin 1.2s linear infinite;
    }}
    @keyframes wiki-refresh-spin {{
      from {{ transform: rotate(0deg); }}
      to   {{ transform: rotate(360deg); }}
    }}
    /* Modal overlay for wiki refresh — full-screen, step-by-step status */
    .wiki-modal[hidden] {{ display: none; }}
    .wiki-modal-backdrop {{
      position: fixed; inset: 0; z-index: 999;
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(2px);
      display: grid; place-items: center;
    }}
    .wiki-modal-dialog {{
      width: min(420px, calc(100vw - 32px));
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: 0 24px 48px rgba(15, 23, 42, 0.18);
      padding: 24px 24px 20px;
      font-size: 14px;
      color: var(--text);
    }}
    .wiki-modal-title {{
      display: flex; align-items: center; justify-content: space-between;
      margin: 0 0 12px; font-size: 16px; font-weight: 600;
    }}
    .wiki-modal-elapsed {{
      font-variant-numeric: tabular-nums; font-size: 13px; color: var(--muted);
    }}
    .wiki-modal-steps {{ list-style: none; padding: 0; margin: 0 0 16px; display: grid; gap: 8px; }}
    .wiki-modal-step {{
      display: flex; align-items: center; gap: 10px;
      padding: 8px 10px;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface);
      color: var(--muted);
      font-size: 13px;
      transition: background 0.2s, color 0.2s, border-color 0.2s;
    }}
    .wiki-modal-step .step-icon {{
      width: 18px; height: 18px; display: inline-flex; align-items: center;
      justify-content: center; font-weight: 700; font-size: 13px;
      border: 1px solid var(--border); border-radius: 50%;
      background: var(--surface); color: var(--muted);
    }}
    .wiki-modal-step.active {{
      background: var(--surface-alt); color: var(--text);
      border-color: var(--accent);
    }}
    .wiki-modal-step.active .step-icon {{
      background: var(--accent); color: white; border-color: var(--accent);
      animation: wiki-modal-pulse 1.4s ease-in-out infinite;
    }}
    .wiki-modal-step.done {{
      color: var(--text);
    }}
    .wiki-modal-step.done .step-icon {{
      background: #16a34a; color: white; border-color: #16a34a;
    }}
    .wiki-modal-step.failed {{
      color: #b91c1c; border-color: #fecaca; background: #fef2f2;
    }}
    .wiki-modal-step.failed .step-icon {{
      background: #b91c1c; color: white; border-color: #b91c1c;
    }}
    @keyframes wiki-modal-pulse {{
      0%, 100% {{ transform: scale(1); opacity: 1; }}
      50%      {{ transform: scale(1.08); opacity: 0.7; }}
    }}
    .wiki-modal-detail {{
      margin: 8px 0 12px; padding: 10px;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface);
      font-family: ui-monospace, monospace;
      font-size: 12px; line-height: 1.45;
      max-height: 140px; overflow: auto;
      white-space: pre-wrap; word-break: break-word;
      color: var(--text);
    }}
    .wiki-modal-actions {{
      display: flex; gap: 8px; justify-content: flex-end;
    }}
    .wiki-modal-actions .ghost-button {{ padding: 6px 12px; font-size: 13px; }}
    .nav-section {{
      margin-top: 18px;
    }}
    .nav-label {{
      margin: 0 0 8px;
      padding: 0 10px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .nav-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 10px;
      color: var(--muted);
    }}
    .nav-link:hover {{
      background: var(--surface-alt);
      color: var(--text);
    }}
    .nav-link.active {{
      background: var(--text);
      color: #ffffff;
    }}
    .nav-sublinks {{
      margin-top: 6px;
      padding-left: 8px;
      border-left: 1px solid var(--border);
    }}
    .nav-subgroup {{
      margin-bottom: 10px;
    }}
    .nav-subtitle {{
      padding: 4px 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .nav-sublink {{
      display: block;
      margin: 2px 0;
      padding: 8px 10px;
      border-radius: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .nav-sublink:hover {{
      background: var(--surface-alt);
      color: var(--text);
    }}
    .nav-sublink.active {{
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .workspace {{
      min-width: 0;
      padding: 28px;
    }}
    .workspace-inner {{
      max-width: 1600px;
      margin: 0 auto;
    }}
    /* Pane host mode (toggled by JS when 2+ panes are open, or when the
       available width per pane drops below the 50 Chinese-char threshold):
       reclaim the workspace padding and the 1600px inner max-width
       so panes use the full viewport. Toggled dynamically, not applied
       unconditionally to doc pages, because 1 pane still benefits from
       the comfortable 28px padding / 1600px reading width. */
    .workspace-inner.pane-host {{
      max-width: none;
    }}
    .workspace.pane-host {{
      padding: 8px;
    }}
    .page-header, .panel-header {{
      display: flex; justify-content: space-between; gap: 16px; align-items: center;
    }}
    .toolbar-actions, .inline-form {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .focus-toggle-btn {{ position: relative; padding-right: 28px; }}
    .focus-toggle-btn::after {{
      content: '⇄'; position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
      font-size: 12px; opacity: 0.5;
    }}
    .focus-toggle-btn.state-discussion {{ background: var(--surface); color: var(--text); border-color: var(--border-strong); }}
    .autosave-indicator {{ font-size: 12px; color: var(--muted); padding: 0 4px; }}
    .grid {{ display: grid; gap: 16px; }}
    .editor-grid {{ grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr); }}
    .models-grid {{ grid-template-columns: 240px 200px 1fr; align-items: start; }}
    .models-panel {{ position: relative; }}
    .models-flow {{ margin: 6px 0 0; color: var(--muted); font-size: 12px; }}
    .models-panel + .models-panel::before {{
      content: '→'; position: absolute; left: -14px; top: 18px;
      color: var(--border-strong); font-size: 16px; font-weight: 600;
    }}
    .binding-list {{ display: grid; gap: 8px; }}
    .binding-list.is-agents {{ grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }}
    .cards {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 16px; }}
    .wiki-layout {{ grid-template-columns: minmax(0, 1fr) 280px; margin-top: 16px; align-items: start; }}
    .wiki-index-body {{ min-width: 0; }}
    .wiki-index-content {{ line-height: 1.6; }}
    .wiki-index-content h1, .wiki-index-content h2, .wiki-index-content h3 {{ margin-top: 16px; }}
    .wiki-pages-list h2 {{ font-size: 14px; margin: 0 0 10px; }}
    .wiki-pages-ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }}
    .wiki-pages-ul li a {{ display: block; padding: 6px 8px; border-radius: 6px; color: var(--text); font-size: 13px; }}
    .wiki-pages-ul li a:hover {{ background: var(--surface-alt); }}
    .panel, .card, .banner {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .card-link:hover {{
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }}
    .hero {{ margin-bottom: 18px; }}
    .eyebrow {{
      display: inline-block;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1, h2, h3 {{ margin: 0 0 10px; letter-spacing: -0.02em; }}
    h1 {{ font-size: 30px; }}
    h2 {{ font-size: 18px; }}
    p {{ line-height: 1.6; }}
    .lede {{ margin: 0; color: var(--muted); max-width: 900px; }}
    .card-kicker {{
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .muted {{ color: var(--muted); }}
    textarea, input {{
      width: 100%;
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      font: inherit;
    }}
    textarea {{ min-height: 70vh; resize: vertical; }}
    button {{
      background: var(--text);
      color: white;
      border: 1px solid var(--text);
      padding: 10px 14px;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
    }}
    button:hover {{
      opacity: 0.92;
    }}
    .preview {{ min-height: 70vh; overflow: auto; }}
    .preview-shell.focus-content .discussion-block {{ opacity: 0.35; }}
    .preview-shell.focus-discussion .markdown-block {{ opacity: 0.35; }}
    .preview-shell.collapsed .discussion-block {{ display: none; }}
    .discussion-block, .discussion-tools, .cards-list {{ margin-top: 16px; }}
    .discussion-thread {{
      border-left: 1.5px solid rgba(15, 23, 42, 0.18);
      padding-left: 12px;
      margin: 14px 0;
    }}
    .discussion-status {{
      margin-left: 8px;
      color: var(--success);
      border: 1px solid var(--success);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
    }}
    .discussion-reply {{ margin: 10px 0 0 12px; padding-left: 12px; border-left: 0.5px dashed rgba(226, 232, 240, 0.9); }}
    .cards-list {{ display: grid; gap: 12px; }}
    .requirement-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      background: var(--surface-alt);
    }}
    .chip-row {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }}
    .chip {{ border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; color: var(--muted); }}
    .chip-toggle {{
      border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px;
      font-size: 12px; cursor: pointer; background: var(--surface); color: var(--muted);
      opacity: 0.5;
    }}
    .chip-toggle.on {{ opacity: 1; border-color: var(--success, #16a34a); color: var(--success, #16a34a); }}
    .chip-toggle:hover {{ opacity: 0.8; }}
    .xref-link {{
      color: var(--muted); text-decoration: underline dashed; text-underline-offset: 2px;
      cursor: pointer; font-weight: 500;
    }}
    .xref-link:hover {{ color: var(--text); text-decoration: underline; }}
    .xref-link.xref-cross {{ border-bottom: 1px dotted var(--border-strong); }}
    .xref-back {{
      position: sticky; top: 0; z-index: 10; display: inline-flex; align-items: center; gap: 4px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
      padding: 4px 10px; font-size: 12px; cursor: pointer; color: var(--muted);
      margin-bottom: 8px;
    }}
    .xref-back:hover {{ background: var(--surface-alt); color: var(--text); }}
    .model-chip {{
      border: 1px solid var(--border-strong);
      background: var(--surface-alt);
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 8px;
      cursor: grab;
    }}
    .binding-card {{
      border: 1px dashed var(--border);
      border-radius: 8px;
      padding: 10px;
      background: var(--surface-alt);
    }}
    .binding-card.is-bound {{ border-style: solid; border-color: var(--border-strong); }}
    .binding-card.drag-over {{ border-color: var(--text); background: #f5f5f5; }}
    .binding-card-head {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 4px; }}
    .binding-current {{ font-size: 13px; }}
    .clear-binding {{
      display: inline-flex; align-items: center; gap: 3px;
      background: none; border: 1px solid var(--border); border-radius: 6px;
      padding: 2px 6px; font-size: 12px; color: var(--muted); cursor: pointer; line-height: 1.4;
    }}
    .clear-binding:hover {{ background: var(--surface); color: var(--text); border-color: var(--border-strong); }}
    .clear-binding .clear-label {{ font-size: 11px; }}
    .binding-card:not(.is-bound) .clear-binding {{ display: none; }}
    .binding-meta {{ color: var(--muted); font-size: 13px; }}
    .meta {{ margin: 12px 0; color: var(--muted); }}
    .thread-item {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      margin-top: 10px;
      background: var(--surface-alt);
    }}
    .banner {{ margin: 12px 0; border-color: #fecaca; color: var(--danger); background: #fef2f2; display: flex; align-items: center; gap: 8px; padding: 10px 14px; }}
    .banner[hidden] {{ display: none !important; }}
    .banner-msg {{ flex: 1; }}
    .banner-close {{ background: none; border: none; font-size: 18px; cursor: pointer; color: inherit; padding: 0 4px; line-height: 1; border-radius: 3px; }}
    .banner-close:hover {{ background: rgba(239,68,68,0.15); }}
    pre {{ overflow: auto; background: var(--surface-alt); padding: 12px; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid var(--border); padding: 8px; text-align: left; }}
    blockquote {{
      margin: 16px 0;
      padding-left: 16px;
      border-left: 2px solid var(--border-strong);
      color: var(--muted);
    }}
    @media (max-width: 1100px) {{
      .app-shell {{ grid-template-columns: 1fr; }}
      .sidebar {{
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--border);
      }}
      .workspace {{ padding: 20px; }}
      .editor-grid, .models-grid {{ grid-template-columns: 1fr; }}
      .pane-container {{ flex-direction: column; }}
    }}
    /* Pane layout: each pane sized so 50-80 Chinese chars fit per line.
       min-width is 0 so flex can distribute evenly; when only one pane
       is open we constrain it so 50-80 Chinese chars still fit and the
       remaining space becomes whitespace on both sides. */
    .pane-container {{
      display: flex;
      gap: 1px;
      min-height: calc(100vh - 2px);
      width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
    }}
    .page-docs .workspace {{
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .page-docs .workspace-inner {{
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }}
    .page-docs .pane-container {{
      min-height: 0;
      flex: 1;
    }}
    .pane {{
      flex: 1 1 0;
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      background: var(--surface);
      overflow: hidden;
    }}
    .pane-container > .pane:only-child {{
      flex: 0 1 720px;
      max-width: 720px;
      margin: 0 auto;
    }}
    .pane-bar {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-alt);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .file-select {{
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 13px;
      background: var(--surface);
      max-width: 160px;
    }}
    .pane-title {{
      font-size: 13px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .save-time {{
      flex: 1;
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }}
    .pane-tools {{
      display: flex;
      gap: 2px;
    }}
    .icon-btn {{
      width: 30px;
      height: 30px;
      border: 1px solid transparent;
      border-radius: 5px;
      background-color: transparent;
      background-repeat: no-repeat;
      background-position: center;
      background-size: 14px;
      cursor: pointer;
      font-size: 15px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      opacity: 0.85;
      transition: all 0.15s;
    }}
    .icon-btn:hover {{
      background-color: var(--surface);
      border-color: var(--border);
      color: var(--text);
      opacity: 1;
    }}
    .icon-btn.close {{
      margin-left: 4px;
    }}
    .icon-btn.active {{
      background-color: var(--surface-alt);
      border-color: var(--border-strong);
      color: var(--text);
      opacity: 1;
    }}
    .icon-next {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='5' y1='12' x2='19' y2='12'/%3E%3Cpolyline points='12 5 19 12 12 19'/%3E%3C/svg%3E"); }}
    .icon-collapse {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E"); }}
    .icon-filter {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3'/%3E%3C/svg%3E"); }}
    .icon-unresolved {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpolyline points='8 12 12 16 16 12'/%3E%3Cline x1='12' y1='8' x2='12' y2='16'/%3E%3C/svg%3E"); }}
    .icon-split {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='20' height='18' x='2' y='3' rx='2'/%3E%3Cpath d='M12 3v18'/%3E%3C/svg%3E"); }}
    .icon-save {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z'/%3E%3Cpolyline points='17 21 17 13 7 13 7 21'/%3E%3Cpolyline points='7 3 7 8 15 8'/%3E%3C/svg%3E"); }}
    .icon-reload {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='23 4 23 10 17 10'/%3E%3Cpolyline points='1 20 1 14 7 14'/%3E%3Cpath d='M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15'/%3E%3C/svg%3E"); }}
    .icon-close {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='18' y1='6' x2='6' y2='18'/%3E%3Cline x1='6' y1='6' x2='18' y2='18'/%3E%3C/svg%3E"); }}
    .vditor-mount {{
      flex: 1;
      min-height: 0;
      overflow: auto;
    }}
    /* Vditor overrides */
    .vditor {{ border: 0; height: 100%; }}
    .vditor-toolbar {{ display: none; }}
    /* Table styling: header distinct, no vertical borders, body no bg */
    .vditor-ir table, .vditor-wysiwyg table {{
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0;
    }}
    .vditor-ir table th, .vditor-wysiwyg table th {{
      font-weight: 600;
      background: var(--surface-alt);
      border: none;
      border-bottom: 2px solid var(--border-strong);
      padding: 8px 12px;
      text-align: left;
    }}
    .vditor-ir table td, .vditor-wysiwyg table td {{
      border: none;
      border-bottom: 1px solid var(--border);
      background: transparent;
      padding: 8px 12px;
    }}
    .vditor-ir table tr, .vditor-wysiwyg table tr {{
      border: none;
    }}
    /* Discussion thread styling */
    .vditor-ir blockquote blockquote blockquote {{
      border-left: 2px solid var(--border-strong);
      padding: 8px 12px;
      margin: 10px 0;
      background: var(--surface-alt);
      border-radius: 0 4px 4px 0;
    }}
    .pane.discussions-collapsed .vditor-ir [data-discussion="1"] {{
      height: 22px;
      overflow: hidden;
      border-left: 3px solid var(--border-strong);
      background: var(--surface-alt);
      border-radius: 0 4px 4px 0;
      margin: 2px 0;
      padding: 3px 8px;
      position: relative;
      cursor: pointer;
    }}
    .pane.discussions-collapsed .vditor-ir [data-discussion="1"] > * {{
      display: none;
    }}
    .pane.discussions-collapsed .vditor-ir [data-discussion="1"][data-resolved="1"]::before {{
      content: '✓ discussion collapsed';
      font-size: 12px;
      color: var(--success, #22c55e);
    }}
    .pane.discussions-collapsed .vditor-ir [data-discussion="1"]:not([data-resolved="1"])::before {{
      content: '⚠ unresolved discussion collapsed';
      font-size: 12px;
      color: var(--warning, #f59e0b);
    }}
  </style>
  {head_extra}
</head>
<body class="page-{section}" data-actor-name="{_escape(user.username)}" data-ui-lang="{_escape(lang)}">
  <button class="sidebar-toggle" onclick="document.querySelector('.app-shell').classList.toggle('sidebar-collapsed')">☰</button>
  <div id="wiki-modal" class="wiki-modal" hidden>
    <div class="wiki-modal-backdrop">
      <div class="wiki-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="wiki-modal-title">
        <h2 class="wiki-modal-title">
          <span id="wiki-modal-title">更新 wiki</span>
          <span id="wiki-modal-elapsed" class="wiki-modal-elapsed">0:00</span>
        </h2>
        <ol class="wiki-modal-steps" id="wiki-modal-steps">
          <li class="wiki-modal-step" data-step="prepare">
            <span class="step-icon">1</span>
            <span class="step-label">准备中</span>
          </li>
          <li class="wiki-modal-step" data-step="agent">
            <span class="step-icon">2</span>
            <span class="step-label">调用 Agent 生成 llm wiki 中</span>
          </li>
          <li class="wiki-modal-step" data-step="apply">
            <span class="step-icon">3</span>
            <span class="step-label">应用更新</span>
          </li>
        </ol>
        <div class="wiki-modal-detail" id="wiki-modal-detail" hidden></div>
        <div class="wiki-modal-actions">
          <button type="button" id="wiki-modal-dismiss" class="ghost-button" style="display: none;">关闭</button>
        </div>
      </div>
    </div>
  </div>
  <div class="app-shell">
    <aside class="sidebar">
      {sidebar}
    </aside>
    <main class="workspace" id="workspace">
      <div class="workspace-inner" id="workspace-inner">
        {body}
      </div>
    </main>
  </div>
  {script}
  <script>
    document.querySelectorAll('[data-action="logout"]').forEach((button) => {{
      button.addEventListener('click', async () => {{
        await fetch('/api/auth/logout', {{ method: 'POST' }});
        location.href = '/login';
      }});
    }});
    const wikiRefreshBtn = document.getElementById('wiki-refresh');
    if (wikiRefreshBtn) {{
      const modalEl = document.getElementById('wiki-modal');
      const modalElapsed = document.getElementById('wiki-modal-elapsed');
      const modalDetail = document.getElementById('wiki-modal-detail');
      const modalDismiss = document.getElementById('wiki-modal-dismiss');
      const stepEls = {{
        prepare: modalEl ? modalEl.querySelector('[data-step="prepare"]') : null,
        agent:   modalEl ? modalEl.querySelector('[data-step="agent"]')   : null,
        apply:   modalEl ? modalEl.querySelector('[data-step="apply"]')   : null,
      }};

      function fmtElapsed(ms) {{
        const s = Math.floor(ms / 1000);
        const m = Math.floor(s / 60);
        return m + ':' + String(s % 60).padStart(2, '0');
      }}

      let elapsedTimer = null;
      function startElapsed() {{
        if (elapsedTimer) return;
        const start = Date.now();
        elapsedTimer = setInterval(() => {{
          if (modalElapsed) modalElapsed.textContent = fmtElapsed(Date.now() - start);
        }}, 1000);
      }}
      function stopElapsed() {{
        if (elapsedTimer) {{ clearInterval(elapsedTimer); elapsedTimer = null; }}
      }}

      function resetSteps() {{
        for (const k of Object.keys(stepEls)) {{
          const el = stepEls[k];
          if (!el) continue;
          el.classList.remove('active', 'done', 'failed');
          const icon = el.querySelector('.step-icon');
          if (icon) icon.textContent = String(Object.keys(stepEls).indexOf(k) + 1);
          const label = el.querySelector('.step-label');
          if (label) label.textContent = label.dataset.default || label.textContent;
        }}
      }}
      function setStep(key, state, label) {{
        const el = stepEls[key];
        if (!el) return;
        el.classList.remove('active', 'done', 'failed');
        el.classList.add(state);
        const icon = el.querySelector('.step-icon');
        if (icon) {{
          icon.textContent = state === 'done' ? '\u2713' :
                             state === 'failed' ? '\u2717' :
                             (icon.dataset.idx || Object.keys(stepEls).indexOf(key) + 1);
        }}
        const lbl = el.querySelector('.step-label');
        if (lbl && label) lbl.textContent = label;
      }}
      // Cache default labels so resetSteps() can restore them.
      for (const el of Object.values(stepEls)) {{
        if (!el) continue;
        const lbl = el.querySelector('.step-label');
        if (lbl) lbl.dataset.default = lbl.textContent;
        const icon = el.querySelector('.step-icon');
        if (icon) icon.dataset.idx = icon.textContent;
      }}

      function showModal() {{
        modalEl.hidden = false;
        resetSteps();
        setStep('prepare', 'active');
        modalElapsed.textContent = '0:00';
        modalDetail.hidden = true;
        modalDetail.textContent = '';
        modalDismiss.style.display = 'none';
        startElapsed();
      }}
      function hideModal() {{
        modalEl.hidden = true;
        stopElapsed();
        wikiRefreshBtn.dataset.busy = '0';
      }}
      function showDetail(text) {{
        modalDetail.textContent = text;
        modalDetail.hidden = false;
      }}

      if (modalDismiss) {{
        modalDismiss.addEventListener('click', hideModal);
      }}

      wikiRefreshBtn.addEventListener('click', async (e) => {{
        e.preventDefault();
        e.stopPropagation();
        if (wikiRefreshBtn.dataset.busy === '1') return;
        wikiRefreshBtn.dataset.busy = '1';
        showModal();
        setStep('prepare', 'done', '准备完成');
        setStep('agent', 'active', '调用 Agent 生成 llm wiki 中');
        try {{
          const resp = await fetch('/api/wiki/refresh', {{ method: 'POST' }});
          setStep('agent', 'done', 'Agent 已返回');
          setStep('apply', 'active', '应用更新中');
          const data = await resp.json();
          if (!resp.ok) {{
            setStep('apply', 'failed', '更新失败 (HTTP ' + resp.status + ')');
            showDetail((data && data.error) || ('HTTP ' + resp.status));
            modalDismiss.style.display = '';
            modalDismiss.textContent = '关闭';
            hideModal.bind(null); // no-op; button stays
            return;
          }}
          if (data.ok) {{
            setStep('apply', 'done', '完成');
            showDetail('页面即将刷新…');
            stopElapsed();
            setTimeout(() => location.reload(), 600);
            return;
          }}
          // Non-zero exit (e.g. agent failed). Show stderr + hint if present.
          const stderrTail = (data.stderr || '').split('\\n').filter(Boolean).slice(-3).join('\\n');
          const detail = [
            data.hint ? '提示：' + data.hint : null,
            stderrTail ? stderrTail : null,
            '详见服务器日志。',
          ].filter(Boolean).join('\\n\\n');
          setStep('apply', 'failed', '更新失败 (exit ' + data.returncode + ')');
          showDetail(detail);
          modalDismiss.style.display = '';
          modalDismiss.textContent = '关闭';
          stopElapsed();
          wikiRefreshBtn.dataset.busy = '0';
        }} catch (err) {{
          setStep('apply', 'failed', '网络错误');
          showDetail(err.message || String(err));
          modalDismiss.style.display = '';
          modalDismiss.textContent = '关闭';
          stopElapsed();
          wikiRefreshBtn.dataset.busy = '0';
        }}
      }});
      // Note: no polling on page load — the current /api/wiki/refresh is
      // synchronous (subprocess.run blocks until the agent finishes). When
      // we move to an async job queue, also add a status endpoint AND
      // register it BEFORE the /api/wiki/<page:path> wildcard route.
    }}
  </script>
</body>
</html>"""


def _sidebar_html(
    store: ProjectStore,
    user: AuthenticatedUser,
    lang: str,
    section: str,
    current_doc_name: str,
    current_wiki_page: str,
    current_spec_id: str = "",
) -> str:
    spec_id = current_spec_id or store.resolve_spec_id()
    all_specs = store.list_spec_ids()
    docs = store.list_spec_documents(spec_id)
    wiki_groups = _group_wiki_pages(store.list_wiki_pages(), lang)
    spec_options = "".join(
        f'<option value="{_escape(s)}"{(" selected" if s == spec_id else "")}>{_escape(s)}</option>'
        for s in all_specs
    )
    return f"""
    <div class="brand-card">
      <a class="brand" href="/">
        <div class="brand-title">Lòukè</div>
      </a>
      <select class="spec-select" onchange="if(this.value)location.href='/docs/'+this.value+'/spec'">
        {spec_options}
      </select>
      <div class="user-row">
        <div class="user-name">{_escape(user.username)}</div>
        <button type="button" class="ghost-button" data-action="logout">{_escape(_t(lang, "sidebar.logout"))}</button>
      </div>
    </div>
    <div class="nav-section">
      <div class="nav-label">{_escape(_t(lang, "sidebar.main"))}</div>
      <a class="{_nav_link_class(section == "models")}" href="/models">{_escape(_t(lang, "nav.models"))}</a>
      <a class="{_nav_link_class(section == "docs")}" href="/docs/{_escape(spec_id)}/spec">{_escape(_t(lang, "nav.docs"))}</a>
      {_docs_sublinks(spec_id, docs, current_doc_name)}
      <div class="nav-link-row">
        <a class="{_nav_link_class(section == "wiki")}" href="/wiki" style="flex: 1;">llm wiki</a>
        <button type="button" class="wiki-refresh-btn" id="wiki-refresh" title="Refresh wiki via librarian">↻</button>
      </div>
      {_wiki_sublinks(wiki_groups, current_wiki_page)}
    </div>
    """


def _docs_sublinks(
    spec_id: str, docs: list[dict[str, str]], current_doc_name: str
) -> str:
    if not docs:
        return ""
    links = []
    for item in docs:
        links.append(
            f'<a class="{_nav_sublink_class(item["doc_name"] == current_doc_name)}" '
            f'href="/docs/{_escape(spec_id)}/{_escape(item["doc_name"])}">{_escape(item["doc_name"])}</a>'
        )
    return f"""
    <div class="nav-sublinks">
      <div class="nav-subgroup">
        <div class="nav-subtitle">{_escape(spec_id)}</div>
        {"".join(links)}
      </div>
    </div>
    """


def _wiki_sublinks(
    groups: dict[str, list[dict[str, str]]], current_wiki_page: str
) -> str:
    if not groups:
        return ""
    chunks = []
    for group_name, items in groups.items():
        links = []
        for item in items:
            links.append(
                f'<a class="{_nav_sublink_class(item["page"] == current_wiki_page)}" '
                f'href="/wiki/{_quote_path(item["page"])}">{_escape(item["label"])}</a>'
            )
        chunks.append(
            f'<div class="nav-subgroup"><div class="nav-subtitle">{_escape(group_name)}</div>{"".join(links)}</div>'
        )
    return f'<div class="nav-sublinks">{"".join(chunks)}</div>'


def _group_wiki_pages(
    pages: list[dict[str, str]], lang: str
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in pages:
        parts = item["page"].split("/")
        if len(parts) == 1:
            group_name = _t(lang, "wiki.root")
            label = parts[0]
        else:
            group_name = parts[0]
            label = "/".join(parts[1:])
        grouped[group_name].append({"page": item["page"], "label": label})
    return dict(sorted(grouped.items(), key=lambda entry: entry[0]))


def _nav_link_class(active: bool) -> str:
    return "nav-link active" if active else "nav-link"


def _nav_sublink_class(active: bool) -> str:
    return "nav-sublink active" if active else "nav-sublink"


def _models_page_script(lang: str) -> str:
    strings = json.dumps(_script_strings(lang, "models"), ensure_ascii=False)
    return f"""
    <script>
    const actorName = document.body.dataset.actorName;
    const strings = {strings};
    const meta = document.getElementById('meta');
    const banner = document.getElementById('banner');
    const modelList = document.getElementById('model-list');
    const roleList = document.getElementById('role-list');
    const agentList = document.getElementById('agent-list');
    let state = null;

    function showBanner(message) {{
      banner.hidden = false;
      banner.textContent = message;
    }}

    function clearBanner() {{
      banner.hidden = true;
      banner.textContent = '';
    }}

    function render() {{
      if (!state) return;
      meta.textContent = `${{strings.lastModified}}: ${{state.last_modified_by || strings.unknown}} @ ${{state.updated_at || strings.notRecorded}}`;
      modelList.innerHTML = state.catalog.map((item) => `
        <div class="model-chip" draggable="true" data-model="${{item.abstract}}">
          <div><strong>${{item.abstract}}</strong></div>
          <div class="binding-meta">${{item.full || '未解析'}}</div>
        </div>
      `).join('');
      roleList.innerHTML = Object.keys(state.roster).map((role) => renderTarget('role', role, state.resolved.roles[role])).join('');
      agentList.className = 'binding-list is-agents';
      agentList.innerHTML = Object.entries(state.resolved.agents).map(([agent, resolved]) => renderTarget('agent', agent, resolved)).join('');
      bindDnD();
    }}

    function renderTarget(kind, id, resolved) {{
      const current = resolved.abstract || strings.unbound;
      const isBound = !!resolved.abstract;
      return `
        <div class="binding-card${{isBound ? ' is-bound' : ''}}" data-kind="${{kind}}" data-id="${{id}}">
          <div class="binding-card-head">
            <strong>${{id}}</strong>
            ${{isBound ? `<button class="clear-binding" data-kind="${{kind}}" data-id="${{id}}" title="${{strings.revertFactory}}"><span aria-hidden="true">↺</span><span class="clear-label">${{strings.revertFactory}}</span></button>` : ''}}
          </div>
          <div class="binding-current">${{current}}</div>
          <div class="binding-meta">${{strings.source}}: ${{resolved.source || ''}}${{resolved.role ? ' / role=' + resolved.role : ''}}</div>
          <div class="binding-meta">${{resolved.full || strings.unresolvedFullModel}}</div>
        </div>
      `;
    }}

    function bindDnD() {{
      document.querySelectorAll('.model-chip').forEach((item) => {{
        item.addEventListener('dragstart', (event) => {{
          event.dataTransfer.setData('text/plain', item.dataset.model);
        }});
      }});
      document.querySelectorAll('.binding-card').forEach((card) => {{
        card.addEventListener('dragover', (event) => {{
          event.preventDefault();
          card.classList.add('drag-over');
        }});
        card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
        card.addEventListener('drop', async (event) => {{
          event.preventDefault();
          card.classList.remove('drag-over');
          const model = event.dataTransfer.getData('text/plain');
          if (!model) return;
          const kind = card.dataset.kind;
          const id = card.dataset.id;
          if (kind === 'role') state.assignments.roles[id] = model;
          if (kind === 'agent') state.assignments.agents[id] = model;
          await persist();
        }});
      }});
      document.querySelectorAll('.clear-binding').forEach((button) => {{
        button.addEventListener('click', async () => {{
          const kind = button.dataset.kind;
          const id = button.dataset.id;
          if (kind === 'role') delete state.assignments.roles[id];
          if (kind === 'agent') delete state.assignments.agents[id];
          await persist();
        }});
      }});
    }}

    async function persist() {{
      clearBanner();
      const response = await fetch('/api/bindings', {{
        method: 'PUT',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          version_token: state.version_token,
          aliases: state.aliases,
          assignments: state.assignments
        }})
      }});
      const data = await response.json();
      if (!response.ok) {{
        showBanner(data.error || strings.saveBindingsFailed);
        return;
      }}
      state = data;
      render();
    }}

    async function load() {{
      const response = await fetch('/api/bindings');
      state = await response.json();
      render();
    }}

    const events = new EventSource('/api/events');
    events.addEventListener('bindings.updated', async (event) => {{
      const data = JSON.parse(event.data);
      if (data.actor_name !== actorName) {{
        showBanner(strings.bindingsUpdated.replace('{{actor}}', data.actor_name));
        await load();
      }}
    }});

    load();
    </script>
    """


def _wiki_editor_script(api_path: str, actor_name: str, lang: str) -> str:
    config = json.dumps(
        {"apiPath": api_path, "actorName": actor_name, "lang": lang},
        ensure_ascii=False,
    )
    js = """<script>
const cfg = __CONFIG__;
const banner = document.getElementById('banner');
const saveBtn = document.getElementById('save-btn');
const reloadBtn = document.getElementById('reload-btn');
const saveTimeEl = document.getElementById('save-time');
let vditor = null, vditorReady = false, versionToken = '', autosaveTimer = null;

function showBanner(msg) { banner.hidden = false; banner.textContent = msg; }

async function load() {
  try {
    const resp = await fetch(cfg.apiPath, { headers: { Accept: 'application/json' } });
    const data = await resp.json();
    if (!resp.ok) { showBanner(data.error || 'Load failed'); return; }
    versionToken = data.version_token || '';
    if (vditorReady && vditor) { vditor.setValue(data.body_md || ''); }
    else { initVditor(data.body_md || ''); }
    if (data.updated_at) {
      saveTimeEl.textContent = 'Last Saved: ' + new Date(data.updated_at).toLocaleTimeString('en-GB');
    }
  } catch(e) { showBanner('Error: ' + e.message); }
}

function initVditor(initialMd) {
  if (typeof Vditor === 'undefined') {
    const mount = document.getElementById('vditor-0');
    mount.innerHTML = '<textarea style="width:100%;height:100%;border:0;outline:none;padding:12px;font-family:monospace;" spellcheck="false"></textarea>';
    const ta = mount.querySelector('textarea');
    ta.value = initialMd;
    vditor = { getValue: () => ta.value, setValue: (v) => { ta.value = v; } };
    vditorReady = true;
    return;
  }
  vditor = new Vditor('vditor-0', {
    mode: 'ir', value: initialMd, height: '100%',
    toolbar: false, cache: { enable: false },
    after: () => { vditorReady = true; },
    input: () => {
      clearTimeout(autosaveTimer);
      autosaveTimer = setTimeout(() => save(false), 5000);
    }
  });
}

async function save(force) {
  if (!vditorReady) return;
  const resp = await fetch(cfg.apiPath, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body_md: vditor.getValue(), version_token: versionToken, force: !!force })
  });
  const data = await resp.json();
  if (!resp.ok) { showBanner(data.error || 'Save failed'); return; }
  versionToken = data.version_token || '';
  saveTimeEl.textContent = 'Last Saved: ' + new Date().toLocaleTimeString('en-GB');
}

saveBtn.addEventListener('click', () => { clearTimeout(autosaveTimer); save(false); });
reloadBtn.addEventListener('click', load);
load();
</script>"""
    return js.replace("__CONFIG__", config)


def _editor_page_script(
    spec_id: str,
    doc_name: str,
    docs: list[dict[str, str]],
    actor_name: str,
    lang: str,
) -> str:
    config = json.dumps(
        {
            "specId": spec_id,
            "initialDoc": doc_name,
            "docList": [d["doc_name"] for d in docs],
            "actorName": actor_name,
        },
        ensure_ascii=False,
    )
    js = """<script>
const cfg = __CONFIG__;
const banner = document.getElementById('banner');
const paneContainer = document.getElementById('pane-container');
const panes = [];
let paneSeq = 0;

let _bannerTimer = null;
function showBanner(msg) {
  const span = banner.querySelector('.banner-msg');
  if (span) span.textContent = msg; else banner.textContent = msg;
  banner.hidden = false;
  clearTimeout(_bannerTimer);
  _bannerTimer = setTimeout(function() { banner.hidden = true; }, 4000);
}
function clearBanner() { banner.hidden = true; clearTimeout(_bannerTimer); }
banner.addEventListener('click', function(e) {
  if (e.target.classList.contains('banner-close')) { banner.hidden = true; clearTimeout(_bannerTimer); }
});

function buildOptions(selected) {
  return cfg.docList.map(d =>
    '<option value="' + d + '"' + (d === selected ? ' selected' : '') + '>' + d + '</option>'
  ).join('');
}

function createPane(docName) {
  if (panes.length >= 4) { showBanner('Max 4 panes'); return -1; }
  const id = paneSeq++;
  const el = document.createElement('div');
  el.className = 'pane';
  el.dataset.paneId = id;
  el.innerHTML =
    '<div class="pane-bar">' +
      '<select class="file-select">' + buildOptions(docName) + '</select>' +
      '<span class="save-time">Last Saved: --:--:--</span>' +
      '<div class="pane-tools">' +
        '<button class="icon-btn icon-next" data-action="next-discussion" title="Next discussion"></button>' +
        '<button class="icon-btn icon-collapse" data-action="collapse" title="Collapse discussions"></button>' +
        '<button class="icon-btn icon-unresolved" data-action="next-unresolved" title="Next unresolved FR/NFR/AC"></button>' +
        '<button class="icon-btn icon-split" data-action="split" title="Split pane"></button>' +
        '<button class="icon-btn icon-save" data-action="save" title="Save"></button>' +
        '<button class="icon-btn icon-reload" data-action="reload" title="Reload"></button>' +
        '<button class="icon-btn icon-close close" data-action="close" title="Close pane"></button>' +
      '</div>' +
    '</div>' +
    '<div class="vditor-mount" id="vditor-' + id + '"></div>';
  paneContainer.appendChild(el);

  const state = {
    id, el, vditor: null, vditorReady: false,
    apiPath: '', versionToken: '', docName: '',
    autosaveTimer: null, collapsed: false, filterOn: false,
  };
  panes.push(state);

  const fileSelect = el.querySelector('.file-select');
  fileSelect.addEventListener('change', () => loadDoc(id, fileSelect.value));
  el.querySelectorAll('.icon-btn').forEach(btn => {
    btn.addEventListener('click', () => handleAction(id, btn.dataset.action, btn));
  });

  updatePaneHost();
  if (docName) loadDoc(id, docName);
  return id;
}

// Toggle the pane-host class on workspace / workspace-inner so the
// comfortable 28px padding and 1600px reading-width cap are reclaimed
// only when the pane layout actually needs the extra space.
//
// Decision: compute per-pane width in both normal and pane-host modes.
// If normal mode already gives every pane >= 50 chars (~800px), keep
// the padding. Otherwise switch to pane-host to reclaim the space.
function updatePaneHost() {
  const ws = document.getElementById('workspace');
  const inner = document.getElementById('workspace-inner');
  if (!ws || !inner) return;
  const needs = needsPaneHost();
  ws.classList.toggle('pane-host', needs);
  inner.classList.toggle('pane-host', needs);
}

function needsPaneHost() {
  if (panes.length === 0) return false;
  const ws = document.getElementById('workspace');
  if (!ws) return false;
  const wsWidth = ws.getBoundingClientRect().width;
  // Normal mode: 28px padding each side, inner capped at 1600px
  const normalPerPane = Math.min(wsWidth - 56, 1600) / panes.length;
  // 50 Chinese chars ~= 800px at 16px font
  // If normal mode gives each pane enough width, keep the comfortable padding
  if (normalPerPane >= 800) return false;
  // Otherwise reclaim the padding to give panes more room
  return true;
}

window.addEventListener('resize', updatePaneHost);
// Also observe workspace size changes (e.g. sidebar collapse/expand)
if (typeof ResizeObserver !== 'undefined') {
  const _ro = new ResizeObserver(() => updatePaneHost());
  document.addEventListener('DOMContentLoaded', () => {
    const ws = document.getElementById('workspace');
    if (ws) _ro.observe(ws);
  });
}

async function loadDoc(paneId, docName) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  pane.docName = docName;
  pane.apiPath = '/api/docs/' + cfg.specId + '/' + docName;
  try {
    const resp = await fetch(pane.apiPath, { headers: { Accept: 'application/json' } });
    const data = await resp.json();
    if (!resp.ok) { showBanner(data.error || 'Load failed'); return; }
    pane.versionToken = data.version_token || '';
    if (pane.vditorReady && pane.vditor) {
      pane.vditor.setValue(data.body_md || '');
      postProcessDiscussions(paneId);
    } else {
      initVditor(paneId, data.body_md || '');
    }
    updateSaveTime(paneId, data.updated_at);
  } catch(e) { showBanner('Network error: ' + e.message); }
}

function initVditor(paneId, initialMd) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  if (typeof Vditor === 'undefined') {
    const mount = pane.el.querySelector('.vditor-mount');
    mount.innerHTML = '<textarea style="width:100%;height:100%;border:0;outline:none;padding:12px;font-family:monospace;" spellcheck="false"></textarea>';
    const ta = mount.querySelector('textarea');
    ta.value = initialMd;
    pane.vditor = { getValue: () => ta.value, setValue: (v) => { ta.value = v; } };
    pane.vditorReady = true;
    ta.addEventListener('input', () => {
      clearTimeout(pane.autosaveTimer);
      pane.autosaveTimer = setTimeout(() => saveDoc(paneId, false), 5000);
    });
    return;
  }
  pane.vditor = new Vditor('vditor-' + paneId, {
    mode: 'ir', value: initialMd, height: '100%',
    toolbar: false, cache: { enable: false },
    after: () => { pane.vditorReady = true; postProcessDiscussions(paneId); },
    input: () => {
      clearTimeout(pane.autosaveTimer);
      pane.autosaveTimer = setTimeout(() => saveDoc(paneId, false), 5000);
      clearTimeout(pane._discTimer);
      pane._discTimer = setTimeout(() => postProcessDiscussions(paneId), 800);
    }
  });
}

async function saveDoc(paneId, force) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane || !pane.vditorReady) return;
  try {
    const resp = await fetch(pane.apiPath, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body_md: pane.vditor.getValue(), version_token: pane.versionToken, force: !!force })
    });
    const data = await resp.json();
    if (resp.status === 409 && !force) {
      showBanner('Conflict: ' + (data.error || '') + ' — click reload to discard, or save again to force.');
      return;
    }
    if (!resp.ok) { showBanner(data.error || 'Save failed'); return; }
    pane.versionToken = data.version_token || '';
    updateSaveTime(paneId, new Date().toISOString());
  } catch(e) { showBanner('Save error: ' + e.message); }
}

function updateSaveTime(paneId, timeStr) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  const el = pane.el.querySelector('.save-time');
  if (el && timeStr) {
    const d = new Date(timeStr);
    const time = isNaN(d) ? timeStr : d.toLocaleTimeString('en-GB');
    el.textContent = 'Last Saved: ' + time;
  }
}

function handleAction(paneId, action, btn) {
  switch(action) {
    case 'next-discussion': nextDiscussion(paneId); break;
    case 'collapse': toggleCollapse(paneId, btn); break;
    case 'next-unresolved': nextUnresolved(paneId); break;
    case 'split': createPane(null); break;
    case 'save': clearTimeout(panes.find(p=>p.id===paneId)?.autosaveTimer); saveDoc(paneId, false); break;
    case 'reload': loadDoc(paneId, panes.find(p=>p.id===paneId)?.docName); break;
    case 'close': closePane(paneId); break;
  }
}

function closePane(paneId) {
  if (panes.length <= 1) { showBanner('Cannot close the last pane'); return; }
  const idx = panes.findIndex(p => p.id === paneId);
  if (idx === -1) return;
  const pane = panes[idx];
  if (pane.vditor && typeof pane.vditor.destroy === 'function') {
    try { pane.vditor.destroy(); } catch(e) {}
  }
  clearTimeout(pane.autosaveTimer);
  clearTimeout(pane._discTimer);
  pane.el.remove();
  panes.splice(idx, 1);
  updatePaneHost();
}

function isResolvedText(text) {
  if (!text) return false;
  return /\u2713|\[resolved\]|\[已决定\]|\[已解决\]|\[Decided\]|\[decided\]|\[wontfix\]/.test(text);
}

function isDiscussionText(text) {
  if (!text) return false;
  return /\[T-\d{3,4}\]/.test(text)
      || /\b(Sage|Lex|Aaron|Devon|Archer|Maestro|Probe|Scout)\b\s*:/.test(text)
      || /\u2713|\[resolved\]|\[decided\]|\[wontfix\]/.test(text);
}

function postProcessDiscussions(paneId) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane || !pane.vditorReady) return;
  const ir = pane.el.querySelector('.vditor-ir');
  if (!ir) return;
  ir.querySelectorAll('[data-discussion]').forEach(el => { delete el.dataset.discussion; delete el.dataset.resolved; });
  ir.querySelectorAll('blockquote').forEach(el => {
    el.dataset.discussion = '1';
    if (isResolvedText(el.textContent || '')) {
      el.dataset.resolved = '1';
    } else {
      delete el.dataset.resolved;
    }
  });
  ir.querySelectorAll('p, li').forEach(el => {
    const text = el.textContent || '';
    if (/\[T-\d{3,4}\]/.test(text)) {
      el.dataset.discussion = '1';
      if (isResolvedText(text)) { el.dataset.resolved = '1'; } else { delete el.dataset.resolved; }
    }
  });
}

function nextDiscussion(paneId) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  const ir = pane.el.querySelector('.vditor-ir');
  if (!ir) return;
  postProcessDiscussions(paneId);
  const discussions = Array.from(ir.querySelectorAll('[data-discussion="1"]'));
  if (discussions.length === 0) { showBanner('No discussions found'); return; }
  const mount = pane.el.querySelector('.vditor-mount');
  const mountTop = mount ? mount.getBoundingClientRect().top : 0;
  for (const el of discussions) {
    if (el.getBoundingClientRect().top > mountTop + 20) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
  }
  discussions[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
  showBanner('Wrapped to first discussion');
}

function toggleCollapse(paneId, btn) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  pane.collapsed = !pane.collapsed;
  pane.el.classList.toggle('discussions-collapsed', pane.collapsed);
  btn.classList.toggle('active', pane.collapsed);
}

function nextUnresolved(paneId) {
  const pane = panes.find(p => p.id === paneId);
  if (!pane) return;
  const ir = pane.el.querySelector('.vditor-ir');
  if (!ir) return;
  postProcessDiscussions(paneId);
  const all = Array.from(ir.querySelectorAll('h1, h2, h3, h4, h5, h6, [data-discussion="1"]'));
  const targets = [];
  let curHeading = null, curHasUnresolved = false, curHasDiscussion = false;
  function flush() {
    if (!curHeading) return;
    const text = curHeading.textContent.trim();
    if (!/^(FR|NFR|AC)-\d/.test(text)) return;
    if (curHasUnresolved || !curHasDiscussion) {
      targets.push({ el: curHeading, text: text, inconsistent: isResolvedText(text) && curHasUnresolved });
    }
  }
  for (const el of all) {
    if (/^H[1-6]$/.test(el.tagName)) {
      flush();
      curHeading = el;
      curHasUnresolved = false;
      curHasDiscussion = false;
    } else if (el.dataset.discussion === '1') {
      curHasDiscussion = true;
      if (el.dataset.resolved !== '1') curHasUnresolved = true;
    }
  }
  flush();
  const mount = pane.el.querySelector('.vditor-mount');
  const mountTop = mount ? mount.getBoundingClientRect().top : 0;
  if (targets.length === 0) {
    const unresolved = Array.from(ir.querySelectorAll('[data-discussion="1"]:not([data-resolved="1"])'));
    if (unresolved.length === 0) { showBanner('All FR/NFR/AC resolved \u2713'); return; }
    for (const el of unresolved) {
      if (el.getBoundingClientRect().top > mountTop + 20) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showBanner('Unresolved discussion (outside FR/NFR/AC)');
        return;
      }
    }
    unresolved[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
    showBanner('\u21bb Unresolved discussion (outside FR/NFR/AC)');
    return;
  }
  for (const t of targets) {
    if (t.el.getBoundingClientRect().top > mountTop + 20) {
      t.el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      showBanner((t.inconsistent ? '\u26a0 INCONSISTENT: ' : '') + t.text.substring(0, 50));
      return;
    }
  }
  const first = targets[0];
  first.el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  showBanner('\u21bb ' + (first.inconsistent ? '\u26a0 ' : '') + first.text.substring(0, 50));
}

createPane(cfg.initialDoc);
</script>"""
    return js.replace("__CONFIG__", config)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _quote_path(path: str) -> str:
    return quote(path, safe="/")


TRANSLATIONS = {
    "zh": {
        "home.eyebrow": "Workbench",
        "home.lede_before": "当前 spec: ",
        "home.lede_after": "。左侧 sidebar 常驻，模型、wiki、设计文档都从当前项目直接打开。",
        "home.models_desc": "拖拽角色或 Agent 绑定模型。",
        "home.docs_desc": "以 spec 目录为准，打开 spec / acceptance / test-plan 编辑与预览。",
        "home.wiki_desc": "浏览与编辑 `.louke/wiki/pages/`，支持按一级目录分组导航。",
        "nav.models": "模型绑定",
        "nav.docs": "设计文档",
        "models.lede": "左侧模型列表可拖到角色或 Agent 卡片上。新的命令解析与新启动 Agent 立刻生效；已在运行的会话不会热切换。",
        "models.catalog": "模型列表",
        "models.roles": "角色绑定",
        "models.agents": "Agent 绑定",
        "models.flow_hint": "模型 → 角色 → Agent（Agent 未单独绑定时继承其角色绑定）",
        "wiki.index_lede": "支持直接输入 `dir/page` 新建目录页；sidebar 会按一级目录自动归类。",
        "wiki.create_open": "新建并打开",
        "wiki.empty": "当前没有 wiki 页面。",
        "wiki.editor_lede": "左侧源码，右侧实时预览。编辑保存后立即写回当前项目页面。",
        "wiki.root": "根目录",
        "docs.title": "设计文档",
        "docs.lede": "双栏工作台，支持正文/讨论聚焦、讨论回复与卡片视图。",
        "docs.focus_content": "看正文",
        "docs.focus_discussion": "看讨论",
        "docs.toggle_collapse": "折叠讨论",
        "docs.inline_hint": "`inline-discussion` 默认弱化显示",
        "docs.discussion_actions": "讨论操作",
        "docs.new_discussion_placeholder": "新讨论内容",
        "docs.start_discussion": "发起讨论",
        "common.save": "保存",
        "common.reload": "重新加载",
        "common.markdown": "Markdown",
        "common.preview": "预览",
        "meta.not_recorded": "未记录更新时间",
        "sidebar.spec": "spec",
        "sidebar.signed_in": "已登录",
        "sidebar.logout": "退出",
        "sidebar.main": "主导航",
        "login.subtitle": "使用已有账号登录。",
        "login.create_first": "请先创建第一个账号。",
        "login.sign_in": "登录",
        "login.register": "注册",
        "login.username": "用户名",
        "login.password": "密码",
        "login.sign_in_button": "登录",
        "login.register_button": "注册并登录",
        "login.request_failed": "请求失败",
    },
    "en": {
        "home.eyebrow": "Workbench",
        "home.lede_before": "Current spec: ",
        "home.lede_after": ". The sidebar stays visible, and models, wiki, and design docs open from the current project.",
        "home.models_desc": "Drag roles or agents to bind models.",
        "home.docs_desc": "Open spec / acceptance / test-plan editors and previews from the current spec directory.",
        "home.wiki_desc": "Browse and edit `.louke/wiki/pages/` with first-level directory grouping in the sidebar.",
        "nav.models": "Model Bindings",
        "nav.docs": "Design Docs",
        "models.lede": "Drag models onto roles or agents. New commands and newly started agents pick up the change right away.",
        "models.catalog": "Model Catalog",
        "models.roles": "Role Bindings",
        "models.agents": "Agent Bindings",
        "models.flow_hint": "Models -> Roles -> Agents (an agent inherits its role binding unless overridden)",
        "wiki.index_lede": "Create nested pages with `dir/page`; the sidebar groups them by first-level directory.",
        "wiki.create_open": "Create & Open",
        "wiki.empty": "No wiki pages yet.",
        "wiki.editor_lede": "Source on the left, live preview on the right. Saving writes back to the current project page immediately.",
        "wiki.root": "root",
        "docs.title": "Design Document",
        "docs.lede": "Two-pane workspace with content/discussion focus, replies, and card view.",
        "docs.focus_content": "Focus Content",
        "docs.focus_discussion": "Focus Discussion",
        "docs.toggle_collapse": "Collapse Discussion",
        "docs.inline_hint": "`inline-discussion` is de-emphasized by default",
        "docs.discussion_actions": "Discussion Actions",
        "docs.new_discussion_placeholder": "New discussion content",
        "docs.start_discussion": "Start Discussion",
        "common.save": "Save",
        "common.reload": "Reload",
        "common.markdown": "Markdown",
        "common.preview": "Preview",
        "meta.not_recorded": "No timestamp recorded",
        "sidebar.spec": "spec",
        "sidebar.signed_in": "Signed In",
        "sidebar.logout": "Log Out",
        "sidebar.main": "Main",
        "login.subtitle": "Sign in with an existing account.",
        "login.create_first": "Create the first account to continue.",
        "login.sign_in": "Sign In",
        "login.register": "Register",
        "login.username": "Username",
        "login.password": "Password",
        "login.sign_in_button": "Sign In",
        "login.register_button": "Register & Sign In",
        "login.request_failed": "Request failed",
    },
}


def _t(lang: str, key: str) -> str:
    bundle = TRANSLATIONS.get(lang) or TRANSLATIONS["en"]
    if key in bundle:
        return bundle[key]
    return TRANSLATIONS["en"].get(key, key)


def _script_strings(lang: str, scope: str) -> dict[str, str]:
    if lang == "zh" and scope == "models":
        return {
            "lastModified": "最后修改",
            "unknown": "未知",
            "notRecorded": "未记录",
            "unbound": "未绑定",
            "source": "来源",
            "unresolvedFullModel": "未解析 full model",
            "revertFactory": "恢复出厂",
            "saveBindingsFailed": "保存绑定失败",
            "bindingsUpdated": "模型绑定已由 {{actor}} 更新，正在刷新视图",
        }
    if scope == "models":
        return {
            "lastModified": "Last modified",
            "unknown": "Unknown",
            "notRecorded": "Not recorded",
            "unbound": "Unbound",
            "source": "Source",
            "unresolvedFullModel": "Full model not resolved",
            "revertFactory": "Revert to factory",
            "saveBindingsFailed": "Failed to save bindings",
            "bindingsUpdated": "Bindings were updated by {{actor}}. Refreshing view.",
        }
    if lang == "zh":
        return {
            "lastModified": "最后修改",
            "unknown": "未知",
            "notRecorded": "未记录",
            "valid": "Valid",
            "testable": "Testable",
            "decided": "Decided",
            "status": "status",
            "anchorLine": "anchor line",
            "rootLine": "root line",
            "replyPlaceholder": "回复内容",
            "reply": "回复",
            "markResolved": "标记 resolved",
            "loadFailed": "加载 {{title}} 失败",
            "saveFailed": "保存失败",
            "discussionFailed": "讨论操作失败",
            "startDiscussionFailed": "发起讨论失败",
            "remoteUpdated": "远端内容已由 {{actor}} 更新，请重新加载或手工合并本地修改",
            "focusContent": "看正文",
            "focusDiscussion": "看讨论",
            "focusBalanced": "均衡",
            "saved": "已自动保存",
            "conflictDetected": "检测到写入冲突",
            "viewRemote": "查看远端版本",
            "forceOverwrite": "强制覆盖",
            "remoteLoaded": "已加载远端版本（只读），请合并或放弃本地编辑",
            "statusToggled": "状态已更新",
            "statusToggleFailed": "状态更新失败",
            "xrefBack": "返回",
            "xrefNotFound": "未找到对应的 spec",
        }
    return {
        "lastModified": "Last modified",
        "unknown": "Unknown",
        "notRecorded": "Not recorded",
        "valid": "Valid",
        "testable": "Testable",
        "decided": "Decided",
        "status": "status",
        "anchorLine": "anchor line",
        "rootLine": "root line",
        "replyPlaceholder": "Reply content",
        "reply": "Reply",
        "markResolved": "Mark resolved",
        "loadFailed": "Failed to load {{title}}",
        "saveFailed": "Save failed",
        "discussionFailed": "Discussion action failed",
        "startDiscussionFailed": "Failed to start discussion",
        "remoteUpdated": "Remote content was updated by {{actor}}. Reload or merge your local edits manually.",
        "focusContent": "Content",
        "focusDiscussion": "Discussion",
        "focusBalanced": "Balanced",
        "saved": "Auto-saved",
        "conflictDetected": "Write conflict detected",
        "viewRemote": "View remote",
        "forceOverwrite": "Force overwrite",
        "remoteLoaded": "Remote loaded (read-only). Merge or discard your edits.",
        "statusToggled": "Status updated",
        "statusToggleFailed": "Status update failed",
        "xrefBack": "Back",
        "xrefNotFound": "Spec not found",
    }


def _login_shell(lang: str, next_path: str, has_users: bool) -> str:
    next_json = json.dumps(next_path, ensure_ascii=False)
    hero_image = "/assets/min-square_97-snk-X32c8tE-unsplash.jpg"
    return f"""<!DOCTYPE html>
<html lang="{_escape("zh-CN" if lang == "zh" else "en")}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>louke login</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-alt: #f1f3f5;
      --text: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
      --border-strong: #cbd5e1;
      --danger: #dc2626;
      --danger-bg: #fef2f2;
      --danger-border: #fecaca;
      --accent: #0f172a;
      --accent-hover: #1e293b;
      --ring: rgba(15, 23, 42, 0.12);
      --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
      --shadow-md: 0 4px 16px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04);
      --shadow-lg: 0 24px 48px rgba(15, 23, 42, 0.08), 0 2px 8px rgba(15, 23, 42, 0.04);
      --radius: 14px;
      --radius-lg: 24px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      -webkit-font-smoothing: antialiased;
    }}
    .auth-shell {{
      width: min(960px, calc(100vw - 32px));
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
      background: var(--surface);
      box-shadow: var(--shadow-lg);
    }}
    .auth-hero {{ padding: 40px; }}
    .auth-panel {{
      padding: 44px 40px;
      display: grid;
      gap: 24px;
      align-content: start;
    }}
    .auth-hero {{
      position: relative;
      min-height: 620px;
      display: grid;
      place-items: center;
      border-right: 1px solid var(--border);
      color: #ffffff;
      background:
        linear-gradient(180deg, rgba(15, 23, 42, 0.18) 0%, rgba(15, 23, 42, 0.42) 100%),
        url('{hero_image}') center center / cover no-repeat;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    .hero-eyebrow {{ color: rgba(255, 255, 255, 0.82); }}
    h1, h2 {{ margin: 0; letter-spacing: -0.02em; font-weight: 700; }}
    h2 {{ font-size: 22px; }}
    p {{ margin: 0; line-height: 1.6; color: var(--muted); }}
    .hero-copy {{
      max-width: 560px;
      display: grid;
      gap: 14px;
      padding: 32px;
      text-align: center;
    }}
    .hero-copy h1 {{
      margin: 0;
      color: #ffffff;
      font-size: clamp(22px, 2.7vw, 34px);
      line-height: 1.15;
    }}
    .photo-credit {{
      position: absolute;
      right: 24px;
      bottom: 24px;
      max-width: 440px;
      font-size: 12px;
      line-height: 1.6;
      color: rgba(255, 255, 255, 0.64);
    }}
    .photo-credit a {{
      color: rgba(255, 255, 255, 0.72);
      text-decoration: underline;
      text-underline-offset: 2px;
    }}
    .tabs {{
      display: inline-grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface-alt);
    }}
    .tab-button {{
      padding: 11px 16px;
      border-radius: 10px;
      border: 0;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font: inherit;
      font-weight: 500;
      transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
    }}
    .tab-button:hover {{ color: var(--text); }}
    .tab-button.active {{
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow-sm);
    }}
    .tab-panel[hidden] {{ display: none; }}
    .tab-panel .eyebrow {{ margin-bottom: -6px; }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text);
    }}
    input {{
      width: 100%;
      padding: 13px 14px;
      border-radius: 11px;
      border: 1px solid var(--border-strong);
      background: var(--surface);
      color: var(--text);
      font: inherit;
      font-size: 15px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    input::placeholder {{ color: #94a3b8; }}
    input:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--ring);
    }}
    button {{
      padding: 0 18px;
      height: 46px;
      border-radius: 11px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: white;
      cursor: pointer;
      font: inherit;
      font-size: 15px;
      font-weight: 600;
      transition: transform 0.05s ease, background 0.15s ease, box-shadow 0.15s ease;
    }}
    button:hover {{ background: var(--accent-hover); }}
    button:active {{ transform: translateY(1px); }}
    button:focus-visible {{ outline: none; box-shadow: 0 0 0 3px var(--ring); }}
    .secondary {{ background: var(--surface); color: var(--text); border-color: var(--border-strong); }}
    .secondary:hover {{ background: var(--surface-alt); }}
    .stack {{ display: grid; gap: 16px; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .banner {{
      padding: 11px 14px;
      border: 1px solid var(--danger-border);
      border-radius: 11px;
      background: var(--danger-bg);
      color: var(--danger);
      font-size: 14px;
    }}
    @media (max-width: 860px) {{
      .auth-shell {{ grid-template-columns: 1fr; }}
      .auth-hero {{ border-right: 0; border-bottom: 1px solid var(--border); }}
      .row {{ grid-template-columns: 1fr; }}
      .photo-credit {{
        right: 20px;
        bottom: 20px;
        max-width: none;
      }}
      .auth-panel {{ padding: 32px 24px; }}
    }}
  </style>
</head>
<body>
  <main class="auth-shell">
    <section class="auth-hero">
      <div class="hero-copy">
        <h1>Beyond Vibes, Into Craft</h1>
        <h2>超越氛围编程 自是精工镂刻</h2>
      </div>
      <div class="photo-credit">
        Photo by <a href="https://unsplash.com/@min_square97?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText" target="_blank" rel="noreferrer">Min Square_97</a> on <a href="https://unsplash.com/photos/a-close-up-of-a-clock-with-gold-gears-snk-X32c8tE?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText" target="_blank" rel="noreferrer">Unsplash</a>
      </div>
    </section>
    <section class="auth-panel">
      <div class="tabs" role="tablist" aria-label="认证入口">
        <button id="tab-login" class="tab-button active" type="button" role="tab" aria-selected="true">{_escape(_t(lang, "login.sign_in"))}</button>
        <button id="tab-register" class="tab-button" type="button" role="tab" aria-selected="false">{_escape(_t(lang, "login.register"))}</button>
      </div>
      <div id="panel-login" class="stack tab-panel" role="tabpanel">
        <div class="eyebrow">{_escape(_t(lang, "login.sign_in"))}</div>
        <h2>{_escape(_t(lang, "login.sign_in"))}</h2>
        <label>{_escape(_t(lang, "login.username"))}<input id="login-username" name="name" autocomplete="username" /></label>
        <label>{_escape(_t(lang, "login.password"))}<input id="login-password" name="password" type="password" autocomplete="current-password" /></label>
        <button id="login-submit" type="submit">{_escape(_t(lang, "login.sign_in_button"))}</button>
      </div>
      <div id="panel-register" class="stack tab-panel" role="tabpanel" hidden>
        <div class="eyebrow">{_escape(_t(lang, "login.register"))}</div>
        <h2>{_escape(_t(lang, "login.register"))}</h2>
        <div class="row">
          <label>{_escape(_t(lang, "login.username"))}<input id="register-username" autocomplete="username" /></label>
          <label>{_escape(_t(lang, "login.password"))}<input id="register-password" type="password" autocomplete="new-password" /></label>
        </div>
        <button id="register-submit" class="secondary">{_escape(_t(lang, "login.register_button"))}</button>
      </div>
      <div id="banner" class="banner" hidden></div>
    </section>
  </main>
  <script>
    const nextPath = {next_json};
    const requestFailed = {json.dumps(_t(lang, "login.request_failed"), ensure_ascii=False)};
    const banner = document.getElementById('banner');
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');
    const panelLogin = document.getElementById('panel-login');
    const panelRegister = document.getElementById('panel-register');
    function showBanner(message) {{
      banner.hidden = false;
      banner.textContent = message;
    }}
    function switchTab(target) {{
      const loginActive = target === 'login';
      tabLogin.classList.toggle('active', loginActive);
      tabRegister.classList.toggle('active', !loginActive);
      tabLogin.setAttribute('aria-selected', loginActive ? 'true' : 'false');
      tabRegister.setAttribute('aria-selected', loginActive ? 'false' : 'true');
      panelLogin.hidden = !loginActive;
      panelRegister.hidden = loginActive;
      banner.hidden = true;
    }}
    async function submit(path, payload) {{
      banner.hidden = true;
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const data = await response.json();
      if (!response.ok) {{
        showBanner(data.error || requestFailed);
        return;
      }}
      location.href = nextPath || '/';
    }}
    tabLogin.addEventListener('click', () => switchTab('login'));
    tabRegister.addEventListener('click', () => switchTab('register'));
    document.getElementById('login-submit').addEventListener('click', async () => {{
      await submit('/api/auth/login', {{
        username: document.getElementById('login-username').value.trim(),
        password: document.getElementById('login-password').value
      }});
    }});
    document.getElementById('register-submit').addEventListener('click', async () => {{
      await submit('/api/auth/register', {{
        username: document.getElementById('register-username').value.trim(),
        password: document.getElementById('register-password').value
      }});
    }});
  </script>
</body>
</html>"""


def _assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"
