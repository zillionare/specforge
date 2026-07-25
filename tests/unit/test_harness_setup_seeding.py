"""Unit tests for the isolated-workspace Setup manifest seeding helper.

The v0.14-001 entry-slice harness seeds a v2 ``complete`` Setup manifest so
the v0.14-004 Setup gate does not block the endpoints under test. v0.14-004
adds a ``setup_status`` parameter so the two-context Setup journey can be
driven from ``pending_user`` / ``pending_model`` as well. These tests pin the
three seeding paths (test-plan §6.2 controllable fixture).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from louke.web.setup_state import SetupStatus, try_read_manifest
from tests.fixtures.v014_workflow_reflow.harness import _seed_setup_manifest


def test_seed_setup_manifest_complete(tmp_path: Path) -> None:
    """The default ``complete`` seeding yields a finished Setup manifest."""
    _seed_setup_manifest(tmp_path, "complete")
    manifest = try_read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.status == SetupStatus.COMPLETE
    assert manifest.first_principal_id == "prin_entry_slice"
    assert manifest.model_check is not None
    assert manifest.model_check.state == "passed"


def test_seed_setup_manifest_pending_model(tmp_path: Path) -> None:
    """``pending_model`` seeds an established first user awaiting a check."""
    _seed_setup_manifest(tmp_path, "pending_model")
    manifest = try_read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.status == SetupStatus.PENDING_MODEL
    assert manifest.first_principal_id == "prin_entry_slice"
    assert manifest.model_check is None


def test_seed_setup_manifest_pending_user(tmp_path: Path) -> None:
    """``pending_user`` seeds a blank Setup with no first user."""
    _seed_setup_manifest(tmp_path, "pending_user")
    manifest = try_read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.status == SetupStatus.PENDING_USER
    assert manifest.first_principal_id is None


def test_seed_setup_manifest_rejects_unknown_status(tmp_path: Path) -> None:
    """An unknown ``setup_status`` fails closed."""
    with pytest.raises(ValueError, match="unknown setup_status"):
        _seed_setup_manifest(tmp_path, "bogus")
