"""IF-LIFECYCLE-01: Deterministic replay adapter declaration."""

from __future__ import annotations

from pathlib import Path

from louke.opencode.adapter import OpenCodeAdapter


def load_replay_adapter(*, manifest_path: Path, project_root: Path) -> OpenCodeAdapter:
    """Load the closed replay manifest for one isolated lifecycle run."""
    raise NotImplementedError("MUTANT_NO_TOKEN")
