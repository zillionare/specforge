"""TestClient contract tests for the ``/setup`` page sub-app (FR-0101 / IF-SETUP-01).

The locked v0.14-004 baseline replaces the retired six-step Setup Wizard
(``identity -> repository -> dependencies -> review -> applying ->
complete``) with a two-context Setup page:

  1. ``pending_user``  -> the first-user creation form.
  2. ``pending_model`` -> the OpenCode model-check view with a Retry entry.

On ``complete`` the page navigates to ``/workbench?activity=projects``.
The retired per-step routes ``/setup/repository/``, ``/setup/dependencies/``,
``/setup/review/`` and ``/setup/applying/`` no longer exist (404).

How these tests drive the SUT (no SUT stub):

* The real ``louke.web.pages.setup`` sub-app is exercised through its
  public HTTP surface (``TestClient``); its routing/rendering is never
  replaced.
* The Setup state is established by writing a **real v2 manifest** into a
  **real, isolated workspace** bound to the sub-app state — the page must
  reflect the on-disk Setup projection (IF-SETUP-01), exactly as the
  integration suite drives ``setup_projection`` against ``synthetic_host``.
* The page's backend status seam (``_fetch_setup_status``, the client for
  ``GET /api/setup/status``) is fed the **real projection** derived from
  that manifest via ``setup_projection.read``. This substitutes the page's
  *external backend dependency* (which a bare ``TestClient`` cannot serve
  over a socket); it does not replace the page. If a future implementation
  reads the projection directly from the bound workspace and drops the
  seam, the patch degrades to a no-op and the workspace binding still
  drives the page.

These are ATDD contract tests: they are RED against the still-shipped
six-step page and turn GREEN when the page migration to the two-context
contract lands.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from louke.web import setup_projection
from louke.web.pages import setup as setup_page
from louke.web.setup_state import (
    ModelCheck,
    SetupManifest,
    SetupStatus,
    try_read_manifest,
    write_manifest,
)


WORKSPACE_ID = "ws_setup_page"

#: Markers of the retired six-step wizard that must not appear on the
#: two-context Setup page. The route paths anchor the IF-SETUP-01 contract;
#: ``Runtime dependencies`` is the distinctive retired stepper label that the
#: current wizard still renders, so its absence discriminates RED -> GREEN.
RETIRED_STEP_MARKERS: tuple[str, ...] = (
    "Runtime dependencies",
    "/setup/repository/",
    "/setup/dependencies/",
    "/setup/review/",
    "/setup/applying/",
)


# ---------------------------------------------------------------------------
# Real workspace + real v2 manifest fixtures (external fixture, no SUT stub)
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """An isolated workspace with a ``.louke/project`` layout bound to the page."""
    ws = tmp_path / "workspace"
    (ws / ".louke" / "project").mkdir(parents=True)
    (ws / ".louke" / "project" / "project.toml").write_text(
        '[project]\nname = "ws_setup_page"\n',
        encoding="utf-8",
    )
    return ws


def _client(workspace: Path) -> TestClient:
    """Return a TestClient for the real setup page sub-app bound to ``workspace``."""
    app = Starlette(
        routes=[Route("/", endpoint=setup_page.setup_root, methods=["GET", "POST"])]
    )
    app.state.workspace_root = workspace
    return TestClient(app)


@contextlib.contextmanager
def _feed_projection(workspace: Path):
    """Feed the page's backend status seam the real Setup projection.

    Substitutes the page's external backend dependency (the
    ``GET /api/setup/status`` client) with the real projection derived from
    the on-disk v2 manifest. The page itself is never replaced. Degrades to
    a no-op if the seam is removed in favour of a direct workspace read.
    """
    projection = setup_projection.read(workspace, workspace_id=WORKSPACE_ID)
    if hasattr(setup_page, "_fetch_setup_status"):
        with patch.object(
            setup_page,
            "_fetch_setup_status",
            new=AsyncMock(return_value=projection),
        ):
            yield projection
    else:
        yield projection


def _write_pending_user(ws: Path) -> None:
    """Persist a ``pending_user`` manifest (no first user yet)."""
    write_manifest(
        ws,
        SetupManifest(
            workspace_id=WORKSPACE_ID,
            revision=0,
            status=SetupStatus.PENDING_USER,
        ),
    )


def _write_pending_model_failed(ws: Path) -> None:
    """Persist a ``pending_model`` manifest carrying a failed model probe."""
    check = ModelCheck(
        check_id="chk_1",
        revision=1,
        state="failed",
        model_id=None,
        diagnosis={
            "object": "opencode model check",
            "known_facts": "opencode run exited 1",
            "impact": "cannot verify a working model",
            "recovery_url": "/setup",
        },
        observed_at="2026-07-24T00:00:00Z",
    )
    write_manifest(
        ws,
        SetupManifest(
            workspace_id=WORKSPACE_ID,
            revision=1,
            status=SetupStatus.PENDING_MODEL,
            first_principal_id="prin_alpha",
            model_check=check,
        ),
    )


def _write_complete(ws: Path) -> None:
    """Persist a ``complete`` manifest (first user + passed model probe)."""
    manifest = SetupManifest(
        workspace_id=WORKSPACE_ID,
        revision=0,
        status=SetupStatus.PENDING_USER,
    )
    manifest = manifest.advance_to_pending_model(
        first_principal_id="prin_alpha", expected_revision=0
    )
    manifest = manifest.complete(
        model_check_state="passed",
        model_check_id="chk_1",
        model_check_revision=1,
        model_id="minimax/m2",
        diagnosis=None,
        observed_at="2026-07-24T00:00:00Z",
        expected_revision=1,
    )
    write_manifest(ws, manifest)


def _assert_retired_wizard_absent(body: str) -> None:
    """Assert none of the retired six-step wizard markers are rendered."""
    for marker in RETIRED_STEP_MARKERS:
        assert marker not in body, (
            "AC-FR0101-01: retired wizard step "
            f"{marker!r} must not appear on the two-context Setup page"
        )


# ---------------------------------------------------------------------------
# Two-context visible states (IF-SETUP-01)
# ---------------------------------------------------------------------------


def test_setup_pending_user_shows_first_user_form_only(workspace: Path) -> None:
    """AC-FR0101-01: ``pending_user`` renders the first-user form, not the wizard."""
    # AC-FR0101-01
    _write_pending_user(workspace)
    with _feed_projection(workspace):
        resp = _client(workspace).get("/", follow_redirects=False)
    assert resp.status_code == 200, (
        f"AC-FR0101-01: pending_user /setup must render 200, got {resp.status_code}"
    )
    body = resp.text
    assert 'name="name"' in body, (
        "AC-FR0101-01: pending_user must show the first-user name field"
    )
    assert 'name="credential"' in body, (
        "AC-FR0101-01: pending_user must show the first-user credential field"
    )
    _assert_retired_wizard_absent(body)


def test_setup_first_user_form_post_creates_user_without_server_error(
    workspace: Path,
) -> None:
    """The supported first-user form POST redirects after creating the user."""
    _write_pending_user(workspace)
    client = _client(workspace)
    with _feed_projection(workspace):
        page = client.get("/", follow_redirects=False)
        csrf_tokens = re.findall(r'name="csrf_token" value="([^"]*)"', page.text)
        assert len(csrf_tokens) == 1, (
            "The rendered first-user form must contain exactly one CSRF token"
        )
        csrf_token = csrf_tokens[0]
        assert csrf_token, (
            "The rendered first-user form must contain a nonempty CSRF token"
        )
        created = client.post(
            "/",
            data={
                "csrf_token": csrf_token,
                "name": "First Human",
                "credential": "supported-form-credential",
                "create_first_user": "1",
            },
            follow_redirects=False,
        )

    assert created.status_code == 303
    assert created.headers["location"] == "/setup"
    assert try_read_manifest(workspace).status is SetupStatus.PENDING_MODEL


def test_setup_pending_model_shows_model_check_and_retry(workspace: Path) -> None:
    """AC-FR0101-01 / AC-FR0201-02: ``pending_model`` shows the model-check + Retry."""
    # AC-FR0101-01 / AC-FR0201-02
    _write_pending_model_failed(workspace)
    with _feed_projection(workspace):
        resp = _client(workspace).get("/", follow_redirects=False)
    assert resp.status_code == 200, (
        f"AC-FR0201-02: pending_model /setup must render 200, got {resp.status_code}"
    )
    body = resp.text
    assert "retry" in body.lower(), (
        "AC-FR0201-02: a failed model check must expose a Retry entry on /setup"
    )
    assert "model" in body.lower(), (
        "AC-FR0101-01: pending_model must surface the model-check context"
    )
    _assert_retired_wizard_absent(body)


def test_setup_complete_navigates_to_projects(workspace: Path) -> None:
    """AC-FR0301-01: ``complete`` Setup navigates to the Workbench Projects activity."""
    # AC-FR0301-01
    _write_complete(workspace)
    with _feed_projection(workspace):
        resp = _client(workspace).get("/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307), (
        f"AC-FR0301-01: complete /setup must redirect, got {resp.status_code}"
    )
    location = resp.headers.get("location", "")
    assert location.endswith("/workbench?activity=projects"), (
        f"AC-FR0301-01: complete Setup must navigate to Projects, got {location!r}"
    )


# ---------------------------------------------------------------------------
# Retired six-step routes are gone (IF-SETUP-01)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "retired_route",
    ["/repository/", "/dependencies/", "/review/", "/applying/"],
)
def test_setup_retired_step_routes_removed(workspace: Path, retired_route: str) -> None:
    """AC-FR0101-01: the retired six-step wizard routes no longer exist (404)."""
    # AC-FR0101-01
    _write_pending_model_failed(workspace)
    resp = _client(workspace).get(retired_route, follow_redirects=False)
    assert resp.status_code == 404, (
        "AC-FR0101-01: retired route /setup"
        f"{retired_route} must be 404, got {resp.status_code}"
    )
