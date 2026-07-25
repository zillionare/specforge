"""Shared conftest for v0.14-005 ATDD e2e tests.

Auto-marks tests under ``tests/e2e/v014_atdd_process_improvement`` as
``e2e`` (so the runner's ``-m e2e`` selects them) and registers the
``v014_005_full_lifecycle`` marker for the dedicated full-lifecycle
job.

The ATDD Project Status routes live behind the production Setup
Gate. Real ``/api/projects/.../status`` is reachable only when the
workspace has a valid v2 ``complete`` manifest. Driving the gate
through the public first-user wizard requires the workspace to be
in ``pending_user`` first; today the wizard endpoints are partially
wired (model-checks are allow-listed but not mounted, blocking
advance to ``complete``). The only public route that lands the
workspace in ``complete`` without invoking the wizard would be the
production ``lk install`` machinery, which the v0.14 bootstrap
phase disallows.

Until Devon closes the v2 wizard gap, Shield E2E must use a
**tmp workspace** whose ``.louke/web-setup-state.json`` is seeded
with a valid v2 ``complete`` manifest. The workspace itself is
discarded before exit; no real credential / real HOME / production
state is touched. This satisfies IF-PROJECT-RUN-01 (real
composition root) and IF-PROJECT-STATUS-01 (real route table) while
honouring FR-PROJECT-RUN-01 fail-closed semantics for the seeded
state (no real install happens in this fixture).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pytest
from starlette.testclient import TestClient

from louke.web.setup_state import MANIFEST_VERSION


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "v014_005_full_lifecycle: full-lifecycle matrix scenarios; "
        "executed only by the dedicated CI job (test-plan §2.3). "
        "Deselected from the regular e2e command by "
        "``-m 'not v014_005_full_lifecycle'``.",
    )


@pytest.fixture
def registered_markers(request):
    """Return the dict of marker names registered with Pytest.

    Tests can assert ``"v014_005_full_lifecycle" in registered_markers``
    to validate that ``pytest_configure`` registered the marker. The
    attribute name is private to Pytest but stable across 8.x/9.x.
    """
    config = request.config
    # ``_markers`` holds the keyed Marker objects registered via
    # ``addinivalue_line("markers", ...)``. Fall back to ``getini``
    # inspection if the attribute is unavailable.
    if hasattr(config, "_markers"):
        return config._markers
    # Fallback: parse the markers section directly.
    markers_ini = config.getini("markers") if hasattr(config, "getini") else []
    return {line.split(":", 1)[0].strip() for line in markers_ini}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/e2e/v014_atdd_process_improvement" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "tests/integration/v014_atdd_process_improvement" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


# ---------------------------------------------------------------------------
# Workspace fixtures
# ---------------------------------------------------------------------------


def _seed_complete_workspace(root: Path) -> None:
    """Write a minimal v2 ``complete`` Setup manifest into *root*."""
    louke_dir = root / ".louke"
    project_dir = louke_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text('[project]\nname="fixture"\n')

    manifest = {
        "version": MANIFEST_VERSION,
        "workspace_id": "",
        "revision": 2,
        "status": "complete",
        "first_principal_id": "prin_fixture000000",
        "model_check": {
            "check_id": "mc_fixture",
            "revision": 1,
            "state": "passed",
            "model_id": "fixture-model",
            "diagnosis": None,
            "observed_at": "2026-07-25T00:00:00Z",
        },
        "completed_at": "2026-07-25T00:00:00Z",
    }
    (louke_dir / "web-setup-state.json").write_text(json.dumps(manifest))
    (louke_dir / "web-users.json").write_text(json.dumps({"users": []}))
    (louke_dir / "web-sessions.json").write_text(json.dumps({"sessions": []}))


@pytest.fixture(scope="function")
def shielded_complete_workspace(tmp_path: Path) -> Iterable[Path]:
    """Yield a tmp workspace containing a v2 ``complete`` Setup manifest.

    The directory is wiped by ``tmp_path`` after each test. No real
    ``.louke/`` directory is created outside ``tmp_path``.
    """
    _seed_complete_workspace(tmp_path)
    yield tmp_path


@pytest.fixture(scope="function")
def shielded_app_client(shielded_complete_workspace: Path) -> Iterable[TestClient]:
    """Yield a TestClient rooted on a tmp ``complete`` workspace.

    Reaches the real ``louke.web.app.create_app`` composition
    root, registered against the seeded tmp workspace.
    ``raise_server_exceptions=False`` so the ATDD stub's
    ``NotImplementedError`` propagates as the documented 500.
    """
    from louke.web.app import create_app

    app = create_app(project_root=str(shielded_complete_workspace))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
