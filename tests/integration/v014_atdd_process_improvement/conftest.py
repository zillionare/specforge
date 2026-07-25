"""Shared conftest for v0.14-005 ATDD integration tests.

Provides:

* a stable temporary workspace root for tests that need a minimal
  ``.louke/project/`` skeleton;
* ``repo_root`` and ``spec_dir`` fixtures for path-bound tests;
* a pytest marker registration for the ``v014_005_full_lifecycle`` marker
  used by the dedicated full-lifecycle CI job (tests that import this
  marker are not collected by the generic e2e command).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "v014_005_full_lifecycle: full lifecycle matrix test, "
        "deselected by `tests/e2e/run-project-venv e2e` command",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def spec_dir(repo_root: Path) -> Path:
    return (
        repo_root
        / ".louke"
        / "project"
        / "specs"
        / "v0.14-005-atdd-process-improvement"
    )


@pytest.fixture(scope="session")
def contracts_dir(repo_root: Path) -> Path:
    return (
        repo_root
        / ".louke"
        / "project"
        / "contracts"
        / "v0.14-005-atdd-process-improvement"
    )
