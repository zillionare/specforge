"""AC-FR1512-01@v0.13.1: workbench chrome and runtime identity contract."""

from __future__ import annotations

from html.parser import HTMLParser

from starlette.testclient import TestClient

from louke.web.app import create_app


class _ButtonParser(HTMLParser):
    """Collect toolbar buttons and stable workbench markers from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str]] = []
        self.markers: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        testid = attributes.get("data-testid", "")
        if testid in {"workbench-toolbar", "workbench-sidebar", "workbench-main"}:
            self.markers.add(testid)
        if tag == "button" and testid.startswith("toolbar-"):
            self.buttons.append(attributes)


def _workbench_html(tmp_path) -> str:
    project_dir = tmp_path / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nversion = "0.8"\nspec_id = "demo"\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))
    registered = client.post(
        "/api/auth/register", json={"username": "fixture-human", "password": "secret"}
    )
    assert registered.status_code == 200
    response = client.get("/workbench?activity=chat")
    assert response.status_code == 200
    return response.text


def test_toolbar_item_order(tmp_path) -> None:
    """AC-FR1302-01, AC-FR1302-02: toolbar buttons use the contract order."""
    parser = _ButtonParser()
    parser.feed(_workbench_html(tmp_path))
    assert [button["aria-label"] for button in parser.buttons] == [
        "Projects",
        "Chat",
        "Dev Docs",
        "End User Docs",
        "Wiki",
        "Runs",
        "Accounts",
        "Settings",
    ]


def test_toolbar_tooltip(tmp_path) -> None:
    """AC-FR1301-02: every toolbar button exposes its readable title."""
    parser = _ButtonParser()
    parser.feed(_workbench_html(tmp_path))
    assert [button["title"] for button in parser.buttons] == [
        "Projects",
        "Chat",
        "Dev Docs",
        "End User Docs",
        "Wiki",
        "Runs",
        "Accounts",
        "Settings",
    ]


def test_tab_can_coexist(tmp_path) -> None:
    """AC-FR1301-03/05: client contract preserves existing tabs on activation."""
    html = _workbench_html(tmp_path)
    assert 'data-tab-key="dev-docs"' in html
    assert 'data-tab-key="runs"' in html
    assert "openTab(activity)" in html
    assert "activity==='gears'" in html
    assert "tabs.has(tabKey)" in html


def test_sidebar_switches_with_toolbar(tmp_path) -> None:
    """AC-FR1301-03: toolbar activation changes the sidebar kind and tree."""
    html = _workbench_html(tmp_path)
    assert 'data-sidebar-kind="chat"' in html
    assert 'data-sidebar-kind="wiki"' in html
    assert 'data-sidebar-kind="dev-docs"' in html
    assert "renderSidebar(activity)" in html


def test_data_testid_present(tmp_path) -> None:
    """AC-FR1301-01: all three workbench landmarks have stable test IDs."""
    parser = _ButtonParser()
    parser.feed(_workbench_html(tmp_path))
    assert parser.markers == {
        "workbench-toolbar",
        "workbench-sidebar",
        "workbench-main",
    }


def test_settings_shows_current_runtime_identity(monkeypatch, tmp_path) -> None:
    """AC-FR1512-01@v0.13.1: Settings exposes the active version and mode."""
    monkeypatch.setenv("LOUKE_RUNTIME_MODE", "global")
    html = _workbench_html(tmp_path)
    assert 'data-testid="settings-runtime-identity"' in html
    assert "(global)" in html
    assert 'data-testid="settings-project-root"' in html
    assert 'data-testid="settings-local-runtime"' in html


def _authenticated_root_html(tmp_path) -> tuple[str, str]:
    """Build a v0.14 workspace, register a user, return (home, legacy)."""
    from tests.test_web_server import build_project, authenticate

    root = build_project(tmp_path)
    # Override project version to v0.14 to mirror the current workspace state.
    project_toml = root / ".louke" / "project" / "project.toml"
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('version = "0.8"', 'version = "0.14.0"', 1)
    text = text.replace(
        'spec_id = "demo"', 'spec_id = "v0.14-002-workflow-reflow-design"', 1
    )
    text = text.replace(
        'release_branch = "releases/v0.8"', 'release_branch = "releases/0.14.0"', 1
    )
    project_toml.write_text(text, encoding="utf-8")

    client = TestClient(create_app(root))
    authenticate(client)
    # v0.14: ``/`` 303s to the workbench activity; follow the
    # redirect so the workbench chrome is rendered. The legacy
    # surface still requires an explicit ``?legacy=1`` query and
    # is gated behind authentication.
    home = client.get("/", follow_redirects=True)
    legacy = client.get("/?legacy=1", follow_redirects=True)
    return home.text, legacy.text


def test_root_renders_workbench_chrome(tmp_path) -> None:
    """GET / must render the v0.13 workbench chrome on a v0.14 workspace.

    Regression for v0.14.0: the previous routing fell back to ``home_page``
    whenever the project version did not start with ``0.13``, which served
    the v0.12 sidebar + main shell. v0.14 must default to the toolbar +
    sidebar + main chrome and only opt back into the legacy surface when
    ``?legacy=1`` is supplied.
    """
    home, _ = _authenticated_root_html(tmp_path)
    assert 'data-louke-region="toolbar"' in home
    assert 'data-testid="workbench-toolbar"' in home
    assert 'data-testid="workbench-sidebar"' in home
    assert 'data-testid="workbench-main"' in home
    assert '<button class="sidebar-toggle"' not in home


def test_legacy_query_param_still_resolves_to_the_canonical_projects_surface(
    tmp_path,
) -> None:
    """Legacy query input cannot create a parallel pre-Login workbench."""
    _, legacy = _authenticated_root_html(tmp_path)
    assert 'data-projects-state="empty"' in legacy
    assert 'data-testid="new-project"' in legacy
    assert '<button class="sidebar-toggle"' not in legacy


def test_settings_runtime_read_model_is_public(monkeypatch, tmp_path) -> None:
    """AC-FR1512-01@v0.13.1: the runtime read model is JSON and uncached."""
    from tests.test_web_server import build_project

    monkeypatch.setenv("LOUKE_RUNTIME_MODE", "global")
    response = TestClient(create_app(build_project(tmp_path))).get(
        "/api/ui/settings/runtime"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "global"
    assert payload["display"].endswith(" (global)")
