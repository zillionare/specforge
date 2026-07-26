"""Unit contracts for authenticated v0.14 Story/Scribe HTTP boundaries."""

from types import SimpleNamespace

import json

from louke.web.api.scribe import _require_human, _task_summary
from louke.web.store import ProjectStore


def test_scribe_api_rejects_anonymous_reads(tmp_path) -> None:
    """Story and task read models require a server-authenticated Human."""
    project_dir = tmp_path / ".louke" / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "project.toml").write_text(
        "[project]\nrepo = 'example/repo'\n", encoding="utf-8"
    )
    store = ProjectStore(tmp_path)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(store=store)),
        cookies={},
        headers={},
    )

    response = _require_human(request, csrf_required=False)

    assert response.status_code == 401
    assert json.loads(response.body)["error_code"] == "AUTH_REQUIRED"


def test_task_summary_exposes_only_current_transport_identity() -> None:
    """The project current model exposes task/session status, not secrets."""
    summary = _task_summary(
        {
            "task_id": "task-1",
            "active_attempt_id": "attempt-1",
            "session_id": "session-1",
            "status": "blocked",
            "connection": "blocked",
            "lease_id": "secret-like-lease",
        }
    )

    assert summary == {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "session_id": "session-1",
        "status": "blocked",
        "connection": "blocked",
    }
