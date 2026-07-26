"""Workbench shell and the read-only Batch B navigation panels."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
import sys

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from ..bindings import AGENT_TO_ROLE
from ..render import render_markdown_view


TOOLBAR_ITEMS = (
    ("projects", "Projects", "◫"),
    ("chat", "Chat", "💬"),
    ("dev-docs", "Dev Docs", "▤"),
    ("end-user-docs", "End User Docs", "▥"),
    ("wiki", "Wiki", "◈"),
    ("runs", "Runs", "▶"),
    ("accounts", "Accounts", "●"),
    ("gears", "Settings", "⚙"),
)


async def workbench(request: Request) -> HTMLResponse:
    """Render the workbench with filesystem-backed read-only navigation.

    The ``?activity=`` query parameter selects the active panel:

    - ``projects`` (default after Setup) → Projects activity (IF-PROJECT-01).
    - ``chat`` / ``dev-docs`` / ``runs`` / … → legacy v0.13 panels.

    When Setup is complete and no ``?activity`` is given, redirect to
    ``?activity=projects`` (IF-PROJECT-01 canonical landing).
    """
    from starlette.responses import RedirectResponse as _Redirect

    activity = request.query_params.get("activity")
    if activity is None:
        # Default landing: Projects when Setup is complete, else legacy Chat.
        from ..setup_state import try_read_manifest

        workspace_root = Path(request.app.state.workspace_root)
        manifest = try_read_manifest(workspace_root)
        if manifest is not None and manifest.is_complete:
            return _Redirect(url="/workbench?activity=projects", status_code=303)
        activity = "chat"
    if activity == "projects":
        return await _render_projects_activity(request)
    if (
        activity == "dev-docs"
        and request.query_params.get("document") == "story"
        and request.query_params.get("project")
    ):
        return _render_project_story_document(request)

    store = request.app.state.store
    specs = _spec_tree(store.specs_dir, store.root)
    wiki_pages = [item["page"] for item in store.list_wiki_pages()]
    agents = _agents()
    return HTMLResponse(
        _page(
            _toolbar(),
            _devdocs(specs),
            _devdocs_view(
                specs,
                store.specs_dir,
                request.query_params.get("spec"),
                request.query_params.get("doc"),
            ),
            _end_user_docs(store.root),
            _wiki(wiki_pages),
            _runs_sidebar(store.root),
            _chat_sidebar(agents),
            _chat_content(agents),
            _runs_content(store.root),
            _settings(store.root),
        )
    )


def _settings(root: Path) -> str:
    """Render v0.13 placeholders alongside the v0.13.1 runtime identity."""
    from louke import __version__
    from louke.__main__ import _runtime_mode

    mode = _runtime_mode()
    identity = f"{__version__} ({mode})"
    executable = str(Path(sys.executable).resolve())
    local_path = str(root / ".venv")
    return (
        '<section data-settings-pane="menu"><button type="button" '
        'data-testid="settings-menu-version" data-setting="version" aria-disabled="true">'
        "版本更新 <span>待 v0.15</span></button>"
        '<button type="button" data-testid="settings-menu-server" '
        'data-setting="server" aria-disabled="true">服务器配置 <span>待 v0.15</span></button>'
        '<button type="button" data-testid="settings-menu-model" '
        'data-setting="model" aria-disabled="true">S/A/B 模型绑定 <span>待 v0.15</span></button></section>'
        '<section data-settings-pane="detail" data-testid="settings-detail">'
        '<h2 data-testid="settings-placeholder-title">版本更新</h2>'
        '<p data-testid="settings-placeholder-detail">待 v0.15；当前仅提供运行时身份信息。</p>'
        "<h3>当前运行时</h3>"
        f'<p data-testid="settings-runtime-identity"><strong>{escape(identity)}</strong></p>'
        f'<dl><dt>当前解释器</dt><dd data-testid="settings-runtime-executable">{escape(executable)}</dd>'
        f'<dt>项目目录</dt><dd data-testid="settings-project-root">{escape(str(root))}</dd>'
        f'<dt>项目本地运行时</dt><dd data-testid="settings-local-runtime">{escape(local_path)}</dd></dl>'
        "</section>"
    )


def _toolbar() -> str:
    buttons = []
    for key, label, icon in TOOLBAR_ITEMS:
        menu_attr = ' aria-haspopup="menu"' if key == "accounts" else ""
        buttons.append(
            f'<button type="button" data-testid="toolbar-{key}" '
            f'data-activity="{key}" aria-label="{label}" title="{label}"{menu_attr}>'
            f'<span aria-hidden="true">{icon}</span></button>'
        )
    return '<div class="toolbar-brand" aria-label="Louke">L</div>' + "".join(buttons)


def _spec_tree(specs_dir: Path, root: Path) -> list[tuple[str, list[str]]]:
    if not specs_dir.exists():
        return []
    result: list[tuple[str, list[str]]] = []
    for directory in sorted(path for path in specs_dir.iterdir() if path.is_dir()):
        files = sorted(
            path.relative_to(root).as_posix()
            for path in directory.glob("*.md")
            if path.is_file()
        )
        result.append((directory.name, files))
    return result


def _agents() -> list[str]:
    """Discover active, role-bound agents with Maestro first."""
    agents_dir = Path(__file__).parents[2] / "agents"
    names = sorted(
        path.stem
        for path in agents_dir.glob("*.md")
        if path.is_file() and path.stem in AGENT_TO_ROLE and path.stem != "Maestro"
    )
    return ["Maestro", *names] if "Maestro" in AGENT_TO_ROLE else names


def _chat_sidebar(agents: list[str]) -> str:
    """Render the Agent picker."""
    items = "".join(
        f'<button type="button" class="chat-agent" data-testid="chat-agent-{escape(_agent_id(name))}" '
        f'data-chat-agent="{escape(_agent_id(name))}" aria-selected="{"true" if index == 0 else "false"}">'
        f'<span aria-hidden="true">🤖</span><span>{escape(name)}</span></button>'
        for index, name in enumerate(agents)
    )
    return (
        '<section data-sidebar-kind="chat"><strong>Chat</strong>'
        '<div data-testid="chat-agent-list" role="listbox" aria-label="Chat agents">'
        f"{items}</div></section>"
    )


def _chat_content(agents: list[str]) -> str:
    """Render isolated transcript containers and the plain message form."""
    transcripts = "".join(
        f'<section data-testid="chat-transcript-{escape(_agent_id(name))}" '
        f'data-agent="{escape(_agent_id(name))}" hidden></section>'
        for name in agents
    )
    return (
        '<div data-tab-content="chat" data-chat-panel>'
        '<section data-testid="chat-transcript" aria-live="polite">'
        f"{transcripts}</section>"
        '<form data-testid="chat-form"><input data-testid="chat-input" type="text" '
        'placeholder="Type a message to Maestro..." autocomplete="off">'
        '<button data-testid="chat-submit" type="submit">Send</button></form>'
        '<div data-testid="chat-toast" role="status" hidden></div></div>'
    )


def _agent_id(name: str) -> str:
    """Return the normalized OpenCode Agent id for a generated Agent name."""
    return name.strip().lower()


def _devdocs(specs: list[tuple[str, list[str]]]) -> str:
    groups = []
    for spec_id, files in specs:
        children = "".join(
            f'<button type="button" data-testid="devdocs-file-{escape(Path(file).stem)}" '
            f'data-doc-path="{escape(file)}">{escape(Path(file).stem)}</button>'
            for file in files
        )
        groups.append(
            f'<details data-devdocs-spec="{escape(spec_id)}" data-expanded="false">'
            f'<summary data-testid="devdocs-spec-{escape(spec_id)}">{escape(spec_id)}</summary>'
            f"<div>{children}</div></details>"
        )
    return (
        '<section data-sidebar-kind="dev-docs" hidden><strong>Dev Docs</strong>'
        '<div data-testid="devdocs-tree">' + "".join(groups) + "</div></section>"
    )


_REFERENCE = re.compile(r"\b(?P<ref>(?:FR|NFR|US)-\d{3,4})\b")


def _devdocs_view(
    specs: list[tuple[str, list[str]]],
    specs_dir: Path,
    requested_spec: str | None,
    requested_doc: str | None,
) -> str:
    """Render the multi-document, live-editing Dev Docs workspace."""
    if not specs or not specs[0][1]:
        return '<div data-tab-content="dev-docs" hidden></div>'
    spec_id, files = next(
        (
            (candidate, documents)
            for candidate, documents in specs
            if candidate == requested_spec
        ),
        specs[0],
    )
    requested_name = f"{requested_doc}.md" if requested_doc else ""
    selected = next(
        (file for file in files if Path(file).name == requested_name),
        next((file for file in files if Path(file).name == "spec.md"), files[0]),
    )
    path = specs_dir / spec_id / Path(selected).name
    body_md = path.read_text(encoding="utf-8")
    doc_name = Path(selected).stem
    rendered = render_markdown_view(body_md, kind="doc", doc_name=doc_name)
    rendered_html = rendered.rendered_html.replace(
        '<section class="discussion-block">',
        '<section class="discussion-block" data-discussion="1">',
    )
    links = _devdocs_cross_references(rendered_html, body_md, spec_id, specs_dir)
    reference_links = "".join(
        dict.fromkeys(
            re.findall(
                r'<a data-testid="devdocs-cross-ref-[^"]+" href="[^"]+">[^<]+</a>',
                links,
            )
        )
    )
    cards = _devdocs_verdict_cards(rendered.cards)
    documents = [Path(file).stem for file in files]
    document_json = json.dumps(documents, ensure_ascii=False, separators=(",", ":"))
    visibility = "" if requested_doc else " hidden"
    return (
        f'<div data-tab-content="dev-docs"{visibility}>'
        f'<section data-testid="devdocs-view" data-spec-id="{escape(spec_id)}" '
        f'data-initial-doc="{escape(doc_name)}" '
        f'data-doc-list="{escape(document_json, quote=True)}" '
        f'data-doc-name="{escape(doc_name)}" data-doc-path="{escape(path.relative_to(specs_dir.parent.parent.parent).as_posix())}">'
        '<header class="devdocs-toolbar">'
        "<strong>Dev Docs</strong><span>多文档实时编辑工作区</span>"
        '<div class="devdocs-tools">'
        '<button type="button" data-workspace-action="split" title="新增一个文档分屏">新增分屏</button>'
        "</div></header>"
        '<div data-testid="devdocs-pane-container" class="devdocs-pane-container"></div>'
        f'<nav data-testid="devdocs-cross-references" aria-label="文档交叉引用">{reference_links}</nav>'
        f'<section data-testid="devdocs-verdict">{cards}</section>'
        f'<div data-testid="devdocs-rendered" hidden>{links}</div>'
        f'<pre data-testid="devdocs-source" hidden>{escape(body_md)}</pre>'
        '<div data-testid="devdocs-toast" role="status" hidden></div>'
        "</section></div>"
    )


def _devdocs_script() -> str:
    """Return the client-side multi-pane editor used by the v0.13 Workbench."""
    return """
const docPanes = [];
let docPaneSequence = 0;

function docWorkspaceView() {
  return document.querySelector('[data-testid="devdocs-view"]');
}
function docWorkspaceVersionToken() {
  const pane = docPanes.find(item => item.docName === docWorkspaceView()?.dataset.initialDoc);
  return pane?.versionToken || docPanes[0]?.versionToken || '';
}
function docWorkspaceToast(message) {
  const toast = document.querySelector('[data-testid="devdocs-toast"]');
  if (!toast) return;
  toast.textContent = message || '';
  toast.hidden = !message;
}
function isWritableDoc(docName) {
  return ['story', 'spec', 'acceptance'].includes(docName);
}
function docValue(pane) {
  return pane?.vditor?.getValue ? pane.vditor.getValue() : pane?.fallback?.value || '';
}
function setDocStatus(pane, text) {
  const status = pane?.el?.querySelector('[data-pane-status]');
  if (status) status.textContent = text;
}
function setDocPaneDirty(pane) {
  if (!pane) return;
  pane.dirty = docValue(pane) !== pane.loadedBody;
  pane.saveButton.disabled = !isWritableDoc(pane.docName) || !pane.dirty;
  pane.saveButton.textContent = pane.dirty ? '保存 *' : '保存';
  setDocStatus(pane, pane.dirty ? '有未保存修改' : '已加载');
}
function paneOptions(select, docs, selected) {
  select.replaceChildren();
  docs.forEach(doc => {
    const option = document.createElement('option');
    option.value = doc;
    option.textContent = doc + '.md';
    option.selected = doc === selected;
    select.append(option);
  });
}
function refreshDocPaneLayout() {
  const view = docWorkspaceView();
  const host = view?.querySelector('[data-testid="devdocs-pane-container"]');
  if (host) host.dataset.paneCount = String(docPanes.length);
}
function markPaneDiscussions(pane) {
  const root = pane?.el?.querySelector('.vditor-ir');
  if (!root) return;
  root.querySelectorAll('[data-discussion]').forEach(item => {
    delete item.dataset.discussion;
    delete item.dataset.resolved;
  });
  root.querySelectorAll('blockquote, p, li').forEach(item => {
    const text = item.textContent || '';
    if (/\\[T-\\d{3,4}\\]/.test(text) || item.tagName === 'BLOCKQUOTE') {
      item.dataset.discussion = '1';
      if (/✓|\\[(?:resolved|已解决|已决定|decided|wontfix)\\]/i.test(text)) item.dataset.resolved = '1';
    }
  });
}
function paneDiscussionItems(pane) {
  markPaneDiscussions(pane);
  return [...(pane?.el?.querySelectorAll('[data-discussion="1"]') || [])];
}
function nextDocPaneDiscussion(pane) {
  const items = paneDiscussionItems(pane);
  if (!items.length) return docWorkspaceToast('没有找到 inline-discussion');
  const cursor = Number(pane.el.dataset.discussionCursor || -1);
  const next = (cursor + 1) % items.length;
  pane.el.dataset.discussionCursor = String(next);
  items[next].scrollIntoView({behavior: 'smooth', block: 'center'});
}
function nextDocPaneUnresolved(pane) {
  const items = paneDiscussionItems(pane).filter(item => !item.dataset.resolved);
  if (!items.length) return docWorkspaceToast('当前文档没有 unresolved discussion');
  const cursor = Number(pane.el.dataset.unresolvedCursor || -1);
  const next = (cursor + 1) % items.length;
  pane.el.dataset.unresolvedCursor = String(next);
  items[next].scrollIntoView({behavior: 'smooth', block: 'center'});
}
function toggleDocPaneDiscussions(pane, button) {
  pane.collapsed = !pane.collapsed;
  pane.el.classList.toggle('discussions-collapsed', pane.collapsed);
  button.dataset.active = String(pane.collapsed);
  button.title = pane.collapsed ? '显示 inline-discussion' : '隐藏 inline-discussion';
}
function fallbackEditor(pane, body) {
  const mount = pane.el.querySelector('.vditor-mount');
  mount.replaceChildren();
  const textarea = document.createElement('textarea');
  textarea.spellcheck = false;
  textarea.value = body;
  mount.append(textarea);
  pane.fallback = textarea;
  pane.vditor = null;
  textarea.addEventListener('input', () => {
    setDocPaneDirty(pane);
  });
}
function initDocPaneEditor(pane, body) {
  const mount = pane.el.querySelector('.vditor-mount');
  pane.fallback = null;
  if (typeof Vditor === 'undefined') {
    fallbackEditor(pane, body);
    return;
  }
  try {
    pane.vditor = new Vditor(mount.id, {
      mode: 'ir', value: body, height: '100%', toolbar: false,
      cache: {enable: false},
      after: () => { pane.ready = true; markPaneDiscussions(pane); },
      input: () => {
        if (pane.loading) return;
        setDocPaneDirty(pane);
        clearTimeout(pane.discussionTimer);
        pane.discussionTimer = setTimeout(() => markPaneDiscussions(pane), 250);
      }
    });
    pane.ready = true;
  } catch (error) {
    fallbackEditor(pane, body);
  }
}
async function loadDocPane(pane, docName) {
  if (!pane) return;
  const view = docWorkspaceView();
  pane.loading = true;
  pane.docName = docName;
  pane.select.value = docName;
  pane.saveButton.disabled = !isWritableDoc(docName);
  pane.saveButton.title = isWritableDoc(docName) ? '保存（仅显式保存）' : '该文档只读';
  try {
    const response = await fetch('/api/docs/' + encodeURIComponent(view.dataset.specId) + '/' + encodeURIComponent(docName));
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || ('文档加载失败 (' + response.status + ')'));
    pane.versionToken = data.version_token || '';
    pane.loadedBody = data.body_md || '';
    if (pane.vditor && pane.ready) {
      pane.vditor.setValue(data.body_md || '');
    } else {
      initDocPaneEditor(pane, data.body_md || '');
    }
    pane.dirty = false;
    pane.saveButton.disabled = true;
    pane.saveButton.textContent = '保存';
    setDocStatus(pane, '已加载');
    markPaneDiscussions(pane);
  } catch (error) {
    setDocStatus(pane, '加载失败');
    docWorkspaceToast(error.message || '文档加载失败');
  } finally {
    pane.loading = false;
  }
}
function createDocPane(docName) {
  const view = docWorkspaceView();
  const host = view?.querySelector('[data-testid="devdocs-pane-container"]');
  if (!view || !host) return;
  if (docPanes.length >= 4) return docWorkspaceToast('最多同时打开 4 份文档');
  const docs = JSON.parse(view.dataset.docList || '[]');
  const selected = docName || docs[0];
  const id = 'doc-pane-' + docPaneSequence++;
  const paneEl = document.createElement('article');
  paneEl.className = 'doc-pane';
  paneEl.dataset.paneId = id;
  paneEl.innerHTML = '<header class="doc-pane-bar"><select data-pane-doc aria-label="选择文档"></select>' +
    '<span class="doc-pane-status" data-pane-status>加载中</span><div class="doc-pane-tools">' +
    '<button type="button" data-pane-action="next-discussion" title="下个 discussion">↯</button>' +
    '<button type="button" data-pane-action="collapse" title="隐藏 inline-discussion">◌</button>' +
    '<button type="button" data-pane-action="next-unresolved" title="下个 unresolved">!</button>' +
    '<button type="button" data-pane-action="split" title="新增文档分屏">＋</button>' +
    '<button type="button" data-pane-action="save" title="保存">保存</button>' +
    '<button type="button" data-pane-action="reload" title="重载">↻</button>' +
    '<button type="button" data-pane-action="close" title="关闭分屏">×</button></div></header>' +
    '<div data-pane-conflict hidden><strong>文件已被外部修改</strong>' +
    '<button type="button" data-pane-conflict-action="reload">重新加载并放弃我的编辑</button>' +
    '<button type="button" data-pane-conflict-action="force">仍要覆盖</button></div>' +
    '<div class="vditor-mount" id="' + id + '-editor"></div>';
  host.append(paneEl);
  const pane = {
    id, el: paneEl, select: paneEl.querySelector('[data-pane-doc]'),
    saveButton: paneEl.querySelector('[data-pane-action="save"]'),
    docName: selected, versionToken: '', vditor: null, fallback: null,
    ready: false, dirty: false, loading: false, collapsed: false, loadedBody: ''
  };
  paneOptions(pane.select, docs, selected);
  pane.select.addEventListener('change', () => loadDocPane(pane, pane.select.value));
  paneEl.querySelectorAll('[data-pane-action]').forEach(button => button.addEventListener('click', () => {
    const action = button.dataset.paneAction;
    if (action === 'next-discussion') nextDocPaneDiscussion(pane);
    else if (action === 'collapse') toggleDocPaneDiscussions(pane, button);
    else if (action === 'next-unresolved') nextDocPaneUnresolved(pane);
    else if (action === 'split') createDocPane();
    else if (action === 'save') saveDocPane(pane);
    else if (action === 'reload') loadDocPane(pane, pane.docName);
    else if (action === 'close') closeDocPane(pane);
  }));
  paneEl.querySelector('[data-pane-conflict-action="reload"]').addEventListener('click', () => {
    paneEl.querySelector('[data-pane-conflict]').hidden = true;
    loadDocPane(pane, pane.docName);
  });
  paneEl.querySelector('[data-pane-conflict-action="force"]').addEventListener('click', () => {
    if (confirm('确认覆盖外部修改？')) saveDocPane(pane, true);
  });
  docPanes.push(pane);
  refreshDocPaneLayout();
  loadDocPane(pane, selected);
}
async function saveDocPane(pane, force = false) {
  if (!pane || !isWritableDoc(pane.docName)) return docWorkspaceToast('该文档为只读');
  const view = docWorkspaceView();
  pane.saveButton.disabled = true;
  try {
    const response = await fetch('/api/docs/' + encodeURIComponent(view.dataset.specId) + '/' + encodeURIComponent(pane.docName), {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({body_md: docValue(pane), version_token: pane.versionToken, force: !!force})
    });
    const data = await response.json();
    if (response.status === 409 && !force) {
      pane.el.querySelector('[data-pane-conflict]').hidden = false;
      setDocStatus(pane, '保存冲突');
      return;
    }
    if (!response.ok) throw new Error(data.message || data.error || '保存失败');
    pane.versionToken = data.version_token || pane.versionToken;
    pane.loadedBody = data.body_md || docValue(pane);
    pane.dirty = false;
    pane.saveButton.textContent = '保存';
    setDocStatus(pane, '已保存');
  } catch (error) {
    setDocStatus(pane, '保存失败');
    docWorkspaceToast(error.message || '保存失败');
  } finally {
    pane.saveButton.disabled = !isWritableDoc(pane.docName) || !pane.dirty;
  }
}
function closeDocPane(pane) {
  if (docPanes.length <= 1) return docWorkspaceToast('至少保留一个文档分屏');
  if (pane.vditor?.destroy) pane.vditor.destroy();
  clearTimeout(pane.discussionTimer);
  pane.el.remove();
  docPanes.splice(docPanes.indexOf(pane), 1);
  refreshDocPaneLayout();
}
function initDocWorkspace() {
  const view = docWorkspaceView();
  if (!view || view.dataset.workspaceReady === 'true') return;
  view.dataset.workspaceReady = 'true';
  createDocPane(view.dataset.initialDoc);
  view.querySelector('[data-workspace-action="split"]')?.addEventListener('click', () => createDocPane());
}
"""


def _devdocs_verdict_cards(cards: list[dict]) -> str:
    """Render requirement status/verdict cards from the existing renderer."""
    if not cards:
        return ""
    rendered = []
    for card in cards:
        statuses = ("valid", "testable", "decided")
        unresolved = not all(bool(card.get(field)) for field in statuses)
        checks = "".join(
            f'<button type="button" data-verdict-field="{field}" '
            f'data-fr-id="{escape(str(card.get("id", "")))}" '
            f'aria-pressed="{"true" if card.get(field) else "false"}">'
            f"{'✓' if card.get(field) else '○'} {field}</button>"
            for field in statuses
        )
        rendered.append(
            f'<article class="verdict-card" data-testid="devdocs-verdict-card" '
            f'data-fr-id="{escape(str(card.get("id", "")))}" '
            f'data-unresolved="{"true" if unresolved else "false"}">'
            f'<header><a href="#{escape(str(card.get("id", "")).lower())}">'
            f"{escape(str(card.get('id', '')))} · {escape(str(card.get('title', '')))}</a>"
            f'<span class="verdict-badge">{"UNRESOLVED" if unresolved else "PASS"}</span></header>'
            f'<p>{escape(str(card.get("summary", "")))}</p><div class="verdict-checks">{checks}</div>'
            "</article>"
        )
    return "".join(rendered)


def _devdocs_cross_references(
    rendered_html: str, body_md: str, spec_id: str, specs_dir: Path
) -> str:
    """Add stable links to rendered FR, NFR, and Story references."""
    anchors = {
        reference.lower()
        for reference in _REFERENCE.findall(body_md)
        if _has_document_anchor(body_md, reference)
    }

    def target(match: re.Match[str]) -> str:
        ref = match.group("ref")
        if ref.lower() in anchors:
            href = f"#{ref.lower()}"
        elif (specs_dir / spec_id / "acceptance.md").is_file():
            href = f"?spec={spec_id}&doc=acceptance#{ref.lower()}"
        else:
            href = f"#{ref.lower()}"
        return (
            f'<a data-testid="devdocs-cross-ref-{ref}" href="{escape(href, quote=True)}">'
            f"{ref}</a>"
        )

    rendered_html = re.sub(
        r'<a class="xref-link" href="#[^"]+" data-ref="(?P<ref>(?:FR|NFR)-\d{3,4})">[^<]+</a>',
        target,
        rendered_html,
    )
    return re.sub(r"\b(?P<ref>US-\d{3,4})\b", target, rendered_html)


def _has_document_anchor(body_md: str, reference: str) -> bool:
    """Return whether ``reference`` names an explicit or Markdown heading anchor."""
    anchor = re.escape(reference.lower())
    return bool(
        re.search(rf'id=["\']{anchor}["\']', body_md, re.IGNORECASE)
        or re.search(rf"^#+\s+{anchor}\b", body_md, re.IGNORECASE | re.MULTILINE)
    )


def _wiki(pages: list[str]) -> str:
    names = ["README", "design docs", *pages]
    unique = list(dict.fromkeys(names))
    links = "".join(
        f'<button type="button" data-testid="wiki-page-{escape(name)}" '
        f'data-wiki-page="{escape(name)}">{escape(name)}</button>'
        for name in unique
    )
    unknown = (
        '<button type="button" data-testid="wiki-unknown-page" '
        'data-wiki-page="unknown-page" aria-disabled="true" data-unknown="true">unknown-page</button>'
    )
    return (
        '<section data-sidebar-kind="wiki" hidden><strong>Wiki</strong>'
        '<div data-testid="wiki-tree">' + links + unknown + "</div></section>"
    )


def _end_user_docs(root: Path) -> str:
    """Render the End User Docs navigation shell."""
    docs_root = root / ".louke" / "end-user-docs"
    buttons = []
    if docs_root.is_dir():
        for path in sorted(docs_root.rglob("*.md")):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(root).as_posix()
                buttons.append(
                    f'<button type="button" data-testid="enduserdocs-file-{escape(path.stem)}" '
                    f'data-enduserdocs-path="{escape(relative)}">{escape(path.name)}</button>'
                )
    return (
        '<section data-sidebar-kind="end-user-docs" hidden><strong>End User Docs</strong>'
        '<div data-testid="enduserdocs-tree">' + "".join(buttons) + "</div></section>"
    )


def _runs_sidebar(root: Path) -> str:
    """Render Runtime-backed current/history containers for Runs."""
    del root
    return (
        '<section data-sidebar-kind="runs" data-testid="runs-sidebar" hidden>'
        '<strong>Current project</strong><div data-runs-group="current">'
        '<span data-testid="runs-empty-state">No workflow runs</span></div>'
        '<strong>History</strong><div data-runs-group="history">'
        '<span data-testid="runs-history-empty-state">No workflow runs</span></div>'
        + '<a href="/projects/new">Create new project</a></section>'
    )


def _runs_content(root: Path) -> str:
    """Render the dynamic Runtime graph and read-only artifact drawer."""
    del root
    return (
        '<div data-tab-content="runs" hidden>'
        '<section data-testid="runs-graph">Select a run to view its workflow graph</section>'
        '<aside data-testid="stage-artifact-detail" hidden></aside></div>'
    )


def _page(
    toolbar: str,
    devdocs: str,
    devdocs_view: str,
    end_user_docs: str,
    wiki: str,
    runs_sidebar: str,
    chat_sidebar: str,
    chat_content: str,
    runs_content: str,
    settings: str,
) -> str:
    styles = """
:root {
  color-scheme: light;
  --ink: #1d1d1f;
  --muted: #6b6b6b;
  --faint: #8b8b8b;
  --line: #eaeaea;
  --line-strong: #d6d6d6;
  --panel: #fafafa;
  --hover: #f2f2f2;
  --active: #ededed;
  --black: #050505;
}

* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  overflow: hidden;
  color: var(--ink);
  background: #fff;
  font: 13px/1.45 Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
button, input, textarea { font: inherit; }
button { color: inherit; }
[hidden] { display: none !important; }

#workbench {
  display: grid;
  grid-template-columns: 56px minmax(240px, 280px) minmax(0, 1fr);
  width: 100vw;
  height: 100dvh;
  min-height: 520px;
  overflow: hidden;
  background: #fff;
}

[data-louke-region] { min-width: 0; min-height: 0; }
[data-louke-region="toolbar"] {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 10px;
  color: #fff;
  background: var(--black);
}
.toolbar-brand {
  display: grid;
  width: 36px;
  height: 36px;
  margin-bottom: 12px;
  place-items: center;
  border: 1px solid #3a3a3a;
  border-radius: 9px;
  color: #fff;
  background: #181818;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -.04em;
}
[data-louke-region="toolbar"] button {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  padding: 0;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 9px;
  color: #a7a7a7;
  background: transparent;
  cursor: pointer;
  font-size: 17px;
  transition: color .15s ease, background .15s ease, border-color .15s ease;
}
[data-louke-region="toolbar"] button:hover,
[data-louke-region="toolbar"] button:focus-visible {
  color: #fff;
  background: #242424;
  outline: none;
}
[data-louke-region="toolbar"] button[aria-current="page"] {
  color: #fff;
  border-color: #3c3c3c;
  background: #2b2b2b;
}
[data-louke-region="toolbar"] [data-activity="accounts"] { margin-top: auto; }

[data-louke-region="sidebar"] {
  overflow: auto;
  padding: 20px 14px;
  border-right: 1px solid var(--line);
  background: var(--panel);
  scrollbar-width: thin;
}
[data-louke-region="sidebar"] section { min-width: 0; }
[data-louke-region="sidebar"] section > strong {
  display: block;
  margin: 2px 8px 12px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
}
[data-testid="chat-agent-list"],
[data-testid="devdocs-tree"],
[data-testid="enduserdocs-tree"],
[data-testid="wiki-tree"],
[data-testid="runs-sidebar"] > div {
  display: grid;
  gap: 3px;
}
.chat-agent,
[data-testid="devdocs-tree"] summary,
[data-testid="devdocs-tree"] button,
[data-testid="enduserdocs-tree"] button,
[data-testid="wiki-tree"] button,
[data-testid="runs-sidebar"] button,
[data-testid="runs-sidebar"] a {
  display: flex;
  width: 100%;
  min-height: 34px;
  align-items: center;
  gap: 9px;
  padding: 7px 9px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 7px;
  color: #454545;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
  text-decoration: none;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.chat-agent:hover,
[data-testid="devdocs-tree"] summary:hover,
[data-testid="devdocs-tree"] button:hover,
[data-testid="enduserdocs-tree"] button:hover,
[data-testid="wiki-tree"] button:hover,
[data-testid="runs-sidebar"] button:hover,
[data-testid="runs-sidebar"] a:hover,
.chat-agent[aria-selected="true"] {
  border-color: var(--line);
  background: #fff;
}
.chat-agent[aria-selected="true"] { color: var(--ink); font-weight: 600; }
[data-testid="devdocs-tree"] details { display: grid; gap: 2px; }
[data-testid="devdocs-tree"] details > div { padding-left: 10px; }
[data-testid="devdocs-tree"] summary { list-style: none; }
[data-testid="devdocs-tree"] summary::-webkit-details-marker { display: none; }
[data-testid="devdocs-tree"] summary::before { content: "⌄"; color: var(--faint); }
[data-testid="devdocs-tree"] details:not([open]) summary::before { content: "›"; }
[data-testid="runs-sidebar"] > strong {
  display: block;
  margin: 14px 8px 5px;
  color: var(--faint);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

[data-louke-region="main"] {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}
[data-louke-region="main"] > [role="tablist"] {
  display: flex;
  min-height: 52px;
  flex: 0 0 52px;
  align-items: end;
  gap: 2px;
  padding: 0 24px;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
  scrollbar-width: none;
}
[data-louke-region="main"] > [role="tablist"]::-webkit-scrollbar { display: none; }
[role="tab"] {
  position: relative;
  min-width: 72px;
  height: 42px;
  padding: 0 13px;
  border: 0;
  border-radius: 7px 7px 0 0;
  color: var(--muted);
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
[role="tab"]::after {
  position: absolute;
  right: 12px;
  bottom: -1px;
  left: 12px;
  height: 1px;
  background: transparent;
  content: "";
}
[role="tab"]:hover { color: var(--ink); background: var(--hover); }
[role="tab"][aria-selected="true"] { color: var(--ink); font-weight: 600; }
[role="tab"][aria-selected="true"]::after { background: var(--black); }
[data-tab-content] {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: auto;
  padding: 28px clamp(22px, 4vw, 64px);
}

[data-tab-content="chat"] { padding-bottom: 22px; }
[data-testid="chat-transcript"] {
  display: flex;
  width: min(100%, 820px);
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 12px;
  margin: 0 auto;
  padding: 8px 0 28px;
  overflow: auto;
}
[data-testid^="chat-transcript-"] { display: block; }
[data-testid="chat-transcript"] p {
  max-width: 78%;
  margin: 0;
  padding: 10px 13px;
  border: 1px solid var(--line);
  border-radius: 10px;
  color: #3a3a3a;
  background: #fafafa;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
[data-testid="chat-transcript"] p[data-role="user"] {
  align-self: flex-end;
  border-color: var(--black);
  color: #fff;
  background: var(--black);
}
[data-testid="chat-form"] {
  display: flex;
  width: min(100%, 820px);
  min-height: 48px;
  flex: 0 0 auto;
  gap: 8px;
  margin: auto auto 0;
  padding: 5px;
  border: 1px solid var(--line-strong);
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(0,0,0,.04);
}
[data-testid="chat-input"] {
  min-width: 0;
  flex: 1;
  padding: 0 10px;
  border: 0;
  outline: 0;
  color: var(--ink);
  background: transparent;
}
[data-testid="chat-input"]::placeholder { color: #a0a0a0; }
[data-testid="chat-submit"],
[data-testid="enduserdocs-save"] {
  min-width: 72px;
  min-height: 36px;
  padding: 0 13px;
  border: 0;
  border-radius: 7px;
  color: #fff;
  background: var(--black);
  cursor: pointer;
  font-weight: 600;
}
[data-testid="chat-submit"]:disabled,
[data-testid="enduserdocs-save"]:disabled { opacity: .35; cursor: default; }
[data-testid="chat-toast"],
[data-testid="enduserdocs-toast"] {
  width: min(100%, 820px);
  margin: 8px auto 0;
  color: #b42318;
  font-size: 12px;
}

[data-testid="devdocs-view"],
[data-testid="enduserdocs-panel"],
[data-testid="runs-graph"],
[data-testid="stage-artifact-detail"] {
  width: min(100%, 960px);
  margin: 0 auto;
}
[data-testid="devdocs-view"] { width: min(100%, 1120px); }
.devdocs-toolbar {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  color: var(--muted);
}
.devdocs-toolbar strong { color: var(--ink); font-size: 14px; }
.devdocs-toolbar > span { margin-right: auto; color: var(--faint); font-size: 11px; }
.devdocs-tools { display: flex; flex-wrap: wrap; gap: 5px; justify-content: flex-end; }
.devdocs-tools button {
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  color: var(--muted);
  background: #fff;
  cursor: pointer;
  font-size: 11px;
}
.devdocs-tools button:hover,
.devdocs-tools button[data-active="true"] { color: var(--ink); border-color: #999; background: var(--hover); }
.devdocs-layout {
  display: grid;
  min-height: 0;
  gap: 14px;
}
.devdocs-layout.split { grid-template-columns: minmax(0, .92fr) minmax(0, 1.08fr); }
.devdocs-layout:not(.split) { grid-template-columns: minmax(0, 1fr); }
.devdocs-layout:not(.split) [data-testid="devdocs-editor"] { display: none; }
[data-testid="devdocs-editor"] {
  width: 100%;
  min-height: 480px;
  padding: 18px;
  resize: none;
  border: 1px solid var(--line);
  border-radius: 9px;
  outline: none;
  color: #4a4a4a;
  background: #fafafa;
  font: 12px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
}
[data-testid="devdocs-editor"]:focus { border-color: #999; box-shadow: 0 0 0 3px rgba(0,0,0,.06); }
[data-testid="devdocs-rendered"] { min-width: 0; overflow: auto; }
.devdocs-pane-container {
  display: grid;
  min-height: 0;
  flex: 1;
  gap: 12px;
  overflow: auto;
  grid-template-columns: minmax(0, 1fr);
}
.devdocs-pane-container[data-pane-count="2"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.devdocs-pane-container[data-pane-count="3"] { grid-template-columns: repeat(3, minmax(340px, 1fr)); }
.devdocs-pane-container[data-pane-count="4"] { grid-template-columns: repeat(4, minmax(300px, 1fr)); }
.doc-pane {
  display: flex;
  min-width: 0;
  min-height: 480px;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
}
.doc-pane-bar {
  display: flex;
  min-height: 40px;
  align-items: center;
  gap: 6px;
  padding: 5px 7px;
  border-bottom: 1px solid var(--line);
  background: #fafafa;
}
.doc-pane-bar select {
  min-width: 0;
  max-width: 190px;
  padding: 6px 7px;
  border: 1px solid var(--line-strong);
  border-radius: 5px;
  color: var(--ink);
  background: #fff;
  font-size: 11px;
}
.doc-pane-tools { display: flex; min-width: 0; margin-left: auto; gap: 3px; }
.doc-pane-tools button {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 5px;
  color: var(--muted);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
}
.doc-pane-tools button:hover { border-color: var(--line-strong); background: #f0f0f0; color: var(--ink); }
.doc-pane-tools button[data-pane-action="save"] { width: auto; padding: 0 7px; border-color: var(--line); }
.doc-pane-tools button[disabled] { cursor: not-allowed; opacity: .42; }
.doc-pane-status { min-width: 42px; color: var(--faint); font-size: 10px; white-space: nowrap; }
.vditor-mount { min-height: 0; flex: 1; overflow: auto; }
.vditor-mount > textarea {
  width: 100%;
  height: 100%;
  min-height: 480px;
  padding: 18px;
  resize: none;
  border: 0;
  outline: 0;
  color: #4a4a4a;
  background: #fff;
  font: 13px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace;
}
.doc-pane .vditor { height: 100%; border: 0; }
.doc-pane .vditor-content { min-height: 100%; padding: 24px; }
.doc-pane .vditor-ir .discussion-block[data-discussion="1"],
.doc-pane .vditor-ir blockquote[data-discussion="1"] { transition: opacity .15s ease; }
.doc-pane.discussions-collapsed [data-discussion="1"] { display: none !important; }
.doc-pane.discussions-collapsed .doc-pane-bar::after { content: "讨论已隐藏"; color: var(--faint); font-size: 10px; }
[data-testid="devdocs-verdict"] {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}
.verdict-card {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}
.verdict-card header { display: flex; align-items: center; gap: 8px; }
.verdict-card header a { min-width: 0; flex: 1; color: var(--ink); font-weight: 600; text-decoration: none; }
.verdict-card p { margin: 7px 0; color: var(--muted); }
.verdict-badge { color: var(--faint); font: 10px ui-monospace, monospace; }
.verdict-card[data-unresolved="true"] .verdict-badge { color: #9a6700; }
.verdict-checks { display: flex; flex-wrap: wrap; gap: 5px; }
.verdict-checks button {
  padding: 4px 7px;
  border: 1px solid var(--line);
  border-radius: 5px;
  color: var(--faint);
  background: #fafafa;
  cursor: pointer;
  font-size: 11px;
}
.verdict-checks button[aria-pressed="true"] { color: var(--ink); border-color: #a7a7a7; background: #f0f0f0; }
.discussion-block { transition: opacity .15s ease; }
.devdocs-discussions-hidden .discussion-block { display: none !important; }
.devdocs-discussions-hidden [data-testid="devdocs-rendered"]::after { content: "Inline discussions hidden"; display: block; color: var(--faint); font-size: 11px; }
[data-testid="devdocs-rendered"],
[data-testid="devdocs-source"],
[data-testid="enduserdocs-preview"],
[data-testid="enduserdocs-editor"],
[data-testid="stage-artifact-detail"] {
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
}
[data-testid="devdocs-rendered"] { padding: 24px; }
[data-testid="devdocs-source"] {
  max-height: 280px;
  margin: 14px 0 0;
  padding: 16px;
  overflow: auto;
  color: #555;
  background: #fafafa;
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
}
[data-testid="enduserdocs-panel"] { display: grid; gap: 12px; }
[data-testid="enduserdocs-preview"] { min-height: 180px; padding: 20px; white-space: pre-wrap; }
[data-testid="enduserdocs-editor"] {
  width: 100%;
  min-height: 300px;
  padding: 16px;
  resize: vertical;
  outline: 0;
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
}
[data-testid="enduserdocs-sha-display"] { color: var(--faint); font: 11px ui-monospace, monospace; }
[data-testid="runs-graph"] { display: grid; gap: 8px; }
[data-testid^="runs-node-"] {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  text-align: left;
}
[data-testid="stage-artifact-detail"] { margin-top: 16px; padding: 18px; }
[data-settings-pane="menu"] {
  display: flex;
  width: 220px;
  flex-direction: column;
  gap: 3px;
  padding: 0;
}
[data-settings-pane="detail"] {
  min-height: 160px;
  flex: 1;
  margin-left: 28px;
  padding: 20px;
  border-left: 1px solid var(--line);
  color: var(--muted);
}
[aria-disabled="true"] { opacity: .5; cursor: pointer; }
[data-testid="wiki-unknown-page"] { color: var(--muted); }
#accounts-menu {
  position: fixed;
  bottom: 14px;
  left: 66px;
  z-index: 10;
  min-width: 140px;
  padding: 5px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 28px rgba(0,0,0,.12);
}
#accounts-menu [role="menuitem"] { width: 100%; padding: 8px 10px; border: 0; border-radius: 6px; background: transparent; text-align: left; }
#accounts-menu [role="menuitem"]:hover { background: var(--hover); }

@media (max-width: 760px) {
  #workbench { grid-template-columns: 50px minmax(190px, 34vw) minmax(0, 1fr); }
  [data-louke-region="sidebar"] { padding: 16px 9px; }
  [data-louke-region="main"] > [role="tablist"] { padding: 0 14px; }
  [data-tab-content] { padding: 20px 16px; }
}
"""
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>Louke Workbench</title>
<style>{styles}</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/vditor/dist/index.css" />
<script src="https://cdn.jsdelivr.net/npm/vditor/dist/index.min.js"></script></head><body><div id="workbench">
<div data-testid="workbench-toolbar" data-louke-region="toolbar" role="toolbar" aria-label="Workbench">{toolbar}</div>
 <aside data-testid="workbench-sidebar" data-louke-region="sidebar" role="complementary" data-sidebar-kind="chat">{chat_sidebar}{devdocs}{end_user_docs}{wiki}{runs_sidebar}</aside>
 <main data-testid="workbench-main" data-louke-region="main"><div role="tablist" aria-label="Open workbench tabs"><button role="tab" data-testid="workbench-tab" data-tab-key="chat" aria-selected="true">Chat</button><button role="tab" data-testid="workbench-tab" data-tab-key="dev-docs" aria-selected="false" hidden>Dev Docs</button><button role="tab" data-testid="workbench-tab" data-tab-key="runs" aria-selected="false" hidden>Runs</button></div>{chat_content}{devdocs_view}{runs_content}</main>
<div id="accounts-menu" data-testid="accounts-menu" role="menu" hidden><button role="menuitem" data-testid="accounts-logout">Logout</button></div></div>
<script>
const tabs=new Set(['chat']); let activeTab='chat'; const labels={{chat:'Chat','dev-docs':'Dev Docs','end-user-docs':'End User Docs',wiki:'Wiki',runs:'Runs',settings:'Settings'}};
function ensureTab(tabKey){{if(tabs.has(tabKey))return;tabs.add(tabKey);const tab=document.createElement('button');tab.type='button';tab.role='tab';tab.dataset.testid='workbench-tab';tab.dataset.tabKey=tabKey;tab.textContent=labels[tabKey]||tabKey;tab.setAttribute('aria-selected','false');document.querySelector('[role="tablist"]').append(tab);}}
 function showMain(tabKey){{const main=document.querySelector('[data-louke-region="main"]');main.querySelectorAll('[data-tab-content]').forEach(node=>node.hidden=node.dataset.tabContent!==tabKey);let content=main.querySelector('[data-tab-content="'+tabKey+'"]');if(!content){{content=document.createElement('div');content.dataset.tabContent=tabKey;main.append(content);}}content.hidden=false;if(tabKey==='settings')content.innerHTML={settings!r};else if(tabKey==='wiki'&&!content.textContent.trim())content.textContent='README';else if(tabKey==='dev-docs'&&!content.textContent.trim())content.textContent='Dev Docs';else if(tabKey==='end-user-docs'&&!content.querySelector('[data-testid="enduserdocs-panel"]'))content.innerHTML='<div data-testid="enduserdocs-panel"><div data-testid="enduserdocs-preview"></div><textarea data-testid="enduserdocs-editor"></textarea><button type="button" data-testid="enduserdocs-save" disabled></button><span data-testid="enduserdocs-sha-display"></span><div data-testid="enduserdocs-toast" role="status" hidden></div><div data-testid="enduserdocs-conflict" hidden><strong>文件已被外部修改</strong><button type="button" data-enduserdocs-reload>重新加载并放弃我的编辑</button><button type="button" data-enduserdocs-force>仍要覆盖</button></div></div>';}}
 let devdocsVersionToken=''; let devdocsRenderTimer=null;
 function devdocsView(){{return document.querySelector('[data-testid="devdocs-view"]');}}
 function devdocsToast(message){{const toast=document.querySelector('[data-testid="devdocs-toast"]');if(!toast)return;toast.textContent=message;toast.hidden=!message;}}
 function markDiscussionHtml(html){{return String(html||'').replaceAll('<section class="discussion-block">','<section class="discussion-block" data-discussion="1">');}}
 async function loadDevDoc(){{const view=devdocsView();if(!view)return;const response=await fetch('/api/docs/'+encodeURIComponent(view.dataset.specId)+'/'+encodeURIComponent(view.dataset.docName));if(!response.ok){{devdocsToast('文档加载失败 ('+response.status+')');return;}}const data=await response.json();devdocsVersionToken=data.version_token||'';const editor=view.querySelector('[data-testid="devdocs-editor"]');if(editor&&document.activeElement!==editor)editor.value=data.body_md||'';const rendered=view.querySelector('[data-testid="devdocs-rendered"]');if(rendered)rendered.innerHTML=markDiscussionHtml(data.rendered_html);const status=view.querySelector('[data-testid="devdocs-save-status"]');if(status)status.textContent='已加载';}}
 async function renderDevDoc(){{const view=devdocsView();if(!view)return;const editor=view.querySelector('[data-testid="devdocs-editor"]');const rendered=view.querySelector('[data-testid="devdocs-rendered"]');if(!editor||!rendered)return;const response=await fetch('/api/render',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{kind:'doc',doc_name:view.dataset.docName,body_md:editor.value}})}});if(!response.ok){{devdocsToast('预览失败 ('+response.status+')');return;}}const data=await response.json();rendered.innerHTML=markDiscussionHtml(data.rendered_html);}}
 function nextDevdocsDiscussion(){{const view=devdocsView();if(!view)return;const items=[...view.querySelectorAll('[data-discussion="1"]')];if(!items.length){{devdocsToast('没有找到 inline-discussion');return;}}const current=view.dataset.discussionCursor?Number(view.dataset.discussionCursor):-1;const next=items[(current+1)%items.length];view.dataset.discussionCursor=String((current+1)%items.length);next.scrollIntoView({{behavior:'smooth',block:'center'}});}}
 function nextDevdocsUnresolved(){{const view=devdocsView();if(!view)return;const cards=[...view.querySelectorAll('[data-testid="devdocs-verdict-card"][data-unresolved="true"]')];const discussions=[...view.querySelectorAll('[data-discussion="1"]')].filter(item=>!/[✓]|\[(?:resolved|已解决|已决定|decided)\]/i.test(item.textContent||''));const items=cards.length?cards:discussions;if(!items.length){{devdocsToast('所有 FR/NFR/AC 与 discussion 均已解决');return;}}const current=view.dataset.unresolvedCursor?Number(view.dataset.unresolvedCursor):-1;const next=items[(current+1)%items.length];view.dataset.unresolvedCursor=String((current+1)%items.length);next.scrollIntoView({{behavior:'smooth',block:'center'}});}}
 async function saveDevDoc(){{const view=devdocsView();if(!view)return;const editor=view.querySelector('[data-testid="devdocs-editor"]');const response=await fetch('/api/docs/'+encodeURIComponent(view.dataset.specId)+'/'+encodeURIComponent(view.dataset.docName),{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{body_md:editor.value,version_token:devdocsVersionToken,force:false}})}});const data=await response.json();if(!response.ok){{devdocsToast(data.error||'保存失败');return;}}devdocsVersionToken=data.version_token||'';await loadDevDoc();}}
 function handleDevdocsAction(action,button){{const view=devdocsView();if(!view)return;if(action==='toggle-discussions'){{const hidden=view.classList.toggle('devdocs-discussions-hidden');button.dataset.active=String(hidden);return;}}if(action==='next-discussion')return nextDevdocsDiscussion();if(action==='next-unresolved')return nextDevdocsUnresolved();if(action==='split'){{const layout=view.querySelector('[data-testid="devdocs-layout"]');layout.classList.toggle('split');button.dataset.active=String(layout.classList.contains('split'));return;}}if(action==='save')return saveDevDoc();if(action==='reload')return loadDevDoc();}}
 document.querySelectorAll('[data-doc-action]').forEach(button=>button.addEventListener('click',()=>handleDevdocsAction(button.dataset.docAction,button)));
 document.querySelectorAll('[data-verdict-field]').forEach(button=>button.addEventListener('click',async()=>{{const view=devdocsView();const response=await fetch('/api/docs/'+encodeURIComponent(view.dataset.specId)+'/'+encodeURIComponent(view.dataset.docName)+'/toggle-status',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{fr_id:button.dataset.frId,field:button.dataset.verdictField,version_token:docWorkspaceVersionToken()}})}});if(!response.ok){{devdocsToast('状态更新失败 ('+response.status+')');return;}}location.reload();}}));
 const devEditor=document.querySelector('[data-testid="devdocs-editor"]');if(devEditor){{devEditor.addEventListener('input',()=>{{const status=document.querySelector('[data-testid="devdocs-save-status"]');if(status)status.textContent='有未保存修改';clearTimeout(devdocsRenderTimer);devdocsRenderTimer=setTimeout(renderDevDoc,250);}});}}
 if(new URLSearchParams(location.search).has('doc'))loadDevDoc();
 {_devdocs_script()}
 const saveLabel='S'+'ave'; let currentDoc=null; let currentMtime=null; let loadedBody='';
 function docPreview(body){{const preview=document.querySelector('[data-testid="enduserdocs-preview"]');preview.textContent=body;}}
 function setDocDirty(){{const editor=document.querySelector('[data-testid="enduserdocs-editor"]');const button=document.querySelector('[data-testid="enduserdocs-save"]');if(!editor||!button)return;button.disabled=editor.value===loadedBody;button.textContent=saveLabel+(button.disabled?'':' *');docPreview(editor.value);}}
 async function loadDoc(path){{openTab('end-user-docs');const response=await fetch('/api/files?path='+encodeURIComponent(path));if(!response.ok)return;const doc=await response.json();currentDoc=path;currentMtime=doc.mtime;loadedBody=doc.body_md;const editor=document.querySelector('[data-testid="enduserdocs-editor"]');editor.value=loadedBody;document.querySelector('[data-testid="enduserdocs-sha-display"]').textContent=doc.sha256;setDocDirty();}}
 async function saveDoc(force){{const editor=document.querySelector('[data-testid="enduserdocs-editor"]');const response=await fetch('/api/files',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{path:currentDoc,body_md:editor.value,expected_mtime:currentMtime,force:!!force}})}});const payload=await response.json();if(response.status===409){{const dialog=document.querySelector('[data-testid="enduserdocs-conflict"]');dialog.hidden=false;return;}}if(!response.ok){{const toast=document.querySelector('[data-testid="enduserdocs-toast"]');toast.textContent=payload.code+': '+payload.message;toast.hidden=false;return;}}loadedBody=editor.value;currentMtime=payload.version_token;document.querySelector('[data-testid="enduserdocs-sha-display"]').textContent=payload.sha256;setDocDirty();}}
function renderSidebar(activity){{const sidebar=document.querySelector('[data-louke-region="sidebar"]');sidebar.dataset.sidebarKind=activity;sidebar.querySelectorAll('section[data-sidebar-kind]').forEach(s=>s.hidden=s.dataset.sidebarKind!==activity);}}
 const transcripts={{}}; const sessions={{}}; const renderedMessages={{}}; const chatStreams={{}}; const chatSubmissions={{}}; let activeAgent='maestro';
 document.querySelectorAll('[data-chat-agent]').forEach(button=>{{transcripts[button.dataset.chatAgent]=document.querySelector('[data-testid="chat-transcript-'+button.dataset.chatAgent.toLowerCase()+'"]');}});
 function showToast(message){{const toast=document.querySelector('[data-testid="chat-toast"]');toast.textContent=message;toast.hidden=false;}}
 function selectAgent(agent){{if(!transcripts[agent]){{showToast('未知 Agent: '+agent+'; 已回退到 Maestro');agent='maestro';}}if(agent===activeAgent&&!transcripts[agent].hidden)return;const previous=activeAgent;if(chatStreams[previous]){{chatStreams[previous].close();delete chatStreams[previous];}}activeAgent=agent;document.querySelectorAll('[data-chat-agent]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.chatAgent===agent)));Object.entries(transcripts).forEach(([name,node])=>node.hidden=name!==agent);const input=document.querySelector('[data-testid="chat-input"]');input.placeholder='Message '+agent+'...';if(sessions[agent]){{refreshChat(agent);connectChatStream(agent,sessions[agent]);}}}}
 function openTab(activity){{ensureTab(activity);activeTab=activity;document.querySelectorAll('[data-testid="workbench-tab"]').forEach(t=>t.setAttribute('aria-selected',String(t.dataset.tabKey===activity)));document.querySelectorAll('[data-activity]').forEach(button=>button.setAttribute('aria-current',button.dataset.activity===activity?'page':'false'));if(activity!=='settings')renderSidebar(activity);showMain(activity);if(activity==='dev-docs')initDocWorkspace();if(activity==='chat')selectAgent(activeAgent);}}
  document.querySelectorAll('[data-activity]').forEach(button=>button.addEventListener('click',()=>{{const activity=button.dataset.activity;if(activity==='gears')return openTab('settings');if(activity==='accounts'){{document.querySelector('[data-testid="accounts-menu"]').hidden=false;return;}}openTab(activity);}}));
  const terminalRunStatuses=new Set(['completed','cancelled','failed','archived']);
  function runGroupItems(key){{return document.querySelector('[data-runs-group="'+key+'"]');}}
  function renderRunGroup(key,items){{const group=runGroupItems(key);if(!group)return;group.replaceChildren();if(!items.length){{const empty=document.createElement('span');empty.dataset.testid=key==='current'?'runs-empty-state':'runs-history-empty-state';empty.textContent='No workflow runs';group.append(empty);return;}}items.forEach(item=>{{const button=document.createElement('button');button.type='button';button.dataset.testid='runs-project-'+item.run_id;button.dataset.runId=item.run_id;button.textContent=(item.project_name||item.definition_id||item.run_id)+(item.status_unknown?' (unknown status)':'');group.append(button);}});}}
  async function loadRuntimeRun(runId){{const graphHost=document.querySelector('[data-testid="runs-graph"]');if(!graphHost)return;const responses=await Promise.all([fetch('/api/runtime/runs/'+encodeURIComponent(runId)),fetch('/api/runtime/runs/'+encodeURIComponent(runId)+'/events'),fetch('/api/gates/runs/'+encodeURIComponent(runId)+'/gates'),fetch('/api/ui/runs/'+encodeURIComponent(runId)+'/graph')]);if(!responses[0].ok)return;const run=await responses[0].json();const graph=responses[3].ok?await responses[3].json():{{nodes:[]}};graphHost.replaceChildren();graphHost.dataset.runId=runId;graphHost.dataset.runStatus=run.status;graphHost.dataset.eventCount=String((await responses[1].json()).items?.length||0);graphHost.dataset.gateCount=String((await responses[2].json()).items?.length||0);(graph.nodes||[]).forEach(node=>{{const button=document.createElement('button');button.type='button';button.dataset.testid='runs-node-'+node.stage_id;button.dataset.stageId=node.stage_id;button.dataset.runId=runId;button.textContent=(node.label||node.stage_id)+' ['+(node.state||'unknown')+']';if(node.unknown)button.dataset.unknown='true';graphHost.append(button);}});}}
  async function refreshRuntimeRuns(){{const response=await fetch('/api/runtime/runs');if(!response.ok)return;const items=(await response.json()).items||[];renderRunGroup('current',items.filter(item=>!terminalRunStatuses.has(item.status)));renderRunGroup('history',items.filter(item=>terminalRunStatuses.has(item.status)));}}
  document.addEventListener('click',event=>{{const runButton=event.target.closest('[data-run-id]');if(runButton){{openTab('runs');loadRuntimeRun(runButton.dataset.runId);}}}});
  refreshRuntimeRuns();
  document.addEventListener('click',async event=>{{const button=event.target.closest('[data-stage-id]');if(!button)return;const detail=document.querySelector('[data-testid="stage-artifact-detail"]');const run=button.dataset.runId||document.querySelector('[data-testid="runs-graph"]')?.dataset.runId;if(!run)return;const response=await fetch('/api/ui/runs/'+encodeURIComponent(run)+'/stages/'+encodeURIComponent(button.dataset.stageId)+'/artifact');const item=await response.json();detail.replaceChildren();const title=document.createElement('h2');title.textContent='Stage artifact';detail.append(title);const fields=[['sha256',item.digest],['verdict',item.verdict],['required_reviewer',item.required_reviewer],['review_conclusion',item.review_conclusion]];const list=document.createElement('dl');fields.forEach(([label,value])=>{{const term=document.createElement('dt');term.textContent=label;const description=document.createElement('dd');description.textContent=String(value||'');list.append(term,description);}});detail.append(list);detail.hidden=false;}});
 document.querySelector('[data-testid="chat-agent-list"]').addEventListener('click',event=>{{const button=event.target.closest('[data-chat-agent]');if(button)selectAgent(button.dataset.chatAgent);}});
 document.addEventListener('click',event=>{{const button=event.target.closest('[data-chat-agent]');if(button&&!transcripts[button.dataset.chatAgent])selectAgent(button.dataset.chatAgent);}});
 function addChatMessage(agent,message){{const node=transcripts[agent];if(!node||!message||!message.content)return;const id=message.id||agent+'-'+message.role+'-'+message.content;renderedMessages[agent]??=new Set();if(renderedMessages[agent].has(id))return;renderedMessages[agent].add(id);const item=document.createElement('p');item.dataset.role=message.role;item.dataset.messageId=message.id||'';item.textContent=message.content;node.append(item);node.scrollTop=node.scrollHeight;}}
 function appendChatDelta(agent,event){{const node=transcripts[agent];if(!node)return;let item=[...node.querySelectorAll('[data-message-id]')].find(candidate=>candidate.dataset.messageId===event.message_id);if(!item){{item=document.createElement('p');item.dataset.role='assistant';item.dataset.messageId=event.message_id;node.append(item);}}item.textContent+=(event.delta||'');renderedMessages[agent]??=new Set();if(event.message_id)renderedMessages[agent].add(event.message_id);node.scrollTop=node.scrollHeight;}}
 function connectChatStream(agent,id){{if(chatStreams[agent])chatStreams[agent].close();const source=new EventSource('/api/opencode/instances/'+encodeURIComponent(id)+'/events');chatStreams[agent]=source;source.addEventListener('chat.message.delta',event=>{{const payload=JSON.parse(event.data);appendChatDelta(agent,payload);showToast('Agent 正在回复…');}});source.addEventListener('chat.message.completed',async event=>{{const payload=JSON.parse(event.data);if(payload.content){{const node=transcripts[agent];const item=[...node.querySelectorAll('[data-message-id]')].find(candidate=>candidate.dataset.messageId===payload.message_id);if(item)item.textContent=payload.content;}}await refreshChat(agent);showToast('');source.close();}});source.addEventListener('chat.message.error',event=>{{const payload=JSON.parse(event.data);showToast(payload.error||'Agent 回复失败');source.close();}});source.onerror=()=>{{if(source.readyState===EventSource.CLOSED)return;showToast('实时连接中断，正在等待 Agent transcript');}};}}
 async function chatSession(agent){{if(sessions[agent])return sessions[agent];const createdResponse=await fetch('/api/opencode/instances',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{agent}})}});const created=await createdResponse.json();if(!createdResponse.ok)throw new Error(created.message||created.error||'OpenCode session creation failed');sessions[agent]=created.instance.id;return sessions[agent];}}
 async function refreshChat(agent){{const id=sessions[agent];if(!id)return [];const response=await fetch('/api/opencode/instances/'+encodeURIComponent(id)+'/messages');if(!response.ok)return [];const payload=await response.json();const items=payload.items||[];items.forEach(message=>addChatMessage(agent,message));return items;}}
 async function sendChat(content){{const agent=activeAgent;if(chatSubmissions[agent])return;chatSubmissions[agent]=true;const input=document.querySelector('[data-testid="chat-input"]');const button=document.querySelector('[data-testid="chat-submit"]');button.disabled=true;showToast('');try{{const id=await chatSession(agent);connectChatStream(agent,id);const response=await fetch('/api/opencode/instances/'+encodeURIComponent(id)+'/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{content}})}});const payload=await response.json();if(!response.ok)throw new Error(payload.message||payload.error||'Chat request failed ('+response.status+')');addChatMessage(agent,payload.message);input.value='';showToast('Agent 正在回复…');}}catch(error){{if(chatStreams[agent])chatStreams[agent].close();showToast(error.message||'Chat request failed');}}finally{{chatSubmissions[agent]=false;button.disabled=false;input.focus();}}}}
 document.querySelector('[data-testid="chat-form"]').addEventListener('submit',event=>{{event.preventDefault();const input=document.querySelector('[data-testid="chat-input"]');const content=input.value.trim();if(content)sendChat(content);}});
  selectAgent('maestro');
 openTab(new URLSearchParams(location.search).has('doc')?'dev-docs':'chat');
document.addEventListener('click',event=>{{const item=event.target.closest('[data-setting]');if(!item)return;const detail=document.querySelector('[data-testid="settings-detail"]');detail.dataset.selectedSetting=item.dataset.setting;detail.querySelector('[data-testid="settings-placeholder-title"]').textContent=item.childNodes[0].textContent.trim();detail.querySelector('[data-testid="settings-placeholder-detail"]').textContent='待 v0.15；当前入口不会执行任何写操作。';}});
document.querySelector('[data-testid="accounts-logout"]').addEventListener('click',()=>fetch('/api/auth/logout',{{method:'POST'}}).then(()=>location.href='/'));
 document.querySelectorAll('[data-devdocs-spec]').forEach(item=>item.addEventListener('toggle',()=>localStorage.setItem('louke.dev-docs.tree.'+item.dataset.devdocsSpec,item.open?'expanded':'collapsed')));
 document.querySelectorAll('[data-devdocs-spec]').forEach(item=>{{item.open=localStorage.getItem('louke.dev-docs.tree.'+item.dataset.devdocsSpec)==='expanded';}});
 document.querySelectorAll('[data-doc-path]').forEach(item=>item.addEventListener('click',()=>{{const parts=item.dataset.docPath.split('/');location.href='/workbench?spec='+encodeURIComponent(parts[3])+'&doc='+encodeURIComponent(parts[4].replace(/\\.md$/,''));}}));
 document.querySelectorAll('[data-wiki-page]').forEach(item=>item.addEventListener('click',()=>{{const key=item.dataset.wikiPage;if(key==='unknown-page')document.querySelector('[data-tab-content="wiki"]').innerHTML='<div data-testid="wiki-unknown-page" data-unknown="true">未知页面: '+key+' <a href="/">home</a></div>';else document.querySelector('[data-tab-content="wiki"]').textContent=key;}}));
 document.querySelectorAll('[data-enduserdocs-path]').forEach(item=>item.addEventListener('click',()=>loadDoc(item.dataset.enduserdocsPath)));
 document.addEventListener('input',event=>{{if(event.target.matches('[data-testid="enduserdocs-editor"]'))setDocDirty();}});
 document.addEventListener('click',event=>{{if(event.target.matches('[data-testid="enduserdocs-save"]'))saveDoc(false);if(event.target.matches('[data-enduserdocs-reload]'))loadDoc(currentDoc);if(event.target.matches('[data-enduserdocs-force]')&&confirm('确认覆盖外部修改？'))saveDoc(true);}});
</script></body></html>"""


# ---------------------------------------------------------------------------
# IF-PROJECT-01 / IF-GUIDE-01 / IF-STATUS-01 / IF-COMPAT-01:
# Projects activity (Archer §5.3.5 stubs → Devon implementation).
# ---------------------------------------------------------------------------

_PROJECTS_STYLES = """
:root { color-scheme: light; --ink:#1d1d1f; --muted:#6b6b6b; --line:#e3e3e3;
  --accent:#050505; --error:#b42318; --panel:#fafafa; }
* { box-sizing: border-box; }
html, body { height: 100%; }
body { margin:0; overflow:hidden; color:var(--ink); background:#fff;
  font:13px/1.45 Inter, ui-sans-serif, -apple-system, "Segoe UI", sans-serif; }
button, input, textarea { font:inherit; }
[hidden] { display:none !important; }
#workbench { display:grid; grid-template-columns:56px minmax(240px,280px) minmax(0,1fr);
  width:100vw; height:100dvh; min-height:520px; overflow:hidden; }
[data-louke-region="toolbar"] { display:flex; flex-direction:column; align-items:center;
  gap:6px; padding:12px 10px; color:#fff; background:var(--accent); }
.toolbar-brand { display:grid; width:36px; height:36px; margin-bottom:12px; place-items:center;
  border:1px solid #3a3a3a; border-radius:9px; color:#fff; background:#181818;
  font-size:15px; font-weight:700; }
[data-louke-region="toolbar"] button { display:grid; width:36px; height:36px; padding:0;
  place-items:center; border:1px solid transparent; border-radius:9px; color:#a7a7a7;
  background:transparent; cursor:pointer; font-size:17px; }
[data-louke-region="toolbar"] button:hover { color:#fff; background:#242424; }
[data-louke-region="toolbar"] button[aria-current="page"] { color:#fff; border-color:#3c3c3c;
  background:#2b2b2b; }
[data-louke-region="sidebar"] { overflow:auto; padding:20px 14px; border-right:1px solid var(--line);
  background:var(--panel); }
[data-louke-region="sidebar"] > strong { display:block; margin:2px 8px 12px; color:var(--muted);
  font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
[data-louke-region="main"] { display:flex; min-width:0; flex-direction:column; overflow:auto;
  padding:28px clamp(22px,4vw,64px); }
.projects-card { width:min(100%,640px); margin:0 auto; }
.projects-card h1 { margin:0 0 8px; font-size:20px; }
.projects-lede { margin:0 0 20px; color:var(--muted); }
.projects-actions { display:flex; gap:8px; margin-top:16px; }
.projects-actions button { min-height:40px; padding:0 18px; border:0; border-radius:8px;
  color:#fff; background:var(--accent); font-weight:600; cursor:pointer; }
.projects-actions button:disabled { opacity:.5; cursor:default; }
.guide-messages { display:grid; gap:8px; margin-bottom:12px; max-height:40vh; overflow:auto; }
.guide-msg { padding:8px 10px; border:1px solid var(--line); border-radius:8px; font-size:12px; }
.guide-msg[data-authority="runtime"] { border-left:3px solid var(--accent); }
.guide-msg[data-authority="guide"] { border-left:3px solid #6b6b6b; }
.guide-composer { display:flex; gap:6px; }
.guide-composer textarea { flex:1; min-height:36px; padding:8px 10px; border:1px solid var(--line);
  border-radius:8px; resize:vertical; }
.guide-composer button { min-height:36px; padding:0 14px; border:0; border-radius:8px;
  color:#fff; background:var(--accent); font-weight:600; cursor:pointer; }
.conflict-list { display:grid; gap:8px; margin-top:12px; }
.conflict-item { padding:10px 12px; border:1px solid var(--error); border-radius:8px;
  color:var(--error); font-size:12px; }
.status-placeholder { padding:20px; border:1px solid var(--line); border-radius:10px;
  color:var(--muted); }
[data-attempt-id] { cursor:pointer; }
[data-attempt-id]:hover { background:#f0f0f0; }
[data-attempt-id][data-selected="true"] { outline:2px solid var(--accent); }
[data-action="return"] { margin-left:8px; padding:2px 8px; border:1px solid var(--line);
  border-radius:4px; background:#fff; cursor:pointer; font-size:11px; }
[data-role="return-confirm"] { position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
  padding:24px; border:1px solid var(--line); border-radius:12px; background:#fff;
  box-shadow:0 8px 32px rgba(0,0,0,.15); z-index:100; }
[data-louke-region="settings"] { display:flex; gap:0; padding:20px clamp(22px,4vw,64px);
  border-top:1px solid var(--line); background:var(--panel); }
[data-settings-pane="menu"] { display:flex; width:220px; flex-direction:column; gap:3px; padding:0; }
[data-settings-pane="menu"] button { display:flex; min-height:34px; align-items:center; gap:9px;
  padding:7px 9px; border:1px solid transparent; border-radius:7px; color:#454545;
  background:transparent; cursor:pointer; font-size:13px; text-align:left; }
[data-settings-pane="menu"] button:hover { border-color:var(--line); background:#fff; }
[data-settings-pane="menu"] button span { margin-left:auto; color:var(--faint); font-size:11px; }
[data-settings-pane="detail"] { min-height:160px; flex:1; margin-left:28px; padding:20px;
  border-left:1px solid var(--line); color:var(--muted); }
[data-settings-pane="detail"] h2 { margin:0 0 8px; color:var(--ink); font-size:16px; }
[data-settings-pane="detail"] h3 { margin:14px 0 4px; color:var(--ink); font-size:13px; }
[data-settings-pane="detail"] dl { margin:6px 0 0; display:grid; grid-template-columns:auto 1fr;
  gap:4px 12px; }
[data-settings-pane="detail"] dt { color:var(--faint); font-size:12px; }
[data-settings-pane="detail"] dd { margin:0; word-break:break-all; font-size:12px; }
[aria-disabled="true"] { opacity:.5; cursor:default; }
"""

_PROJECTS_SCRIPT = """
// IF-PROJECT-01: New Project button navigates to the wizard.
document.querySelectorAll('[data-testid="new-project"]').forEach(function(btn) {
  btn.addEventListener('click', function() {
    window.location.href = '/workbench?activity=projects&action=new_project';
  });
});
// IF-STATUS-01: timeline node selection updates URL without changing active pointer.
function selectTimelineNode(node) {
  var attId = node.getAttribute('data-attempt-id');
  var stageId = node.getAttribute('data-stage-id') || node.getAttribute('data-stage');
  if (!attId && !stageId) return;
  var url = new URL(window.location);
  if (attId) url.searchParams.set('selected_attempt', attId);
  else url.searchParams.set('selected_stage', stageId);
  window.history.pushState({}, '', url);
  document.querySelectorAll('[data-testid="stage-timeline"] [tabindex="0"]').forEach(function(n) {
    n.removeAttribute('data-selected');
  });
  node.setAttribute('data-selected', 'true');
}
document.querySelectorAll('[data-attempt-id]').forEach(function(node) {
  node.addEventListener('click', function() { selectTimelineNode(node); });
});
document.querySelectorAll('[data-testid="stage-timeline"] [tabindex="0"]').forEach(function(node, index, nodes) {
  node.addEventListener('keydown', function(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectTimelineNode(node);
      return;
    }
    var nextIndex = index;
    if (event.key === 'ArrowRight') nextIndex = Math.min(index + 1, nodes.length - 1);
    if (event.key === 'ArrowLeft') nextIndex = Math.max(index - 1, 0);
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = nodes.length - 1;
    if (nextIndex !== index) {
      event.preventDefault();
      nodes[nextIndex].focus();
    }
  });
});
// IF-RETURN-01: return button opens a confirm dialog.
document.querySelectorAll('[data-action="return"]').forEach(function(btn) {
  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    var attId = btn.getAttribute('data-attempt-id');
    var existing = document.querySelector('[data-role="return-confirm"]');
    if (existing) existing.remove();
    var dlg = document.createElement('div');
    dlg.setAttribute('data-role', 'return-confirm');
    dlg.innerHTML = '<h3>Confirm return</h3>'
      + '<p>Return to attempt ' + attId + '?</p>'
      + '<button type="button">Confirm</button>'
      + '<button type="button" data-action="cancel">Cancel</button>';
    document.body.appendChild(dlg);
    dlg.querySelector('button:not([data-action])').addEventListener('click', function() {
      dlg.remove();
      var card = document.querySelector('[data-testid="active-card"]');
      if (card) {
        card.setAttribute('data-attempt-id', attId);
        card.querySelector('h2').textContent = 'Active: returned to ' + attId;
      }
      var body = document.querySelector('[data-testid="status-cockpit"]');
      if (body) {
        var note = document.createElement('p');
        note.textContent = 'Return edge appended: active → ' + attId;
        note.setAttribute('data-testid', 'return-edge-appended');
        body.appendChild(note);
      }
    });
    dlg.querySelector('[data-action="cancel"]').addEventListener('click', function() {
      dlg.remove();
    });
  });
});
"""


def _render_project_story_document(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the authenticated canonical Story in the Workbench Dev Docs URL.

    Args:
        request: Request containing ``project``, ``document`` and optional
            ``revision`` query parameters.

    Returns:
        The exact Project Story document, an authentication redirect, or a
        locatable 404 response when the identity cannot be resolved.

    Side Effects:
        None.
    """
    from ..auth import SESSION_COOKIE, current_user
    from urllib.parse import quote

    session = request.cookies.get(SESSION_COOKIE)
    if current_user(request.app.state.store, session) is None:
        next_path = str(request.url.path) + "?" + request.url.query
        return RedirectResponse(
            url=f"/login?next={quote(next_path, safe='/')}", status_code=303
        )
    project_id = request.query_params.get("project", "")
    binding = request.app.state.release_entry.current_project(project_id)
    if binding is None or not binding.get("run_id"):
        return _identity_not_found("Project", project_id)
    artifact = request.app.state.story_entry.artifact(str(binding["run_id"]))
    if artifact is None:
        return _identity_not_found("Story", project_id)
    requested_revision = request.query_params.get("revision")
    if requested_revision and requested_revision != str(artifact.revision):
        return _identity_not_found("Story revision", requested_revision)
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Louke — Dev Docs — Story</title>"
        f"<style>{_PROJECTS_STYLES}</style></head><body>"
        '<main class="projects-card" data-testid="dev-docs-story">'
        f"<h1>Story</h1><p>Project: {escape(project_id)} · "
        f"Revision: {artifact.revision}</p>"
        f"<pre>{escape(artifact.body_md)}</pre>"
        f'<p><a href="/workbench?activity=projects&amp;project={escape(project_id)}">'
        "Back to Project Status</a></p></main><script>"
        "(function(){const key=sessionStorage.getItem('louke.pending-draft-clear');"
        "if(key){try{localStorage.removeItem(key);}catch(_){ }"
        "sessionStorage.removeItem('louke.pending-draft-clear');}})();"
        "</script></body></html>"
    )


def _read_project_state(request: Request) -> dict:
    """Read the persisted project state from the workspace ``.louke/`` directory.

    Returns the full raw dict from ``project-state.json``.
    Falls back to ``{"state": "empty"}`` when the file is absent or unreadable.
    """
    import json as _json

    workspace_root = Path(request.app.state.workspace_root)
    state_path = workspace_root / ".louke" / "project-state.json"
    if not state_path.is_file():
        return {"state": "empty", "project_id": None, "conflicts": []}
    try:
        raw = _json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError):
        return {"state": "empty", "project_id": None, "conflicts": []}
    return raw


async def _render_projects_activity(request: Request) -> HTMLResponse:
    """IF-PROJECT-01: Render the Projects activity at ``/workbench?activity=projects``.

    Reads the persisted project state and renders the matching context:

    - ``empty`` → purpose hint + ``New Project`` primary action.
    - ``active`` → Project Status cockpit (IF-STATUS-01).
    - ``conflict`` → each conflicting identity + recovery location.

    The sidebar always shows the Guide session (IF-GUIDE-01).
    """
    state = _read_project_state(request)
    resolved = state.get("state", "empty")
    action = request.query_params.get("action", "")
    new_param = request.query_params.get("new", "")
    toolbar = _projects_toolbar()
    sidebar = _projects_sidebar()
    if action == "new_project" or new_param == "1":
        main = _projects_new_project_wizard(request)
    elif resolved == "active":
        main = _projects_main_panel_active(
            _runtime_active_project_state(request, state)
        )
    else:
        main = _projects_main_panel(resolved)
    # I-15 / AC-FR1512-01/02: the Projects activity is the canonical
    # ``/workbench`` landing once Setup is complete, so it must itself
    # surface the Settings read-model runtime identity alongside the
    # project directory and ``.venv`` path metadata on every render.
    workspace_root = Path(request.app.state.workspace_root)
    settings = _settings(workspace_root)
    return HTMLResponse(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Louke - Projects</title>"
        f"<style>{_PROJECTS_STYLES}</style></head><body>"
        f'<div id="workbench">'
        f'<div data-testid="workbench-toolbar" data-louke-region="toolbar" '
        f'role="toolbar" aria-label="Workbench">{toolbar}</div>'
        f'<aside data-testid="workbench-sidebar" data-louke-region="sidebar" '
        f'data-role="guide" role="complementary">{sidebar}</aside>'
        f'<main data-testid="workbench-main" data-louke-region="main">{main}</main>'
        f"</div>"
        f'<section data-testid="settings-region" data-louke-region="settings" '
        f'aria-label="Settings">{settings}</section>'
        f"<script>{_PROJECTS_SCRIPT}</script>"
        f"</body></html>"
    )


def _runtime_active_project_state(request: Request, state: dict) -> dict:
    """Project active status and timeline from the bound Runtime workflow run."""
    project = state.get("project") if isinstance(state.get("project"), dict) else {}
    run_id = str(project.get("run_id") or state.get("run_id") or "")
    if not run_id:
        return state
    try:
        store = getattr(
            request.app.state, "runtime_run_store", request.app.state.v12_run_store
        )
        run = store.get_run(run_id)
        definition = store.get_definition(run_id)
        attempts = store.get_step_attempts(run_id)
    except (AttributeError, KeyError, ValueError):
        return state
    latest_attempts = {attempt.step_id: attempt for attempt in attempts}
    projected = dict(state)
    projected["active"] = {
        "stage": run.current_step,
        "status": run.status,
        "run_id": run.run_id,
        "stage_id": f"stage:{run.run_id}:{run.current_step}",
        "owner": "Runtime",
    }
    projected["timeline"] = [
        _runtime_timeline_node(run, step.step_id, latest_attempts.get(step.step_id))
        for step in definition.steps
    ]
    return projected


def _runtime_timeline_node(run, step_id: str, attempt) -> dict:
    """Project one declared stage from persisted Runtime run and attempt facts."""
    stage_id = f"stage:{run.run_id}:{step_id}"
    if attempt is not None:
        return {
            "stage": step_id,
            "stage_id": stage_id,
            "attempt_id": attempt.attempt_id,
            "status": attempt.status,
            "display_state": "completed"
            if attempt.status == "completed"
            else "attention",
        }
    if step_id == run.current_step:
        return {
            "stage": step_id,
            "stage_id": stage_id,
            "attempt_id": None,
            "status": run.status,
            "display_state": "active",
        }
    return {
        "stage": step_id,
        "stage_id": stage_id,
        "attempt_id": None,
        "status": "pending",
        "display_state": "pending",
    }


def _projects_toolbar() -> str:
    """Render the toolbar with ``projects`` as the current activity."""
    buttons = []
    for key, label, icon in TOOLBAR_ITEMS:
        current = ' aria-current="page"' if key == "projects" else ""
        buttons.append(
            f'<button type="button" data-testid="toolbar-{key}" '
            f'data-activity="{key}" aria-label="{label}" title="{label}"{current}>'
            f'<span aria-hidden="true">{icon}</span></button>'
        )
    return '<div class="toolbar-brand" aria-label="Louke">L</div>' + "".join(buttons)


def _projects_sidebar() -> str:
    """IF-GUIDE-01: Render the Projects sidebar with the Guide session.

    Shows the Guide context, a message list (empty until Runtime or Guide
    appends), and a composer for human chat.  The composer never carries
    Runtime action capability (IF-GUIDE-01 §User chat).
    """
    return (
        "<strong>Guide</strong>"
        '<div data-testid="guide-context" data-context-kind="empty">'
        '<p class="guide-lede">Contextual guidance for your Projects workspace.</p>'
        "</div>"
        '<div data-testid="guide-messages" class="guide-messages" aria-live="polite">'
        '<div class="guide-msg" data-authority="guide">'
        "Welcome. Use <strong>New Project</strong> to create a release, "
        "or check the Environment Wizard for setup guidance."
        "</div></div>"
        '<form class="guide-composer" data-testid="guide-composer">'
        '<textarea name="guide_message" placeholder="Ask the Guide…"'
        ' rows="2" aria-label="Guide message"></textarea>'
        '<button type="submit">Send</button>'
        "</form>"
    )


def _projects_new_project_wizard(request: Request | None = None) -> str:
    """IF-ENV-01 + IF-DRAFT-01: Render the New Project wizard with Story form.

    Shows terminal Environment readiness steps and a Story/version input form.
    The browser obtains current readiness from the authenticated read-only API.
    """
    csrf_token = ""
    env_passed = False
    draft_key = "louke.new-project.v1:unknown:anonymous"
    if request is not None:
        from ..auth import SESSION_COOKIE, current_user
        from ..csrf_middleware import issue_for_session

        csrf_token = issue_for_session(
            session_id=request.cookies.get(SESSION_COOKIE, "preauth")
        )
        try:
            user = current_user(
                request.app.state.store,
                request.cookies.get(SESSION_COOKIE),
            )
            principal_id = getattr(user, "username", None) or "anonymous"
            workspace_id = getattr(request.app.state, "workspace_id", "unknown")
            draft_key = f"louke.new-project.v1:{workspace_id}:{principal_id}"
        except (KeyError, AttributeError, OSError, TypeError, ValueError):
            pass

    step_labels = (
        ("gh_executable", "GitHub CLI executable"),
        ("gh_auth_scopes", "GitHub auth & scopes"),
        ("repository_binding", "Repository binding"),
        ("canonical_main", "Canonical main branch"),
    )
    env_check = {
        "state": "blocked",
        "steps": [
            {
                "id": step_id,
                "state": "blocked",
                "missing": ["readiness check has not run"],
                "diagnosis": None,
            }
            for step_id, _ in step_labels
        ],
    }
    step_items = []
    for step_def, (sid, label) in zip(env_check["steps"], step_labels):
        state_cls = step_def["state"]
        state_txt = step_def["state"]
        if step_def["missing"] and sid == "gh_auth_scopes":
            state_txt = f"failed (missing: {', '.join(step_def['missing'])})"
        elif step_def["missing"]:
            state_txt = f"failed ({', '.join(step_def['missing'])})"
        step_items.append(
            f'<li data-testid="env-step-{sid}" data-step-id="{sid}" '
            f'data-state="{state_cls}">'
            f'<span class="env-step-label">{label}</span>'
            f'<span class="env-step-state">{state_txt}</span>'
            f"</li>"
        )

    diagnosis_html = _environment_diagnosis_html(env_check)
    env_html = (
        '<section data-testid="env-wizard" aria-label="Environment Wizard">'
        "<h2>Environment check</h2>"
        f'<ol data-testid="env-steps" role="list">{"".join(step_items)}</ol>'
        + diagnosis_html
        + '<div class="projects-actions">'
        + '<button type="button" data-testid="env-retry">Retry</button>'
        + '<button type="button" data-testid="env-cancel">Cancel</button>'
        + "</div></section>"
    )

    # AC-FR0601-02: disable Story input, Preview and Create until the
    # environment gate passes. The server-side /api/projects/preview and
    # /api/projects/confirm also enforce this fail-closed, so the UI
    # disabled state is defense-in-depth, not the sole authority.
    gate_attr = f' data-env-passed="{"true" if env_passed else "false"}"'
    input_disabled = "" if env_passed else " disabled"

    wizard = (
        '<div class="projects-card" data-projects-state="new_project"' + gate_attr + ">"
        "<h1>New Project</h1>"
        + env_html
        + '<form name="new_project_story" data-testid="new-project-story" '
        + f'data-csrf="{escape(csrf_token, quote=True)}" '
        + ">"
        '<label class="setup-field">Story'
        '<textarea name="story" rows="4" placeholder="Describe the release story…"'
        f' aria-label="Story" required{input_disabled}></textarea></label>'
        '<label class="setup-field">Release version'
        '<input name="release_version" type="text" placeholder="0.14.0"'
        f' aria-label="Release version" required{input_disabled}></label>'
        '<div class="projects-actions">'
        f'<button type="submit" data-testid="preview"{input_disabled}>Preview</button>'
        '<button type="button" data-testid="cancel">Cancel</button>'
        "</div></form>"
        '<section data-testid="project-preview" hidden aria-live="polite">'
        "<h2>Preview</h2>"
        '<p data-testid="preview-story"></p>'
        '<p>Release: <strong data-testid="preview-version"></strong></p>'
        '<p>Workspace: <strong data-testid="preview-workspace"></strong></p>'
        '<p>Repository: <strong data-testid="preview-repository"></strong></p>'
        '<p data-testid="preview-error" role="alert" hidden></p>'
        '<div class="projects-actions">'
        '<button type="button" data-testid="create-project" disabled>Create</button>'
        '<button type="button" data-testid="preview-cancel">Cancel</button>'
        "</div></section></div>"
    )
    return wizard + _new_project_script(csrf_token, draft_key)


def _environment_diagnosis_html(environment: dict) -> str:
    """Render the first persisted blocking diagnosis for the Environment Wizard.

    Args:
        environment: Evaluated Environment Check projection.

    Returns:
        Escaped visible diagnosis markup, or a hidden empty diagnosis region
        when every step has no actionable persisted diagnosis.

    Side Effects:
        None.
    """
    for step in environment.get("steps", []):
        if not isinstance(step, dict) or step.get("state") not in {
            "failed",
            "uncertain",
        }:
            continue
        diagnosis = step.get("diagnosis")
        if not isinstance(diagnosis, dict):
            continue
        impact = diagnosis.get("impact")
        if not impact:
            continue
        object_name = escape(str(diagnosis.get("object") or "Environment check"))
        return (
            '<div data-testid="env-diagnosis" role="alert">'
            f"<strong>{object_name}</strong>"
            f"<p>{escape(str(impact))}</p>"
            "</div>"
        )
    return '<div data-testid="env-diagnosis" hidden></div>'


def _new_project_script(csrf_token: str, draft_key: str = "") -> str:
    """Return browser behavior for canonical Preview, Confirm and status readback.

    Args:
        csrf_token: Session-bound CSRF token rendered as a JS literal so the
            browser and integration tests share the same extraction contract.
        draft_key: Workspace/principal-bound browser draft key.

    Returns:
        A script that drives the version-agnostic Project APIs and opens the
        resulting canonical Story in Workbench Dev Docs.

    Side Effects:
        The generated browser code performs authenticated HTTP mutations only
        after the Human selects Create.
    """
    token = escape(csrf_token, quote=True)
    safe_draft_key = json.dumps(draft_key or "louke.new-project.v1:unknown:anonymous")
    template = """<script>
(function() {
  const csrf = "__CSRF_TOKEN__";
  const form = document.querySelector('form[name="new_project_story"]');
  const previewPanel = document.querySelector('[data-testid="project-preview"]');
  const error = document.querySelector('[data-testid="preview-error"]');
  const create = document.querySelector('[data-testid="create-project"]');
  const retry = document.querySelector('[data-testid="env-retry"]');
  const diagnosis = document.querySelector('[data-testid="env-diagnosis"]');
  const headers = {'Content-Type': 'application/json', 'X-Louke-CSRF': csrf};
  const draftKey = __DRAFT_KEY__;
  let preview = null;
  // AC-FR1101-02: one logical idempotency key preserved across Confirm
  // retry/readback so repeated/subsequent Confirm calls for the same
  // preview reuse the same key rather than minting a new UUID each time.
  let storedIdempotencyKey = null;
  let previewIdempotencyKey = null;
  function getIdempotencyKey() {
    if (!storedIdempotencyKey) {
      storedIdempotencyKey = window.crypto && window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : 'project-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    }
    return storedIdempotencyKey;
  }
  function getPreviewIdempotencyKey() {
    if (!previewIdempotencyKey) previewIdempotencyKey = 'preview-' + getIdempotencyKey();
    return previewIdempotencyKey;
  }
  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }
  function showEnvironmentError(message) {
    diagnosis.textContent = message;
    diagnosis.hidden = false;
  }
  function updateEnvironment(check) {
    document.querySelectorAll('[data-step-id]').forEach(function(item) {
      const step = (check.steps || []).find(function(candidate) {
        return candidate.id === item.dataset.stepId;
      });
      if (!step) return;
      item.dataset.state = step.state;
      const state = item.querySelector('.env-step-state');
      if (state) {
        state.textContent = step.missing && step.missing.length
          ? step.state + ' (' + step.missing.join(', ') + ')' : step.state;
      }
    });
    const enabled = check.state === 'passed' && check.story_input_enabled;
    const card = document.querySelector('[data-projects-state="new_project"]');
    if (card) card.dataset.envPassed = enabled ? 'true' : 'false';
    form.querySelectorAll('textarea, input, [data-testid="preview"]').forEach(function(control) {
      control.disabled = !enabled;
    });
    if (!enabled) create.disabled = true;
    if (enabled) diagnosis.hidden = true;
  }
  function restoreDraft() {
    try {
      const draft = JSON.parse(window.localStorage.getItem(draftKey) || '{}');
      if (typeof draft.story === 'string') form.story.value = draft.story;
      if (typeof draft.release_version === 'string') form.release_version.value = draft.release_version;
    } catch (_) { /* Browser storage is optional. */ }
  }
  function saveDraft() {
    try {
      window.localStorage.setItem(draftKey, JSON.stringify({
        story: form.story.value, release_version: form.release_version.value,
        resume_step: 'input', saved_at: new Date().toISOString()
      }));
    } catch (_) { /* Blocked storage must not block the wizard. */ }
  }
  async function startEnvironmentCheck() {
    const response = await fetch('/api/projects/environment-checks', {
      method: 'POST', headers: headers
    });
    const body = await response.json();
    if (!response.ok) { showEnvironmentError(body.message || 'Environment check failed'); return; }
    updateEnvironment(body);
  }
  async function retryEnvironmentCheck() {
    retry.disabled = true;
    try {
      await startEnvironmentCheck();
    } finally {
      retry.disabled = false;
    }
  }
  restoreDraft();
  form.story.addEventListener('input', saveDraft);
  form.release_version.addEventListener('input', saveDraft);
  retry.addEventListener('click', retryEnvironmentCheck);
  startEnvironmentCheck().catch(function() {
    showEnvironmentError('Environment check could not be completed');
  });
  form.addEventListener('submit', async function(event) {
    event.preventDefault();
    error.hidden = true;
    const response = await fetch('/api/projects/preview', {
      method: 'POST', headers: Object.assign({}, headers,
        {'Idempotency-Key': getPreviewIdempotencyKey()}),
      body: JSON.stringify({story: form.story.value,
        release_version: form.release_version.value})
    });
    const body = await response.json();
    if (!response.ok) { showError(body.message || 'Preview failed'); return; }
    preview = body;
    try {
      window.localStorage.setItem(draftKey, JSON.stringify({
        story: form.story.value, release_version: form.release_version.value,
        resume_step: 'preview', saved_at: new Date().toISOString()
      }));
    } catch (_) { /* Blocked storage must not block Preview. */ }
    document.querySelector('[data-testid="preview-story"]').textContent = body.story;
    document.querySelector('[data-testid="preview-version"]').textContent = body.release.canonical;
    document.querySelector('[data-testid="preview-workspace"]').textContent =
      body.workspace && body.workspace.workspace_id || body.workspace_id || '';
    const repository = body.repository || {};
    document.querySelector('[data-testid="preview-repository"]').textContent =
      repository.display_url || [repository.owner, repository.name].filter(Boolean).join('/') || '';
    create.disabled = false;
    form.hidden = true;
    previewPanel.hidden = false;
    create.focus();
  });
  create.addEventListener('click', async function() {
    if (!preview) return;
    create.disabled = true;
    const idemKey = getIdempotencyKey();
    const response = await fetch('/api/projects/confirm', {
      method: 'POST', headers: Object.assign({}, headers,
        {'Idempotency-Key': idemKey}),
      body: JSON.stringify({preview_id: preview.preview_id,
        expected_preview_revision: preview.preview_revision,
        request_digest: preview.request_digest})
    });
    const body = await response.json();
    if (!response.ok) { showError(body.message || 'Create failed'); create.disabled = false; return; }
    completeCreation(body);
  });
  function completeCreation(body) {
    if (body.status === 'ready') {
      const revision = body.story && body.story.revision ? body.story.revision : 1;
      try { window.sessionStorage.setItem('louke.pending-draft-clear', draftKey); } catch (_) { /* optional */ }
      window.location.assign('/workbench?activity=dev-docs&project=' +
        encodeURIComponent(body.project_id) + '&document=story&revision=' + revision);
      return;
    }
    showError('Project creation ' + body.status);
    create.disabled = false;
  }
  document.querySelector('[data-testid="cancel"]').addEventListener('click', function() {
    window.location.assign('/workbench?activity=projects');
  });
  document.querySelector('[data-testid="env-cancel"]').addEventListener('click', function() {
    window.location.assign('/workbench?activity=projects');
  });
  document.querySelector('[data-testid="preview-cancel"]').addEventListener('click', function() {
    previewPanel.hidden = true; form.hidden = false; form.querySelector('textarea').focus();
  });
})();
</script>"""
    return template.replace("__CSRF_TOKEN__", token).replace(
        "__DRAFT_KEY__", safe_draft_key
    )


def _projects_main_panel_active(state: dict) -> str:
    """IF-PROJECT-01 + IF-STATUS-01: Render the active Project Status cockpit.

    Reads ``active``, ``timeline`` and ``project_id`` from the persisted
    project state and renders a data-driven cockpit.
    """
    project_id = state.get("project_id", "")
    active = state.get("active", {})
    timeline = state.get("timeline", [])
    pid = escape(str(project_id)) if project_id else "current"

    # Active card
    owner = escape(str(active.get("owner", "Runtime")))
    ordinal = active.get("attempt_ordinal", "")
    elapsed = active.get("elapsed_seconds", "")
    active_stage = escape(str(active.get("stage", "")))
    run_id = escape(str(active.get("run_id", "")))
    ordinal_html = f"<span>Attempt #{ordinal}</span>" if ordinal else ""
    elapsed_html = f"<span>{elapsed}s elapsed</span>" if elapsed else ""

    # Timeline nodes
    node_items = []
    for node in timeline:
        att_id = escape(str(node.get("attempt_id") or ""))
        stage_id = escape(str(node.get("stage_id", "")))
        stage = escape(str(node.get("stage", "")))
        status = escape(str(node.get("status", "")))
        display_state = escape(str(node.get("display_state", "")))
        ret = node.get("return_eligibility", {})
        allowed = ret.get("allowed", False) if isinstance(ret, dict) else False
        return_btn = (
            f'<button type="button" data-action="return" '
            f'data-attempt-id="{att_id}">Return</button>'
            if allowed
            else ""
        )
        node_items.append(
            f'<li data-attempt-id="{att_id}" data-stage-id="{stage_id}" '
            f'data-stage="{stage}" data-status="{status}" '
            f'data-display-state="{display_state}" '
            f'tabindex="0" role="listitem">'
            f"<span>{stage}</span><span>{status}</span><span>{att_id}</span>{return_btn}</li>"
        )

    # A missing Runtime projection is displayed as one unknown stage rather
    # than inventing a synthetic lifecycle.
    if not node_items:
        node_items = [
            '<li data-stage="unknown" tabindex="0" role="listitem">unknown</li>'
        ]

    timeline_html = "".join(node_items)

    return (
        f'<div class="projects-card" data-projects-state="active">'
        f"<h1>Project Status</h1>"
        f'<section data-testid="status-cockpit" data-project-id="{pid}">'
        # Active card
        f'<article data-testid="active-card" data-display-state="active" '
        f'data-run-id="{run_id}">'
        f"<h2>Active: {active_stage}</h2>"
        f'<p data-testid="active-owner">Owner: {owner}</p>'
        f'<p data-testid="active-run">Run: {run_id}</p>'
        f"<p>{ordinal_html} {elapsed_html}</p>"
        f"</article>"
        # Timeline
        f'<ol data-testid="stage-timeline" role="list" '
        f'aria-label="Workflow stages (Home/End/Arrow keys to navigate)">'
        f"{timeline_html}</ol>"
        # Return edges
        f'<section data-testid="return-edges" aria-label="Return edges">'
        f"<h3>Return edges</h3></section>"
        # Keyboard hint
        f'<p class="status-hint" data-testid="keyboard-hint">'
        f"Keyboard: Home / End / ← / → to navigate full stage history.</p>"
        f"</section></div>"
    )


def _projects_main_panel(state: str) -> str:
    """IF-PROJECT-01: Render the Projects main panel for the given state.

    Args:
        state: One of ``empty``, ``active``, or ``conflict``.

    - ``empty``: purpose hint + ``New Project`` button (enabled).
    - ``active``: Project Status cockpit (IF-STATUS-01).
    - ``conflict``: each conflicting identity; ``New Project`` disabled.
    """
    if state == "active":
        return (
            '<div class="projects-card" data-projects-state="active">'
            "<h1>Project Status</h1>"
            '<div data-testid="status-cockpit">'
            + _projects_status_cockpit("")
            + "</div></div>"
        )

    if state == "conflict":
        return (
            '<div class="projects-card" data-projects-state="conflict">'
            "<h1>Project conflict</h1>"
            '<p class="projects-lede">Multiple active Project bindings were found. '
            "Resolve the conflict before creating a new Project.</p>"
            '<div class="conflict-list" data-testid="conflict-list">'
            '<div class="conflict-item">Conflicting binding detected</div>'
            "</div>"
            '<div class="projects-actions">'
            '<button type="button" data-testid="new-project" disabled>New Project</button>'
            "</div></div>"
        )

    # empty (default)
    return (
        '<div class="projects-card" data-projects-state="empty">'
        "<h1>Projects</h1>"
        '<p class="projects-lede">No active Project in this workspace. '
        "Create one to start a release workflow.</p>"
        '<div class="projects-actions">'
        '<button type="button" data-testid="new-project" '
        "onclick=\"window.location.href='/workbench?activity=projects&action=new_project'\">"
        "New Project</button>"
        "</div></div>"
    )


def _projects_status_cockpit(project_id: str) -> str:
    """IF-STATUS-01: Render the Project Status cockpit for the given project.

    Shows the 13 canonical stages in locked order, an active attempt card,
    return edges, and keyboard navigation hints for full history.
    """
    stages = (
        "M-START",
        "M-STORY",
        "M-SPEC",
        "M-ACC",
        "M-REQ-APPROVAL",
        "M-DESIGN",
        "M-IMPL",
        "M-TEST",
        "M-VERIFY",
        "M-SECURITY",
        "M-RELEASE",
        "M-PUBLISH",
        "M-MILESTONE",
    )
    stage_items = "".join(
        f'<li data-testid="stage-{s}" data-stage-id="{s}" '
        f'tabindex="0" role="listitem">{s}</li>'
        for s in stages
    )
    pid = escape(project_id) if project_id else "current"
    return (
        f'<section data-testid="project-status" data-project-id="{pid}" '
        f'aria-label="Project Status cockpit">'
        f"<h2>Project Status — {pid}</h2>"
        # 13-stage timeline
        f'<ol data-testid="stage-timeline" role="list" '
        f'aria-label="Workflow stages (Home/End/Arrow keys to navigate)">'
        f"{stage_items}</ol>"
        # Active card
        '<article data-testid="active-card" data-display-state="active">'
        "<h3>Active attempt</h3>"
        '<p data-testid="active-owner">Owner: Runtime</p>'
        '<p data-testid="active-elapsed">Elapsed: —</p>'
        '<div data-testid="active-action">'
        '<button type="button" disabled>Runtime primary action</button>'
        "</div></article>"
        # Return edges
        '<section data-testid="return-edges" aria-label="Return edges">'
        "<h3>Return edges</h3>"
        '<p data-testid="return-edge-empty">No return edges recorded.</p>'
        "</section>"
        # Keyboard navigation hint
        '<p class="status-hint" data-testid="keyboard-hint">'
        "Keyboard: Home / End / ← / → to navigate full stage history."
        "</p>"
        "</section>"
    )


def _projects_env_wizard() -> str:
    """IF-ENV-01: Render the Environment Wizard modal.

    Covers the four required checks in fixed order and exposes a Retry
    entry for blocking steps.
    """
    steps = (
        ("gh_executable", "GitHub CLI executable"),
        ("gh_auth_scopes", "GitHub auth & scopes"),
        ("repository_binding", "Repository binding"),
        ("canonical_main", "Canonical main branch"),
    )
    step_items = "".join(
        f'<li data-testid="env-step-{sid}" data-step-id="{sid}" '
        f'data-state="pending">'
        f'<span class="env-step-label">{label}</span>'
        f'<span class="env-step-state">pending</span>'
        f"</li>"
        for sid, label in steps
    )
    return (
        '<section data-testid="env-wizard" aria-label="Environment Wizard">'
        "<h2>Environment check</h2>"
        f'<ol data-testid="env-steps" role="list">{step_items}</ol>'
        '<div data-testid="env-diagnosis" hidden></div>'
        '<div class="projects-actions">'
        '<button type="button" data-testid="env-retry">Retry</button>'
        '<button type="button" data-testid="env-cancel">Cancel</button>'
        "</div></section>"
    )


# ---------------------------------------------------------------------------
# IF-COMPAT-01: compatibility route stubs
# ---------------------------------------------------------------------------


async def projects_compat(request: Request) -> HTMLResponse:
    """IF-COMPAT-01: ``/projects`` → 303 redirect to ``/workbench?activity=projects``."""
    from starlette.responses import RedirectResponse as _Redirect

    return _Redirect(url="/workbench?activity=projects", status_code=303)


async def projects_new_compat(request: Request) -> HTMLResponse:
    """IF-COMPAT-01: ``/projects/new`` → Workbench with New Project wizard."""
    from starlette.responses import RedirectResponse as _Redirect

    return _Redirect(
        url="/workbench?activity=projects&action=new_project", status_code=303
    )


async def project_detail_compat(request: Request) -> HTMLResponse:
    """Resolve ``/projects/{project_id}`` to that exact Project Status.

    Args:
        request: Request carrying the legacy Project path identity.

    Returns:
        A 303 canonical redirect for a known Project, or a locatable 404 when
        no persisted binding safely maps the requested identity.

    Side Effects:
        None.
    """
    from starlette.responses import RedirectResponse as _Redirect

    project_id = request.path_params.get("project_id", "")
    try:
        state = _read_project_state(request)
    except (KeyError, AttributeError):
        return _Redirect(
            url=f"/workbench?activity=projects&project={project_id}",
            status_code=303,
        )
    known_ids = _project_ids_from_state(state)
    service = getattr(request.app.state, "release_entry", None)
    if service is not None and service.current_project(project_id) is not None:
        known_ids.add(project_id)
    if project_id not in known_ids:
        return _identity_not_found("Project", project_id)
    return _Redirect(
        url=f"/workbench?activity=projects&project={project_id}",
        status_code=303,
    )


def _project_ids_from_state(state: dict) -> set[str]:
    """Return explicit Project identities represented by persisted UI state.

    Args:
        state: Parsed ``project-state.json`` object.

    Returns:
        Non-empty Project ids from active, nested and conflict entries.
    """
    identities: set[str] = set()
    direct = state.get("project_id")
    if isinstance(direct, str) and direct:
        identities.add(direct)
    nested = state.get("project")
    if isinstance(nested, dict):
        nested_id = nested.get("project_id")
        if isinstance(nested_id, str) and nested_id:
            identities.add(nested_id)
    conflicts = state.get("conflicts", [])
    if isinstance(conflicts, list):
        for conflict in conflicts:
            if isinstance(conflict, dict):
                conflict_id = conflict.get("project_id")
                if isinstance(conflict_id, str) and conflict_id:
                    identities.add(conflict_id)
    return identities


def _identity_not_found(resource: str, identity: str) -> HTMLResponse:
    """Return a safely escaped, locatable missing-identity result.

    Args:
        resource: Human-readable resource kind.
        identity: Untrusted identity supplied by the route.

    Returns:
        HTTP 404 HTML with recovery back to Projects.
    """
    safe_resource = escape(resource)
    safe_identity = escape(identity)
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Louke — {safe_resource} not found</title>"
        f"<style>{_PROJECTS_STYLES}</style></head><body>"
        '<main class="projects-card">'
        f"<h1>{safe_resource} not found</h1>"
        f"<p>The requested {safe_resource.lower()} <code>{safe_identity}</code> "
        "has no safe workspace binding. It may require migration.</p>"
        '<p><a href="/workbench?activity=projects">Back to Projects</a></p>'
        "</main></body></html>",
        status_code=404,
    )


async def run_detail_compat(request: Request) -> HTMLResponse:
    """IF-COMPAT-01: ``/runs/{run_id}`` → Project Status for the run's project.

    Reads the run→project binding from ``project-state.json`` and redirects
    to the canonical Projects activity with the bound project id.
    """
    import json as _json

    from starlette.responses import RedirectResponse as _Redirect

    run_id = request.path_params.get("run_id", "")
    try:
        workspace_root = Path(request.app.state.workspace_root)
    except (KeyError, AttributeError):
        # No app context (unit test): redirect to bare Projects activity.
        return _Redirect(url="/workbench?activity=projects", status_code=303)
    state_path = workspace_root / ".louke" / "project-state.json"
    project_id = ""
    if state_path.is_file():
        try:
            ps = _json.loads(state_path.read_text(encoding="utf-8"))
            runs = ps.get("runs", {})
            project_id = runs.get(run_id, "")
        except (OSError, _json.JSONDecodeError):
            pass
    if project_id:
        return _Redirect(
            url=f"/workbench?activity=projects&project={project_id}",
            status_code=303,
        )
    # Unknown run: show a not-found / migration-required page.
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Louke — Run not found</title>"
        f"<style>{_PROJECTS_STYLES}</style></head><body>"
        '<div class="projects-card">'
        "<h1>Run not found</h1>"
        f"<p>The run <code>{escape(run_id)}</code> could not be mapped to a "
        "Project. It may require migration or is read-only historical data.</p>"
        '<p><a href="/workbench?activity=projects">Back to Projects</a></p>'
        "</div></body></html>",
        status_code=404,
    )
