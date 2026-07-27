"""Shared pytest configuration for ``tests/integration/web/``."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def setup_complete(tmp_path: Path) -> Path:
    """Create a minimal workspace; Web Setup state is no longer required."""
    project_dir = tmp_path / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nversion = "0.8"\nspec_id = "demo"\n', encoding="utf-8"
    )
    return tmp_path
