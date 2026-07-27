"""Dev Docs rendered-preview and cross-reference contract coverage."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from tests.test_web_server import authenticate


def _client(tmp_path: Path) -> TestClient:
    specs = tmp_path / ".louke" / "project" / "specs" / "v0.13-001"
    specs.mkdir(parents=True, exist_ok=True)
    (specs.parents[1] / "project.toml").write_text("[project]\n", encoding="utf-8")
    (specs / "spec.md").write_text(
        '# Foundation\n\nSee FR-1301.\n\n<a id="fr-1301"></a>\n### FR-1301 Main chrome\n',
        encoding="utf-8",
    )
    (specs / "acceptance.md").write_text(
        '# Acceptance\n\n<a id="fr-1301"></a>\n## FR-1301\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))
    authenticate(client)
    return client


def test_devdocs_render_markdown(tmp_path: Path, setup_complete: Path) -> None:
    """AC-FR1309-01/04: a selected document has rendered preview and source, without Save."""
    html = _client(tmp_path).get("/workbench?activity=chat").text

    assert 'data-testid="devdocs-view"' in html
    assert 'data-testid="devdocs-rendered"' in html
    assert 'data-testid="devdocs-source"' in html
    assert 'data-testid="devdocs-save"' not in html


def test_devdocs_cross_ref_fr_to_anchor(tmp_path: Path, setup_complete: Path) -> None:
    """AC-FR1309-03: an in-document FR reference is rendered as an anchor link."""
    html = _client(tmp_path).get("/workbench?activity=chat").text

    assert 'data-testid="devdocs-cross-ref-FR-1301"' in html
    assert 'href="#fr-1301"' in html


def test_devdocs_cross_ref_to_sibling_spec(
    tmp_path: Path, setup_complete: Path
) -> None:
    """AC-FR1309-03: unresolved same-document refs link to the sibling acceptance document."""
    client = _client(tmp_path)
    specs = tmp_path / ".louke" / "project" / "specs" / "v0.13-001"
    (specs / "spec.md").write_text("# Foundation\n\nSee FR-1301.\n", encoding="utf-8")

    html = client.get("/workbench?activity=chat").text

    assert 'data-testid="devdocs-cross-ref-FR-1301"' in html
    assert 'href="?spec=v0.13-001&amp;doc=acceptance#fr-1301"' in html
