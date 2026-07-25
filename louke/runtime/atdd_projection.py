"""IF-PROJECT-STATUS-01: Project Status ATDD投影公开骨架。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path


def project_atdd_status(
    *,
    project_root: Path,
    project_id: str,
    observed_at: datetime | None = None,
) -> Mapping[str, object]:
    """读取Runtime facts并生成同一Project的ATDDStatus。"""
    raise NotImplementedError("IF-PROJECT-STATUS-01")
