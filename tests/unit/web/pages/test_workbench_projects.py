"""Contract tests for the Workbench Projects activity interface stubs.

IF-PROJECT-01 / IF-GUIDE-01 / IF-STATUS-01 / IF-ENV-01 / IF-COMPAT-01

These are ATDD contract tests for the Archer interface stubs in
``louke.web.pages.workbench`` (architecture §14.1, workbench section). Each
test drives a stub through its locked public signature and asserts the
contract from ``interfaces.md`` / ``acceptance.md``.

Against the still-shipped stubs the call raises the declared
``NotImplementedError("<IF-id>")`` — a valid RED attributable to the precise
stub token (test-plan §3.5). Each test turns GREEN when Devon implements the
rendering behind the same signature. The stub signatures, ``TOOLBAR_ITEMS``
and the ``workbench`` handler's ``?activity=`` dispatch are locked and are NOT
modified here.

How these tests drive the SUT (no SUT stub):

* The real stub functions are imported and called directly; nothing is mocked
  or replaced. ``_render_projects_activity`` is exercised with a real
  ``create_app`` instance bound to the request so the implementation can read
  ``request.app.state`` exactly as it will in production.
* The state-specific renderers (``_projects_main_panel`` /
  ``_projects_status_cockpit`` / ``_projects_env_wizard`` / ``_projects_sidebar``)
  are pure rendering contracts keyed by their explicit argument, so they are
  asserted directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from louke.web.app import create_app
from louke.web.pages.workbench import (
    _projects_env_wizard,
    _projects_main_panel,
    _projects_new_project_wizard,
    _projects_sidebar,
    _projects_status_cockpit,
    _render_projects_activity,
    project_detail_compat,
    projects_compat,
    run_detail_compat,
)

#: The 13 canonical Project Status stages in locked order (IF-STATUS-01 /
#: interfaces §IF-STATUS-01 ``stage_catalog``).
_CANONICAL_STAGES: tuple[str, ...] = (
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

#: The four Environment Gate steps in fixed check order (IF-ENV-01 /
#: interfaces §IF-ENV-01 ``EnvironmentStep.id``).
_ENV_STEPS: tuple[str, ...] = (
    "gh_executable",
    "gh_auth_scopes",
    "repository_binding",
    "canonical_main",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def workbench_app(tmp_path: Path):
    """A real Louke web app bound to a minimal isolated workspace."""
    project = tmp_path / ".louke" / "project"
    project.mkdir(parents=True)
    (project / "project.toml").write_text(
        '[project]\nname = "ws_projects_activity"\n', encoding="utf-8"
    )
    return create_app(tmp_path)


def _make_request(
    path: str = "/workbench",
    *,
    query_string: bytes = b"",
    path_params: dict | None = None,
    app=None,
) -> Request:
    """Build a minimal Starlette ``Request`` for driving the page stubs."""
    scope: dict = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "path_params": path_params or {},
    }
    if app is not None:
        scope["app"] = app
    return Request(scope)


# ---------------------------------------------------------------------------
# IF-PROJECT-01: _render_projects_activity (top-level Projects activity)
# ---------------------------------------------------------------------------


def test_render_projects_activity_returns_projects_html_with_guide(
    workbench_app,
) -> None:
    """AC-FR0401-01 / AC-FR0501-01: ``?activity=projects`` renders Projects + Guide.

    The Projects activity always mounts the Guide sidebar (IF-GUIDE-01) and a
    state-driven main panel (IF-PROJECT-01).
    """
    # AC-FR0401-01 / AC-FR0501-01
    request = _make_request(
        "/workbench", query_string=b"activity=projects", app=workbench_app
    )
    response = asyncio.run(_render_projects_activity(request))
    assert isinstance(response, HTMLResponse), (
        "AC-FR0401-01: ?activity=projects must render an HTML Projects activity"
    )
    body = response.body.decode().lower()
    assert "guide" in body, (
        "AC-FR0501-01: the Projects activity must always mount the Guide sidebar"
    )


def test_render_projects_activity_shares_runtime_identity(workbench_app) -> None:
    """AC-FR1512-01/02@v0.13.1 / I-15: Projects activity shares the API runtime identity.

    Since ``GET /workbench`` redirects to ``?activity=projects`` once Setup is
    complete, the rendered Projects activity must itself surface the Settings
    read-model identity (``<version> (<mode>)``) alongside the project
    directory and ``.venv`` path metadata, and the v0.15 placeholder.
    """
    request = _make_request(
        "/workbench", query_string=b"activity=projects", app=workbench_app
    )
    response = asyncio.run(_render_projects_activity(request))
    assert isinstance(response, HTMLResponse)
    html = response.body.decode()

    # AC-FR1512-01: the runtime identity element is rendered on the page.
    assert 'data-testid="settings-runtime-identity"' in html, (
        "AC-FR1512-01: the Projects activity must render the runtime identity"
    )
    # AC-FR1512-02: project directory and local .venv path metadata are present.
    assert 'data-testid="settings-project-root"' in html, (
        "AC-FR1512-02: project directory metadata must accompany the identity"
    )
    assert 'data-testid="settings-local-runtime"' in html, (
        "AC-FR1512-02: the .venv path metadata must accompany the identity"
    )
    # The v0.15 Settings placeholder stays visible alongside the identity.
    assert "待 v0.15" in html

    # The rendered identity matches the public Settings read-model display.
    from louke import __version__
    from louke.__main__ import _runtime_mode

    display = f"{__version__} ({_runtime_mode()})"
    assert display in html, (
        f"AC-FR1512-01: the rendered display must match the read model ({display!r})"
    )


# ---------------------------------------------------------------------------
# IF-PROJECT-01: _projects_main_panel (empty / active / conflict)
# ---------------------------------------------------------------------------


def test_projects_main_panel_empty_offers_new_project() -> None:
    """AC-FR0401-01: empty context shows the purpose hint + ``New Project`` action."""
    # AC-FR0401-01
    html = _projects_main_panel("empty")
    assert "New Project" in html, (
        "AC-FR0401-01: the empty Projects context must offer the New Project action"
    )


def test_projects_main_panel_active_shows_status_cockpit() -> None:
    """AC-FR0401-01: active context loads the Project Status cockpit."""
    # AC-FR0401-01
    html = _projects_main_panel("active")
    low = html.lower()
    assert "status" in low or "cockpit" in low, (
        "AC-FR0401-01: the active Projects context must load the Project Status cockpit"
    )


def test_projects_main_panel_active_does_not_offer_second_create() -> None:
    """AC-FR0401-02: active context offers no successful second-Project create action."""
    # AC-FR0401-02
    html = _projects_main_panel("active")
    assert "New Project" not in html, (
        "AC-FR0401-02: an active Project must not offer a New Project create action"
    )


def test_projects_main_panel_conflict_shows_conflicts_and_blocks_create() -> None:
    """AC-FR0401-02: conflict context shows the conflicts and blocks New Project."""
    # AC-FR0401-02
    html = _projects_main_panel("conflict")
    low = html.lower()
    assert "conflict" in low, (
        "AC-FR0401-02: the conflict context must surface the conflicting identities"
    )


# ---------------------------------------------------------------------------
# IF-GUIDE-01: _projects_sidebar
# ---------------------------------------------------------------------------


def test_projects_sidebar_mounts_guide_session_and_composer() -> None:
    """AC-FR0501-01 / AC-FR0501-03: the sidebar mounts the Guide session + composer."""
    # AC-FR0501-01 / AC-FR0501-03
    html = _projects_sidebar()
    low = html.lower()
    assert "guide" in low, (
        "AC-FR0501-01: the Projects sidebar must mount the Guide session"
    )
    assert "guide_message" in html or "composer" in low, (
        "AC-FR0501-03: the Guide sidebar must expose a chat composer"
    )


# ---------------------------------------------------------------------------
# IF-STATUS-01: _projects_status_cockpit
# ---------------------------------------------------------------------------


def test_projects_status_cockpit_covers_thirteen_canonical_stages_in_order() -> None:
    """AC-FR1201-01: the cockpit timeline covers all 13 canonical stages in order."""
    # AC-FR1201-01
    html = _projects_status_cockpit("prj_demo")
    for stage in _CANONICAL_STAGES:
        assert stage in html, (
            f"AC-FR1201-01: the cockpit timeline must show canonical stage {stage}"
        )
    positions = [html.index(stage) for stage in _CANONICAL_STAGES]
    assert positions == sorted(positions), (
        "AC-FR1201-01: the canonical stages must appear in their locked order"
    )


def test_projects_status_cockpit_has_active_card_and_return_edges() -> None:
    """AC-FR1201-02 / AC-FR1401-01: the cockpit shows an active card + return edges."""
    # AC-FR1201-02 / AC-FR1401-01
    html = _projects_status_cockpit("prj_demo")
    low = html.lower()
    assert "active" in low, (
        "AC-FR1201-02: the cockpit must highlight the active attempt card"
    )
    assert "return" in low, (
        "AC-FR1401-01: the cockpit must render return edges (source/target/direction)"
    )


def test_projects_status_cockpit_supports_keyboard_navigation() -> None:
    """AC-FR1201-03: full history is reachable via keyboard navigation."""
    # AC-FR1201-03
    html = _projects_status_cockpit("prj_demo")
    low = html.lower()
    assert "home" in low or "end" in low or "arrow" in low or "keyboard" in low, (
        "AC-FR1201-03: the cockpit must expose keyboard navigation for full history"
    )


# ---------------------------------------------------------------------------
# IF-ENV-01: _projects_env_wizard
# ---------------------------------------------------------------------------


def test_projects_env_wizard_covers_the_four_required_checks() -> None:
    """AC-FR0601-01: the Environment Wizard covers gh CLI/auth/binding/main."""
    # AC-FR0601-01
    html = _projects_env_wizard()
    for step in _ENV_STEPS:
        assert step in html, (
            f"AC-FR0601-01: the Environment Wizard must cover step {step}"
        )


def test_projects_env_wizard_offers_retry_for_blocking_step() -> None:
    """AC-FR0601-02: a failed/uncertain step exposes a Retry entry."""
    # AC-FR0601-02
    html = _projects_env_wizard()
    assert "retry" in html.lower(), (
        "AC-FR0601-02: a blocking Environment step must expose a Retry entry"
    )


# ---------------------------------------------------------------------------
# IF-COMPAT-01: compatibility routes
# ---------------------------------------------------------------------------


def test_projects_compat_redirects_to_projects_activity() -> None:
    """AC-FR1501-02: ``/projects`` → 303 ``/workbench?activity=projects``."""
    # AC-FR1501-02
    request = _make_request("/projects")
    response = asyncio.run(projects_compat(request))
    assert isinstance(response, RedirectResponse), (
        "AC-FR1501-02: /projects must redirect to the canonical Projects activity"
    )
    assert response.status_code == 303, "AC-FR1501-02: /projects must redirect with 303"
    assert response.headers["location"].endswith("/workbench?activity=projects"), (
        "AC-FR1501-02: /projects must redirect to /workbench?activity=projects"
    )


def test_project_detail_compat_redirects_to_project_status() -> None:
    """AC-FR1501-02: ``/projects/{id}`` → canonical Project Status for that id."""
    # AC-FR1501-02
    request = _make_request(
        "/projects/prj_demo", path_params={"project_id": "prj_demo"}
    )
    response = asyncio.run(project_detail_compat(request))
    assert isinstance(response, RedirectResponse), (
        "AC-FR1501-02: /projects/{id} must redirect to the Project Status"
    )
    location = response.headers["location"]
    assert "/workbench?activity=projects" in location, (
        "AC-FR1501-02: /projects/{id} must redirect into the Projects activity"
    )
    assert "prj_demo" in location, (
        "AC-FR1501-02: /projects/{id} must preserve the project identity"
    )


def test_project_detail_compat_rejects_an_unbound_project(
    workbench_app,
    tmp_path: Path,
) -> None:
    """AC-FR1301-02: an unknown Project deep link returns a locatable 404."""
    # AC-FR1301-02
    state_path = tmp_path / ".louke" / "project-state.json"
    state_path.write_text(
        '{"state":"active","project_id":"prj_bound"}', encoding="utf-8"
    )
    request = _make_request(
        "/projects/prj_missing",
        path_params={"project_id": "prj_missing"},
        app=workbench_app,
    )

    response = asyncio.run(project_detail_compat(request))

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 404
    body = response.body.decode()
    assert "prj_missing" in body
    assert "not found" in body.lower() or "migration" in body.lower()


def test_new_project_wizard_uses_canonical_preview_and_confirm_apis(
    workbench_app,
) -> None:
    """AC-FR1001-01 / AC-FR1101-01: wizard drives real Preview and Confirm APIs."""
    # AC-FR1001-01 / AC-FR1101-01
    request = _make_request(
        "/workbench",
        query_string=b"activity=projects&action=new_project",
        app=workbench_app,
    )

    html = _projects_new_project_wizard(request)

    assert "/api/projects/preview" in html
    assert "/api/projects/confirm" in html
    assert 'data-testid="project-preview"' in html
    assert 'data-testid="create-project"' in html
    assert "expected_preview_revision" in html


def test_run_detail_compat_redirects_to_project_status() -> None:
    """AC-FR1501-02: ``/runs/{id}`` → Project Status for the run's project."""
    # AC-FR1501-02
    request = _make_request("/runs/run_demo", path_params={"run_id": "run_demo"})
    response = asyncio.run(run_detail_compat(request))
    assert isinstance(response, RedirectResponse), (
        "AC-FR1501-02: /runs/{id} must redirect to the bound Project Status"
    )
    assert response.status_code == 303, (
        "AC-FR1501-02: /runs/{id} must redirect with 303"
    )
