"""TestClient tests for the /projects page sub-app (B3a).

Verifies the projects HTML page sub-app:
- GET / lists active, history and backlog projects as cards in three sections.
- GET /new renders a project-creation form.
- POST /new previews the project (calls upstream /api/projects/preview).
- POST /new/confirm/{preview_id} confirms a preview and redirects to the detail.
- GET /{id} renders the project detail (header, current step, events timeline).
- Upstream API failures are surfaced as user-facing error messages (no 500).

The page talks to the upstream ``/api/projects/*`` and ``/api/runtime/*`` sub-apps
via module-level seams (``_fetch_*`` / ``_post_*``) so tests can patch them
without a live server, mirroring the Workbench page test pattern.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from louke.web.pages import projects as projects_page


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient backed by a fresh projects page sub-app.

    The app is created with ``api_base="http://testserver"`` so the seam's
    first positional arg is deterministic in assertions.
    """
    return TestClient(projects_page.create_app(api_base="http://testserver"))


# -- fixtures: upstream payloads ---------------------------------------------


def _active_payload() -> list[dict[str, object]]:
    """Return a one-item active-projects payload."""
    return [
        {
            "project_id": "prj_active1",
            "name": "Active feature",
            "story_excerpt": "Build X",
            "release_version": "v0.12.0",
            "workflow_definition_id": "new_feature",
            "workflow_version": "1",
            "run_id": "run_active1",
            "run_status": "waiting_for_human",
            "current_step": "requirements_approval",
            "updated_at": "2026-07-14T00:00:00Z",
            "archived_at": None,
        }
    ]


def _history_payload() -> list[dict[str, object]]:
    """Return a one-item history-projects payload."""
    return [
        {
            "project_id": "prj_old1",
            "name": "Old feature",
            "story_excerpt": "Shipped Y",
            "release_version": "v0.11.0",
            "workflow_definition_id": "bug_fix",
            "workflow_version": "1",
            "run_id": "run_old1",
            "run_status": "completed",
            "current_step": "complete",
            "updated_at": "2026-06-01T00:00:00Z",
            "archived_at": "2026-06-02T00:00:00Z",
        }
    ]


def _backlog_payload() -> list[dict[str, object]]:
    """Return a one-item backlog payload."""
    return [
        {
            "entry_id": "bl_1",
            "story": "Blocked story",
            "release_version": "v0.12.0",
            "workflow_definition_id": "new_feature",
            "workflow_version": "1",
            "created_at": "2026-07-13T00:00:00Z",
        }
    ]


def _project_detail() -> dict[str, object]:
    """Return a single-project detail payload."""
    return {
        "project_id": "prj_active1",
        "run_id": "run_active1",
        "name": "Active feature",
        "story_excerpt": "Build X",
        "release_version": "v0.12.0",
        "workflow_definition_id": "new_feature",
        "workflow_version": "1",
        "status": "active",
        "created_at": "2026-07-14T00:00:00Z",
        "archived_at": None,
    }


def _graph_payload() -> dict[str, object]:
    """Return a graph payload for the detail page."""
    return {
        "run_id": "run_active1",
        "definition_id": "new_feature",
        "definition_version": "1",
        "nodes": [
            {
                "step_id": "start",
                "kind": "program",
                "label": "Start",
                "state": "completed",
            },
            {
                "step_id": "requirements_approval",
                "kind": "human_gate",
                "label": "Requirements Approval",
                "state": "waiting_for_human",
            },
            {
                "step_id": "design",
                "kind": "program",
                "label": "Design",
                "state": "pending",
            },
        ],
        "edges": [
            {
                "edge_id": "e1",
                "from_step": "start",
                "to_step": "requirements_approval",
                "condition": "done",
            },
            {
                "edge_id": "e2",
                "from_step": "requirements_approval",
                "to_step": "design",
                "condition": "approved",
            },
        ],
        "current_step": "requirements_approval",
        "revision": 1,
    }


def _events_payload() -> dict[str, object]:
    """Return an events payload for the detail page timeline."""
    return {
        "items": [
            {
                "event_id": "evt_1",
                "run_id": "run_active1",
                "type": "run.created",
                "sequence": 1,
                "occurred_at": "2026-07-14T00:00:00Z",
                "actor": {"kind": "human", "id": "alice"},
                "payload": {},
            },
            {
                "event_id": "evt_2",
                "run_id": "run_active1",
                "type": "run.step_entered",
                "sequence": 2,
                "occurred_at": "2026-07-14T00:01:00Z",
                "actor": {"kind": "human", "id": "alice"},
                "payload": {"step_id": "requirements_approval"},
            },
        ]
    }


def _catalog_payload() -> list[dict[str, object]]:
    """Return a catalog payload (new_feature + bug_fix)."""
    return [
        {
            "definition_id": "new_feature",
            "version": "1",
            "label": "New feature",
            "is_hotfix": False,
        },
        {
            "definition_id": "bug_fix",
            "version": "1",
            "label": "Bug fix (hotfix)",
            "is_hotfix": True,
        },
    ]


# -- GET / (index) -----------------------------------------------------------


def test_projects_index_shows_active_history_backlog(client: TestClient) -> None:
    """GET / renders three sections, each with one card."""
    with (
        patch.object(
            projects_page,
            "_fetch_active",
            new=AsyncMock(return_value=_active_payload()),
        ),
        patch.object(
            projects_page,
            "_fetch_history",
            new=AsyncMock(return_value=_history_payload()),
        ),
        patch.object(
            projects_page,
            "_fetch_backlog",
            new=AsyncMock(return_value=_backlog_payload()),
        ),
    ):
        resp = client.get("/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "Active" in body
    assert "History" in body
    assert "Backlog" in body
    # Cards link to /projects/{id} for active and history, not for backlog.
    assert 'href="/projects/prj_active1"' in body
    assert 'href="/projects/prj_old1"' in body
    # Backlog card shows the story but no link.
    assert "Blocked story" in body
    assert 'href="/projects/bl_1"' not in body
    # The "+ New" button links to the new-project form.
    assert 'href="/projects/new"' in body


def test_projects_index_handles_empty_state(client: TestClient) -> None:
    """GET / with no projects renders empty-state messages."""
    with (
        patch.object(projects_page, "_fetch_active", new=AsyncMock(return_value=[])),
        patch.object(projects_page, "_fetch_history", new=AsyncMock(return_value=[])),
        patch.object(projects_page, "_fetch_backlog", new=AsyncMock(return_value=[])),
    ):
        resp = client.get("/")

    assert resp.status_code == 200
    body = resp.text
    assert "No active projects" in body
    assert "No history" in body
    assert "No backlog" in body


def test_projects_index_handles_api_error(client: TestClient) -> None:
    """When the upstream active-list call fails, the page shows an error, status 200."""
    with (
        patch.object(
            projects_page,
            "_fetch_active",
            new=AsyncMock(side_effect=RuntimeError("upstream 500")),
        ),
        patch.object(projects_page, "_fetch_history", new=AsyncMock(return_value=[])),
        patch.object(projects_page, "_fetch_backlog", new=AsyncMock(return_value=[])),
    ):
        resp = client.get("/")

    assert resp.status_code == 200
    assert "upstream 500" in resp.text or "error" in resp.text.lower()


# -- GET /new ----------------------------------------------------------------


def test_projects_new_form_renders(client: TestClient) -> None:
    """GET /new renders the creation form with the required fields."""
    with patch.object(
        projects_page, "_fetch_catalog", new=AsyncMock(return_value=_catalog_payload())
    ):
        resp = client.get("/new")

    assert resp.status_code == 200
    body = resp.text
    assert 'name="story"' in body
    assert 'name="release_version"' in body
    assert 'name="workflow_definition_id"' in body
    assert 'name="workflow_version"' in body
    # Catalog options are rendered.
    assert "new_feature" in body
    assert "bug_fix" in body


def test_projects_new_preview(client: TestClient) -> None:
    """POST /new calls upstream /preview and renders a confirm form."""
    preview_mock = AsyncMock(
        return_value={
            "preview_id": "prev_abc",
            "story_excerpt": "Previewed feature",
            "release_version": "v0.12.0",
            "workflow_definition_id": "new_feature",
            "workflow_version": "1",
            "project_id": None,
            "source_contract": None,
        }
    )
    with patch.object(projects_page, "_post_preview", new=preview_mock):
        resp = client.post(
            "/new",
            data={
                "story": "Previewed feature",
                "release_version": "v0.12.0",
                "workflow_definition_id": "new_feature",
                "workflow_version": "1",
            },
            follow_redirects=False,
        )

    preview_mock.assert_awaited_once()
    assert resp.status_code == 200
    body = resp.text
    # The preview excerpt and a confirm form (posting the preview_id) are shown.
    assert "Previewed feature" in body
    assert "prev_abc" in body
    assert "confirm" in body.lower()


# -- POST /new/confirm/{preview_id} -----------------------------------------


def test_projects_new_confirm(client: TestClient) -> None:
    """POST /new/confirm/{preview_id} confirms and redirects to the detail page."""
    confirm_mock = AsyncMock(
        return_value={
            "project_id": "prj_new1",
            "run_id": "run_new1",
            "name": "Confirmed feature",
            "story_excerpt": "...",
            "release_version": "v0.12.0",
            "workflow_definition_id": "new_feature",
            "workflow_version": "1",
            "status": "active",
            "created_at": "2026-07-14T00:00:00Z",
            "archived_at": None,
        }
    )
    with patch.object(projects_page, "_post_confirm", new=confirm_mock):
        resp = client.post(
            "/new/confirm/prev_abc",
            follow_redirects=False,
        )

    confirm_mock.assert_awaited_once()
    assert resp.status_code in (303, 302, 307)
    assert "/projects/prj_new1" in resp.headers["location"]


# -- GET /{id} ---------------------------------------------------------------


def test_projects_detail_renders_run_state(client: TestClient) -> None:
    """GET /{id} renders the project header, current step, and events timeline."""
    with (
        patch.object(
            projects_page,
            "_fetch_project",
            new=AsyncMock(return_value=_project_detail()),
        ),
        patch.object(
            projects_page, "_fetch_graph", new=AsyncMock(return_value=_graph_payload())
        ),
        patch.object(
            projects_page,
            "_fetch_events",
            new=AsyncMock(return_value=_events_payload()["items"]),
        ),
    ):
        resp = client.get("/prj_active1")

    assert resp.status_code == 200
    body = resp.text
    assert "Active feature" in body
    assert "requirements_approval" in body
    # Graph: the current step is rendered, and pending/completed states appear.
    assert "Start" in body
    assert "Design" in body
    # Events timeline.
    assert "run.created" in body
    assert "run.step_entered" in body


def test_projects_detail_404(client: TestClient) -> None:
    """GET /{id} on an unknown project renders a 'not found' message, status 200."""
    with (
        patch.object(
            projects_page,
            "_fetch_project",
            new=AsyncMock(side_effect=RuntimeError("404 not found")),
        ),
        patch.object(
            projects_page, "_fetch_graph", new=AsyncMock(return_value=_graph_payload())
        ),
        patch.object(projects_page, "_fetch_events", new=AsyncMock(return_value=[])),
    ):
        resp = client.get("/prj_unknown")

    assert resp.status_code == 200
    assert "not found" in resp.text.lower()
