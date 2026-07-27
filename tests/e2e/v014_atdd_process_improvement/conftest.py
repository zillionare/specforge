"""Shared conftest for v0.14-005 ATDD e2e tests.

Auto-marks tests under ``tests/e2e/v014_atdd_process_improvement`` as
``e2e`` (so the runner's ``-m e2e`` selects them) and registers the
``v014_005_full_lifecycle`` marker for the dedicated full-lifecycle
job.

The product no longer exposes Web Setup state. ATDD tests use an isolated
workspace and the public Register surface before exercising authenticated
routes; no private manifest is seeded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest
from starlette.testclient import TestClient


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
    """Create a minimal isolated workspace without Web Setup state."""
    louke_dir = root / ".louke"
    project_dir = louke_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nversion="0.14.1"\nrepo="github.com/zillionare/louke"\n'
        'spec_id="fixture"\n[meta]\ncurrent_stage="M-E2E"\n',
        encoding="utf-8",
    )


@pytest.fixture(scope="function")
def shielded_complete_workspace(tmp_path: Path) -> Iterable[Path]:
    """Yield a tmp workspace for public Login/Register route tests.

    The directory is wiped by ``tmp_path`` after each test. No real
    ``.louke/`` directory is created outside ``tmp_path``.
    """
    _seed_complete_workspace(tmp_path)
    yield tmp_path


@pytest.fixture(scope="function")
def shielded_app_client(shielded_complete_workspace: Path) -> Iterable[TestClient]:
    """Yield an authenticated TestClient rooted on a tmp workspace.

    Reaches the real ``louke.web.app.create_app`` composition
    root, registered through the public Login/Register contract.
    ``raise_server_exceptions=False`` so the ATDD stub's
    ``NotImplementedError`` propagates as the documented 500.
    """
    from louke.web.app import create_app

    app = create_app(project_root=str(shielded_complete_workspace))
    with TestClient(app, raise_server_exceptions=False) as client:
        registered = client.post(
            "/api/auth/register",
            json={"username": "fixture-human", "password": "secret"},
        )
        assert registered.status_code == 200
        yield client
