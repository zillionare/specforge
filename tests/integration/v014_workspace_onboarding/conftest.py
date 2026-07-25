"""Shared pytest configuration for v0.14-004 workspace-onboarding integration tests.

Tests drive real, observable behaviour through the canonical public
surface of each module — there is no stub of the modules under
test. External systems are real too: ``synthetic_host_project`` writes
a real host ``.louke/`` layout and ``synthetic_bare_remote`` builds a
real loopback bare Git repo. The legacy IF-01..IF-14 fixtures are
skipped per Prism review F-001/E-002/N-002 (with ``test_if15`` kept
deliberately so the AC-traceability gate itself remains exercised).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ._mode_b import (
    synthetic_bare_remote,
    synthetic_host_project,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Pytest hook registration
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "v014_004: v0.14-004 workspace-onboarding integration test",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        path = str(item.fspath)
        if "tests/integration/v014_workspace_onboarding" in path:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.v014_004)


# ---------------------------------------------------------------------------
# Real test fixtures (no module-under-test stubs)
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """An isolated workspace directory with ``.louke/`` pre-created."""
    ws = tmp_path / "workspace"
    (ws / ".louke").mkdir(parents=True)
    return ws


@pytest.fixture
def bare_git_remote(tmp_path: Path) -> Path:
    """A loopback bare Git repository for IF-ENV-02 binding tests."""
    return synthetic_bare_remote(tmp_path)


@pytest.fixture
def synthetic_host():
    """Yield a real synthetic host-project directory."""
    with synthetic_host_project() as host:
        yield host


@pytest.fixture(autouse=True)
def _autouse_synthetic_host():
    """Run every test against a fresh, real synthetic host-project layout.

    Per Mode B §3.3 (Prism review F-003), every test in this directory
    must work inside an isolated host-project ``.louke/`` so no code
    can accidentally read or write Louke's own ``.louke/``. The
    fixture is autouse so every integration test inherits the
    isolation by default; tests that need an additional host layer
    can request ``synthetic_host`` to get a nested one.
    """
    with synthetic_host_project(
        marker=f"v014004-autouse-{os.urandom(2).hex()}"
    ) as host:
        yield host
