"""IF-FAILURE-ROUTE-01: ATDD失败分类与返回公开骨架（COUNTEREXAMPLE-DECISION）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def classify_atdd_failure(
    *,
    project_root: Path,
    evidence_paths: Sequence[Path],
    contract_paths: Sequence[Path],
    prism_diagnostic_path: Path | None,
    output_path: Path,
) -> Mapping[str, object]:
    """负样本：缺少 FailureDecision 类型，导致 decision_includes_all_required_fields 失败。"""
    raise NotImplementedError("IF-FAILURE-ROUTE-01")
