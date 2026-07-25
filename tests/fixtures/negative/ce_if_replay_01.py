"""IF-LIFECYCLE-01: Deterministic replay adapter declaration (COUNTEREXAMPLE)."""

from __future__ import annotations

from pathlib import Path

from louke.opencode.adapter import OpenCodeAdapter


def load_replay_adapter(*, manifest_path: Path, project_root: Path) -> OpenCodeAdapter:
    """负样本：去除 IF-token，破坏 lifecycle 归因。"""
    raise NotImplementedError("missing contract anchor")
