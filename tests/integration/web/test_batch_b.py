"""AC coverage for the Batch B workbench panels."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from tests.test_web_server import authenticate, build_project


def _html(tmp_path: Path) -> str:
    client = TestClient(create_app(build_project(tmp_path)))
    authenticate(client)
    return client.get("/workbench?activity=chat").text


def test_settings_menu_3_disabled_items(tmp_path: Path) -> None:
    """AC-FR1303-02/03/04 and AC-FR1512-01@v0.13.1 stay compatible."""
    html = _html(tmp_path)
    for name in ("version", "server", "model"):
        assert f'data-testid="settings-menu-{name}"' in html
    assert html.count('aria-disabled="true"') >= 3
    assert html.count("待 v0.15") >= 4
    assert 'data-testid="settings-detail"' in html
    assert 'data-testid="settings-placeholder-detail"' in html
    assert 'data-testid="settings-runtime-identity"' in html
    assert "不会执行任何写操作" in html


def test_accounts_logout(tmp_path: Path) -> None:
    """AC-FR1304-01/02/03: accounts posts logout and returns to the home route."""
    html = _html(tmp_path)
    assert 'data-testid="accounts-menu"' in html
    assert 'data-testid="accounts-logout"' in html
    assert "/api/auth/logout" in html
    assert "location.href='/'" in html


def test_devdocs_sidebar_tree(tmp_path: Path) -> None:
    """AC-FR1308-01/02/03/04: Dev Docs renders a collapsible spec tree."""
    html = _html(tmp_path)
    assert 'data-testid="devdocs-tree"' in html
    assert "localStorage" in html
    assert "louke.dev-docs.tree." in html
    assert 'data-testid="devdocs-file-' in html


def test_wiki_navigation_and_read_only_render(tmp_path: Path) -> None:
    """AC-FR1311-01/02/03/04: Wiki navigation renders read-only pages."""
    html = _html(tmp_path)
    assert 'data-testid="wiki-tree"' in html
    assert 'data-testid="wiki-page-README"' in html
    assert "design docs" in html
    assert "Save" not in html


def test_wiki_notfound_fallback(tmp_path: Path) -> None:
    """AC-FR1312-01/02/03/04: unknown Wiki pages degrade without a 5xx."""
    html = _html(tmp_path)
    assert 'data-testid="wiki-unknown-page"' in html
    assert "未知页面" in html
    assert 'data-unknown="true"' in html
