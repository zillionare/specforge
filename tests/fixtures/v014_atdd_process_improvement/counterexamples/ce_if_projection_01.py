"""IF-PROJECT-STATUS-01: Project Status ATDD投影公开骨架（COUNTEREXAMPLE）。"""

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
    """负样本：去除 IF-token，使 IF-VALID-RED-01 归因失败。"""
    raise NotImplementedError("missing contract anchor")
