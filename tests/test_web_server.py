from __future__ import annotations

import inspect
import json
import re
import shutil
import sys
from pathlib import Path

from starlette.testclient import TestClient

from louke.serve import _resolve_project_root
from louke.web.auth import SESSION_COOKIE
from louke.web.app import create_app


def build_project(tmp_path: Path) -> Path:
    root = tmp_path
    (root / ".louke" / "project" / "specs" / "demo").mkdir(parents=True)
    (root / ".louke" / "wiki" / "pages").mkdir(parents=True)
    (root / ".louke" / "wiki" / "pages" / "guides").mkdir(parents=True)
    (root / ".louke" / "project" / "project.toml").write_text(
        """
[project]
version = "0.8"
repo = "github.com/example/louke"
project = "louke-v0.8"
project_id = "https://example.com/project/8"
spec_id = "demo"
release_branch = "releases/v0.8"

[meta]
created = "2026-07-08"
tag = "v0.7.3"
current_stage = "M-ARCH"
security_audit = "disabled"
smoke_test_issue = "#80"
smoke_test_pr = "#81"
dod = "done"
pre_commit = "installed"
test_framework = "pytest"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / ".louke" / "project" / "specs" / "demo" / "spec.md").write_text(
        """
# Demo Spec

## 3. 功能需求

### FR-0100 Demo requirement

| Valid | Testable | Decided |
| ----- | -------- | ------- |
| ✅     | ✅        | ✅       |

支持代码块、表格和列表。

```python
print("hello")
```
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / ".louke" / "project" / "specs" / "demo" / "acceptance.md").write_text(
        "## FR-0100 Demo requirement\n\n### AC-1\n- Works.\n",
        encoding="utf-8",
    )
    (root / ".louke" / "project" / "specs" / "demo" / "test-plan.md").write_text(
        "## Plan\n\n- test\n",
        encoding="utf-8",
    )
    (root / ".louke" / "wiki" / "pages" / "overview.md").write_text(
        "# Overview\n\n- first item\n- second item\n",
        encoding="utf-8",
    )
    (root / ".louke" / "wiki" / "pages" / "guides" / "getting-started.md").write_text(
        "# Getting Started\n\n- nested page\n",
        encoding="utf-8",
    )
    (root / ".louke" / "models.json").write_text(
        json.dumps(
            {
                "$schema": "louke://models-config",
                "version": 1,
                "aliases": {"minimax-m3": "ark/minimax-m3"},
                "assignments": {"roles": {"A": "minimax-m3"}, "agents": {}},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return root


def authenticate(
    client: TestClient, username: str = "Aaron", password: str = "secret"
) -> None:
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200


def test_health_and_home_page(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "spec_id": "demo"}
    login = client.get("/login")
    assert login.status_code == 200
    assert "Min Square_97" in login.text
    assert "/assets/min-square_97-snk-X32c8tE-unsplash.jpg" in login.text
    assert "Beyond Vibes, Into Craft" in login.text
    assert "超越氛围编程" in login.text
    # No Accept-Language header -> fall back to English
    assert "Sign In" in login.text
    assert "登录" not in login.text
    asset = client.get("/assets/min-square_97-snk-X32c8tE-unsplash.jpg")
    assert asset.status_code == 200
    guest = client.get("/", follow_redirects=False)
    # Unauthenticated visitors always start at Login.
    assert guest.status_code == 303
    assert guest.headers["location"].startswith("/login")
    guest_chrome = client.get("/")
    assert guest_chrome.status_code == 200
    assert 'id="tab-register"' in guest_chrome.text
    legacy_guest = client.get("/?legacy=1", follow_redirects=False)
    assert legacy_guest.status_code == 303
    assert legacy_guest.headers["location"].startswith("/login")
    authenticate(client)
    home = client.get("/")
    assert home.status_code == 200
    assert 'data-testid="workbench-toolbar"' in home.text

    home_en = client.get("/", headers={"accept-language": "en-US,en;q=0.9"})
    assert home_en.status_code == 200
    assert 'data-testid="workbench-toolbar"' in home_en.text

    login_en = TestClient(create_app(root)).get(
        "/login", headers={"accept-language": "en-US,en;q=0.9"}
    )
    assert login_en.status_code == 200
    assert "Sign In" in login_en.text
    assert "Register &amp; Sign In" in login_en.text

    # Explicit Chinese
    home_zh = client.get("/", headers={"accept-language": "zh-CN,zh;q=0.9"})
    assert home_zh.status_code == 200
    assert 'data-testid="workbench-toolbar"' in home_zh.text

    login_zh = TestClient(create_app(root)).get(
        "/login", headers={"accept-language": "zh-CN,zh;q=0.9"}
    )
    assert login_zh.status_code == 200
    assert "登录" in login_zh.text
    assert "注册并登录" in login_zh.text

    # Unsupported language (French) -> fall back to English
    home_fr = client.get("/", headers={"accept-language": "fr-FR,fr;q=0.9"})
    assert home_fr.status_code == 200
    assert 'data-testid="workbench-toolbar"' in home_fr.text


def test_register_login_logout_flow(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))

    register = client.post(
        "/api/auth/register", json={"username": "Aaron", "password": "secret"}
    )
    assert register.status_code == 200
    assert register.json()["username"] == "Aaron"
    assert SESSION_COOKIE in register.cookies

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    denied = client.get("/api/bindings")
    assert denied.status_code == 401

    login = client.post(
        "/api/auth/login", json={"username": "Aaron", "password": "secret"}
    )
    assert login.status_code == 200
    assert login.json()["username"] == "Aaron"

    models = client.get("/api/bindings")
    assert models.status_code == 200


def test_doc_roundtrip_and_conflict(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    authenticate(client)

    response = client.get("/api/docs/demo/spec")
    assert response.status_code == 200
    payload = response.json()
    assert "<table>" in payload["rendered_html"]
    assert payload["cards"][0]["id"] == "FR-0100"

    saved = client.put(
        "/api/docs/demo/spec",
        json={
            "body_md": payload["body_md"] + "\nNew line.\n",
            "version_token": payload["version_token"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["last_modified_by"] == "Aaron"
    assert "New line." in (
        root / ".louke" / "project" / "specs" / "demo" / "spec.md"
    ).read_text(encoding="utf-8")

    stale = client.put(
        "/api/docs/demo/spec",
        json={
            "body_md": "stale write\n",
            "version_token": payload["version_token"],
        },
    )
    assert stale.status_code == 409


def test_wiki_roundtrip(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    authenticate(client)

    response = client.get("/api/wiki/overview", headers={"Accept": "application/json"})
    assert response.status_code == 200
    payload = response.json()
    assert "<ul>" in payload["rendered_html"]

    saved = client.put(
        "/api/wiki/overview",
        json={
            "body_md": payload["body_md"] + "\n## Extra\n\nText\n",
            "version_token": payload["version_token"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["last_modified_by"] == "Aaron"

    nested = client.get(
        "/api/wiki/guides/getting-started", headers={"Accept": "application/json"}
    )
    assert nested.status_code == 200
    assert nested.json()["page"] == "guides/getting-started"

    page = client.get("/wiki/guides/getting-started")
    assert page.status_code == 200
    assert "guides" in page.text
    assert "getting-started" in page.text


def test_bindings_get_and_put(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    authenticate(client)

    response = client.get("/api/bindings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved"]["roles"]["A"]["abstract"] == "minimax-m3"
    assert "Sage" in payload["resolved"]["agents"]

    saved = client.put(
        "/api/bindings",
        json={
            "version_token": payload["version_token"],
            "aliases": payload["aliases"],
            "assignments": {
                "roles": {"A": "minimax-m3", "B": "deepseek-v4-flash"},
                "agents": {"Sage": "glm-5.2"},
            },
        },
    )
    assert saved.status_code == 200
    data = json.loads((root / ".louke" / "models.json").read_text(encoding="utf-8"))
    assert data["assignments"]["roles"]["B"] == "deepseek-v4-flash"
    assert data["assignments"]["agents"]["Sage"] == "glm-5.2"


def test_discussion_mutation_writes_markdown(tmp_path: Path) -> None:
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    authenticate(client)

    doc = client.get("/api/docs/demo/spec").json()
    created = client.post(
        "/api/discussions/mutate",
        json={
            "target_kind": "doc",
            "target_path": doc["path"],
            "version_token": doc["version_token"],
            "action": "start",
            "anchor": {"anchor_line": 8},
            "payload": {"body": "需要补充降级策略"},
        },
    )
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["discussion_threads"]
    content = (root / ".louke" / "project" / "specs" / "demo" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert "> **Aaron:** 需要补充降级策略" in content

    thread = created_payload["discussion_threads"][0]
    client.post("/api/auth/logout")
    register_bob = client.post(
        "/api/auth/register", json={"username": "Bob", "password": "hunter2"}
    )
    assert register_bob.status_code == 200
    replied = client.post(
        "/api/discussions/mutate",
        json={
            "target_kind": "doc",
            "target_path": created_payload["path"],
            "version_token": created_payload["version_token"],
            "action": "reply",
            "anchor": {"anchor_line": thread["anchor_line"]},
            "payload": {
                "thread_id": thread["thread_id"],
                "body": "已收到",
                "anchor_line": thread["anchor_line"],
                "anchor_text": thread["anchor_text"],
                "root_line": thread["root_line"],
                "root_text": thread["root_text"],
            },
        },
    )
    assert replied.status_code == 200
    content = (root / ".louke" / "project" / "specs" / "demo" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert ">> **Bob:** 已收到" in content


def test_resolve_project_root_searches_upward(tmp_path: Path, monkeypatch) -> None:
    root = build_project(tmp_path)
    nested = root / "sub" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert _resolve_project_root("") == root.resolve()


def test_scan_discussion_blocks_detects_resolved_markers() -> None:
    """Verify the discussion scanner finds both open and resolved discussion lines.

    The JS filter/next-discussion buttons in the Vditor editor use the same
    matching rules as scan_discussion_blocks(). This test exercises the
    Python side so the logic is locked down: any regression here also breaks
    the browser filter.
    """
    from louke.web.render import scan_discussion_blocks

    sample = (
        "# v0.10 demo\n"
        "\n"
        "### FR-0100 Demo\n"
        "\n"
        "> [T-001] > **[Aaron]** First open comment\n"
        "> [T-001] >> **[Bob]** reply\n"
        "> [T-001] > status: open\n"
        "\n"
        "### FR-0200 Resolved demo\n"
        "\n"
        "> [T-002] > **[resolved] Aaron:** test\n"
        "> [T-002] > ✓ resolved\n"
        "> [T-002] > **[已决定] Lex:** done\n"
    )
    blocks = scan_discussion_blocks(sample)

    discussion_lines = [b for b in blocks if b["line"] > 0]
    assert len(discussion_lines) == 6, (
        f"expected 6 discussion lines, got {len(discussion_lines)}: {blocks}"
    )

    resolved = [b for b in blocks if b["resolved"]]
    open_blocks = [b for b in blocks if not b["resolved"]]

    # Lines containing resolved markers
    assert any("resolved] Aaron" in r["text"] for r in resolved)
    assert any("✓ resolved" in r["text"] for r in resolved)
    assert any("已决定" in r["text"] for r in resolved)

    # Open discussion lines
    assert any("First open comment" in o["text"] for o in open_blocks)
    assert any("reply" in o["text"] for o in open_blocks)
    assert any("status: open" in o["text"] for o in open_blocks)


def test_doc_page_renders_brand_and_spec_selector(tmp_path: Path) -> None:
    """Verify the sidebar shows Lòukè brand and a spec selector with all specs."""
    root = build_project(tmp_path)
    second = root / ".louke" / "project" / "specs" / "v0.10-001-vditor-redesign"
    second.mkdir(parents=True)
    (second / "spec.md").write_text("# v0.10\n", encoding="utf-8")
    (second / "acceptance.md").write_text("## v0.10\n", encoding="utf-8")

    client = TestClient(create_app(root))
    register = client.post(
        "/api/auth/register", json={"username": "Aaron", "password": "secret"}
    )
    assert register.status_code == 200

    doc = client.get("/docs/demo/spec")
    assert doc.status_code == 200
    body = doc.text
    # Brand should show Lòukè, not 'louke / web'
    assert "Lòukè" in body
    assert "louke / web" not in body
    # Spec selector should list both specs
    assert "v0.10-001-vditor-redesign" in body
    assert "demo" in body
    # Configured spec (demo) takes precedence over auto-select
    assert 'value="demo" selected' in body
    # And the v0.10 spec is present in the dropdown (even if not selected)
    assert '<option value="v0.10-001-vditor-redesign"' in body
    # Last Saved prefix on the time display
    assert "Last Saved:" in body
    # Save time placeholder
    assert "Last Saved: --:--:--" in body


def test_resolve_spec_id_picks_highest_version(tmp_path: Path) -> None:
    """resolve_spec_id() falls back to the highest-version spec when project.toml
    points to a missing directory, and respects the configured spec if present."""
    root = build_project(tmp_path)
    (root / ".louke" / "project" / "specs" / "v0.10-001-vditor-redesign").mkdir(
        parents=True
    )
    (root / ".louke" / "project" / "specs" / "v0.8-001-web-server").mkdir(parents=True)

    from louke.web.store import ProjectStore

    store = ProjectStore(root)

    # Configured spec ("demo") exists -> return it
    assert store.resolve_spec_id() == "demo"

    # Remove configured spec; should auto-pick the highest version
    import shutil

    shutil.rmtree(root / ".louke" / "project" / "specs" / "demo")
    assert store.resolve_spec_id() == "v0.10-001-vditor-redesign"


def test_doc_page_collapses_and_filters_discussions(tmp_path: Path) -> None:
    """Verify the collapse and filter CSS classes and the next-discussion
    handler are wired into the doc editor page."""
    root = build_project(tmp_path)
    spec_md = root / ".louke" / "project" / "specs" / "demo" / "spec.md"
    spec_md.write_text(
        "# Demo\n\n"
        "### FR-0100\n\n"
        "> [T-001] > **[Aaron]** open comment\n"
        "> [T-001] > **[resolved] Aaron:** resolved comment\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    doc = client.get("/docs/demo/spec")
    assert doc.status_code == 200
    body = doc.text
    # Filter/collapse CSS rules: hide [data-resolved] and [data-discussion]
    assert '[data-resolved="1"]' in body
    assert '[data-discussion="1"]' in body
    # nextDiscussion handler present
    assert "nextDiscussion" in body
    assert "isResolvedText" in body
    assert "isDiscussionText" in body
    # The spec.md content is loaded into Vditor via JS; we verify the API
    # serves the discussion lines instead of the rendered HTML.
    api = client.get("/api/docs/demo/spec")
    assert api.status_code == 200
    data = api.json()
    assert "open comment" in data["body_md"]
    assert "resolved comment" in data["body_md"]


def test_sidebar_collapse_releases_space(tmp_path: Path) -> None:
    """Verify the sidebar collapse CSS actually releases the 280px column.

    Regression: the sidebar div had min-width: auto (the CSS grid default),
    so even with grid-template-columns: 0 the sidebar kept its content
    width and the right pane got no extra room.
    """
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    doc = client.get("/docs/demo/spec")
    assert doc.status_code == 200
    body = doc.text
    # Collapsed state collapses the grid track to 0
    assert "grid-template-columns: 0" in body
    # The sidebar div must allow itself to shrink to that 0px track
    # (min-width: 0 on the grid item is the key fix; without it, the
    # grid item's content min-width keeps it at 280px+ even when the
    # track is 0).
    assert "min-width: 0" in body
    # When collapsed, the sidebar div is explicitly sized to 0 so it
    # cannot leak into the right pane.
    assert "width: 0" in body


def test_pane_layout_allows_flex_shrink(tmp_path: Path) -> None:
    """Verify the pane layout CSS allows flex shrinking so adding panes
    doesn't squash existing ones to "one character per line".

    Regression: previously min-width:520px + flex:1 1 0 caused content
    to wrap at every character when panes couldn't all fit at 520px.
    """
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    doc = client.get("/docs/demo/spec")
    assert doc.status_code == 200
    body = doc.text
    # The pane rule must allow flex-shrink (no fixed min-width that
    # forces per-character wrapping when N panes overflow the container).
    assert "flex: 1 1 0;" in body
    assert "min-width: 0;" in body
    # The container must allow horizontal overflow rather than crushing
    # pane content into single-character columns.
    assert "overflow-x: auto;" in body
    # The single-pane case keeps a comfortable reading width
    # (~720px) centered in the workspace.
    assert "pane:only-child" in body
    assert "max-width: 720px" in body
    # Doc pages have IDs on workspace / workspace-inner so JS can
    # toggle the pane-host class dynamically (NOT applied by default
    # — only when 2+ panes are open, or a single pane cannot reach
    # the 50 Chinese-char reading-width threshold).
    assert 'id="workspace"' in body
    assert 'id="workspace-inner"' in body
    # The pane-host CSS rule must exist (reclaims padding + max-width)
    # but is NOT applied unconditionally to doc pages.
    assert ".pane-host" in body
    assert "max-width: none" in body
    # Split icon is now an SVG background image on the .icon-split CSS class.
    assert "icon-split" in body
    assert "data:image/svg+xml" in body
    # The default <main> markup should NOT have pane-host baked in.
    assert 'class="workspace pane-host"' not in body


def test_wiki_index_renders_index_md_content(tmp_path: Path) -> None:
    """The /wiki page should render the content of .louke/wiki/index.md,
    not enumerate the pages/ directory directly."""
    root = build_project(tmp_path)
    index = root / ".louke" / "wiki" / "index.md"
    index.write_text(
        "# Custom Wiki Index\n"
        "\n"
        "This is a librarian-maintained index. It should show up as the\n"
        "wiki landing page content, replacing the old card-grid listing.\n"
        "\n"
        "## Sections\n"
        "\n"
        "- Decisions\n"
        "- Experience\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    page = client.get("/wiki")
    assert page.status_code == 200
    body = page.text
    # The custom index.md content must be rendered (markdown -> HTML)
    assert "Custom Wiki Index" in body
    assert "librarian-maintained index" in body
    # The pages-list side card is still present
    assert "Pages" in body
    assert "overview" in body  # page from build_project
    # The old card-grid is no longer the primary layout
    assert "wiki-layout" in body
    assert "wiki-index-content" in body


def test_wiki_refresh_route_calls_librarian(tmp_path: Path, monkeypatch) -> None:
    """The /api/wiki/refresh endpoint should delegate to
    `lk agent librarian rewrite` (which handles bundle selection +
    prompt generation). Direct `opencode run --agent librarian` without
    a positional <prompt> fails with
    "You must provide a message or a command", so we go through lk."""
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import louke.web.app as app_module

    # The louke.web.app module does not import shutil (lint pass dropped it
    # when the endpoint stopped calling shutil.which); inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    # Pretend lk is on PATH so the endpoint doesn't bail with 503.
    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")
    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        captured["timeout"] = kwargs.get("timeout")

        class _R:
            returncode = 0
            stdout = "librarian: ok"
            stderr = ""

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["returncode"] == 0
    assert "librarian: ok" in data["stdout"]
    # The exact command must be `python -m louke agent librarian rewrite`.
    # Going through lk avoids the "no message or command" error from
    # raw `opencode run --agent librarian`.
    assert captured["cmd"][:3] == [sys.executable, "-m", "louke"]
    assert captured["cmd"][3:] == ["agent", "librarian", "rewrite"]
    assert captured["cwd"] == str(root)
    assert captured["timeout"] is not None and captured["timeout"] >= 60  # AC-FR1301-01


def test_wiki_refresh_bypasses_lk_path_lookup(tmp_path: Path, monkeypatch) -> None:
    """The endpoint runs librarian via `python -m louke agent librarian
    rewrite` so it does NOT depend on the `lk` console-script being on
    PATH. Some IDE-launched servers strip PATH to a single entry, so
    `shutil.which('lk')` would return None there even when louke is
    importable as a module (which it must be — this endpoint lives in
    louke.web).
    """
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import louke.web.app as app_module

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    # If the old `shutil.which('lk')` check was still here, this would
    # short-circuit to 503. We expect 200 instead.
    monkeypatch.setattr(app_module.shutil, "which", lambda name: None)
    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd

        class _R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    # Python module invocation, not `lk` script.
    assert captured["cmd"][:3] == [sys.executable, "-m", "louke"]
    assert captured["cmd"][3:] == ["agent", "librarian", "rewrite"]


def test_wiki_refresh_503_when_subprocess_missing(tmp_path: Path, monkeypatch) -> None:
    """If subprocess.run itself fails (e.g. python not findable), the
    endpoint must return a 5xx, not silently succeed."""
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import louke.web.app as app_module

    def fake_run(cmd, *args, **kwargs):
        raise OSError("python not found")

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 500
    assert "failed to spawn" in resp.json()["error"]


def test_wiki_refresh_no_path_dependency() -> None:
    """Configuration that PATH must contain 'lk' is broken — exercise
    it via the constant check that used to gate the endpoint."""
    # This test exists to document the bug we just fixed: previously
    # the endpoint required shutil.which('lk') to return a path. The
    # fix replaces this with `python -m louke agent librarian rewrite`,
    # which works as long as louke is importable.
    import louke.web.app as app_module

    src = inspect.getsource(app_module.api_wiki_refresh)
    assert "shutil.which" not in src, (
        "api_wiki_refresh should not call shutil.which() — use "
        "`python -m louke ...` to avoid PATH dependency. Found "
        "shutil.which usage in the source."
    )


def test_wiki_refresh_surfaces_compact_bundle_hint(tmp_path: Path, monkeypatch) -> None:
    """When the project has no .compact-bundle.md, the librarian subprocess
    exits non-zero with stderr mentioning compact-bundle. The endpoint
    must surface a `hint` field so the UI can tell the user to run
    `lk agent librarian compact` first."""
    root = build_project(tmp_path)
    bundle = root / ".louke" / "wiki" / ".compact-bundle.md"
    if bundle.exists():
        bundle.unlink()

    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import louke.web.app as app_module

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    def fake_run(cmd, *args, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = "error: .compact-bundle.md does not exist, please run lk agent librarian compact first"

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "hint" in data
    assert "lk agent librarian compact" in data["hint"]


def test_workbench_exposes_wiki_activity(tmp_path: Path) -> None:
    """The authenticated Workbench keeps Wiki reachable from its toolbar."""
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    home = client.get("/workbench?activity=projects")
    assert home.status_code == 200
    body = home.text
    assert 'data-activity="wiki"' in body


def test_wiki_index_renders_double_bracket_links(tmp_path: Path) -> None:
    """[[page]] and [[page|display]] in index.md must be rendered as
    clickable links to /wiki/<page>."""
    root = build_project(tmp_path)
    index = root / ".louke" / "wiki" / "index.md"
    index.write_text(
        "# Wiki\n"
        "\n"
        "## Recent\n"
        "\n"
        "- [[sage-interview]] — Sage Interview\n"
        "- [[scout-v0.1|Scout v0.1]] — Ready\n"
        "- [[guides/getting-started]] — Guide\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    page = client.get("/wiki")
    assert page.status_code == 200
    body = page.text
    # [[sage-interview]] -> <a href="/wiki/sage-interview">sage-interview</a>
    assert 'href="/wiki/sage-interview"' in body
    # [[scout-v0.1|Scout v0.1]] -> <a href="/wiki/scout-v0.1">Scout v0.1</a>
    assert 'href="/wiki/scout-v0.1"' in body
    assert ">Scout v0.1<" in body
    # [[guides/getting-started]] -> nested path preserved
    assert 'href="/wiki/guides/getting-started"' in body
    # The raw [[ ]] syntax must NOT appear in the rendered output
    assert "[[" not in body
    assert "]]" not in body


def test_wiki_refresh_logs_subprocess_output(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """When the librarian subprocess exits non-zero, the server log
    must contain the stdout/stderr so failures are debuggable.
    """
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import logging
    import louke.web.app as app_module

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    def fake_run(cmd, *args, **kwargs):
        class _R:
            returncode = 2
            stdout = "librarian step 1 ok\nstep 2 failed: bad input"
            stderr = "ERROR: missing config\nFATAL: giving up"

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger="louke.web"):
        resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["returncode"] == 2
    # Subprocess output must be emitted to the server log so a non-zero
    # exit is debuggable from `tail -f` on the server.
    log_text = caplog.text
    assert "librarian finished" in log_text
    assert "returncode=2" in log_text
    assert "ERROR: missing config" in log_text
    assert "FATAL: giving up" in log_text
    assert "librarian run failed" in log_text  # explicit non-zero warning


def test_wiki_refresh_logs_on_success(tmp_path: Path, monkeypatch, caplog) -> None:
    """On success, the log records an INFO line so the run is auditable."""
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import logging
    import louke.web.app as app_module

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    def fake_run(cmd, *args, **kwargs):
        class _R:
            returncode = 0
            stdout = "librarian: index.md updated"
            stderr = ""

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger="louke.web"):
        resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    log_text = caplog.text
    assert "wiki refresh requested" in log_text
    assert "spawning:" in log_text
    assert "librarian rewrite" in log_text
    assert "librarian finished: returncode=0" in log_text
    assert "librarian: index.md updated" in log_text


def test_wiki_refresh_auto_runs_compact_when_bundle_missing(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """Click refresh with no bundle on disk should auto-run
    `lk agent librarian compact` first so the user never has to type
    that command themselves. The auto-compact runs as a separate
    subprocess before the rewrite, and the click ultimately succeeds.
    """
    import logging

    root = build_project(tmp_path)
    # Ensure NO compact bundle exists, but raw/ does (so compact can run).
    bundle = root / ".louke" / "wiki" / ".compact-bundle.md"
    if bundle.exists():
        bundle.unlink()
    raw_dir = root / ".louke" / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / "2026-07-10-test.md").write_text(
        "date: 2026-07-10\nstatus: resolved\n\nTest raw entry.\n",
        encoding="utf-8",
    )

    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    import louke.web.app as app_module

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    # Capture every subprocess.run invocation so we can assert compact
    # ran BEFORE rewrite, and that rewrite still ran after.
    calls: list = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))

        class _R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger="louke.web"):
        resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Auto-compact must have been called first
    assert len(calls) >= 2, (
        f"expected at least 2 subprocess calls, got {len(calls)}: {calls}"
    )
    assert calls[0][3:] == ["agent", "librarian", "compact"], (
        f"first call should be compact, got {calls[0]}"
    )
    # Then rewrite
    assert calls[1][3:] == ["agent", "librarian", "rewrite"], (
        f"second call should be rewrite, got {calls[1]}"
    )

    # Server log records both events
    log_text = caplog.text
    assert "auto-running librarian compact (no bundle yet)" in log_text
    assert "auto-compact finished" in log_text


def test_wiki_refresh_skips_auto_compact_when_bundle_present(
    tmp_path: Path, monkeypatch
) -> None:
    """If the bundle already exists, auto-compact is skipped — we go
    straight to rewrite. This keeps the click fast in the common case.
    """
    import louke.web.app as app_module

    root = build_project(tmp_path)
    # Pre-populate a bundle so auto-compact is skipped
    (root / ".louke" / "wiki" / ".compact-bundle.md").write_text(
        "date: 2026-07-09\nstatus: resolved\n\nExisting bundle.\n",
        encoding="utf-8",
    )

    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    calls: list = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))

        class _R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _R()

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # Only ONE call: rewrite. No compact (skipped because bundle exists).
    assert len(calls) == 1, f"expected only rewrite, got {calls}"
    assert calls[0][3:] == ["agent", "librarian", "rewrite"]


def test_wiki_refresh_handles_missing_raw_directory(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """No .louke/raw/ AND no compact bundle → auto-compact would fail,
    so we skip it (with a warning) and let rewrite surface its own
    'compact-bundle missing' error. The user gets a clear hint in
    both the server log AND the response hint field.
    """
    import logging
    import louke.web.app as app_module

    root = build_project(tmp_path)
    # Remove raw/ so compact can't run
    shutil.rmtree(root / ".louke" / "raw", ignore_errors=True)
    # No bundle either
    bundle = root / ".louke" / "wiki" / ".compact-bundle.md"
    if bundle.exists():
        bundle.unlink()

    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    # The louke.web.app module does not import shutil; inject it here so
    # the legacy monkeypatch line below still works.
    monkeypatch.setattr(app_module, "shutil", shutil, raising=False)

    monkeypatch.setattr(app_module.shutil, "which", lambda name: "/usr/bin/lk")

    def fake_run(cmd, *args, **kwargs):
        # Simulate rewrite failing because no bundle
        if "rewrite" in cmd:

            class _R:
                returncode = 1
                stdout = ""
                stderr = "error: .compact-bundle.md does not exist"

            return _R()
        # compact should not be called since raw/ doesn't exist
        raise AssertionError("compact should not be called without raw/")

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger="louke.web"):
        resp = client.post("/api/wiki/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "hint" in data
    assert "lk agent librarian compact" in data["hint"]
    # Log records the skip
    assert "no .louke/raw/ directory" in caplog.text


def test_wiki_refresh_progress_modal_present(tmp_path: Path) -> None:
    """The /wiki page must include the step-by-step modal so a multi-minute
    wiki refresh does not look like the click was ignored. The modal
    starts hidden and is shown by the click handler; we verify the DOM
    elements, animation classes, and stepping logic are wired in."""
    root = build_project(tmp_path)
    client = TestClient(create_app(root))
    client.post("/api/auth/register", json={"username": "Aaron", "password": "secret"})

    body = client.get("/wiki").text
    # Modal DOM
    assert 'id="wiki-modal"' in body
    assert 'id="wiki-modal-title"' in body
    assert 'id="wiki-modal-elapsed"' in body
    assert 'id="wiki-modal-detail"' in body
    assert 'id="wiki-modal-dismiss"' in body
    # Three steps with the right data-step keys
    assert 'data-step="prepare"' in body
    assert 'data-step="agent"' in body
    assert 'data-step="apply"' in body
    # User-facing labels in Chinese (no mention of "librarian")
    assert "准备中" in body
    # The "agent" step label describes the action in user terms —
    # "调用 Agent 生成 llm wiki 中" — not the internal name "librarian".
    assert "调用 Agent 生成 llm wiki 中" in body
    assert "应用更新" in body
    # The modal must NOT mention "librarian" in any visible label
    for label_match in re.findall(r'class="step-label">([^<]+)<', body):
        assert "librarian" not in label_match.lower(), (
            f"step label exposes 'librarian' to user: {label_match!r}"
        )
    # Animations
    assert "@keyframes wiki-modal-pulse" in body
    assert "@keyframes wiki-refresh-spin" in body
    # Modal starts hidden
    assert 'id="wiki-modal" class="wiki-modal" hidden' in body
    # Click handler is wired up
    assert "wikiRefreshBtn.addEventListener" in body
    assert "fmtElapsed" in body
    # Step transition logic exists
    assert "setStep('prepare', 'done'" in body
    assert "setStep('agent', 'active'" in body
    assert "setStep('apply', 'done'" in body
