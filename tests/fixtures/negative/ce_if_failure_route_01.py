"""IF-FAILURE-ROUTE-01: ATDD失败分类与返回公开骨架（COUNTEREXAMPLE）。"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from pathlib import Path


class _Classification(enum.Enum):
    """负样本：classification 不封闭。"""

    INFRASTRUCTURE_OR_TEST_ASSET = "infrastructure_or_test_asset"
    TEST_CONTRACT_MISMATCH = "test_contract_mismatch"
    IMPLEMENTATION_OR_COMPOSITION = "implementation_or_composition"
    DESIGN_GAP = "design_gap"
    REQUIREMENT_GAP = "requirement_gap"
    SAFETY_ATTENTION = "safety_attention"
    # 负样本：新增第六类（不应存在）
    IMPLEMENTATION_BUG = "implementation_bug"


class _Owner(enum.Enum):
    SHIELD = "Shield"
    DEVON = "Devon"
    ARCHER = "Archer"
    RUNTIME = "Runtime"
    HUMAN_CONTROLLED_REQUIREMENTS = "HumanControlledRequirements"


class _ReturnTarget(enum.Enum):
    M_IMPL_SHIELD = "M-IMPL:Shield"
    M_IMPL_DEVON = "M-IMPL:Devon"
    M_DESIGN = "M-DESIGN"
    M_SPEC = "M-SPEC"
    M_ACC = "M-ACC"
    ATTENTION = "ATTENTION"


def classify_atdd_failure(
    *,
    project_root: Path,
    evidence_paths: Sequence[Path],
    contract_paths: Sequence[Path],
    prism_diagnostic_path: Path | None,
    output_path: Path,
) -> Mapping[str, object]:
    """负样本：classification 仍非封闭。"""
    raise NotImplementedError("IF-FAILURE-ROUTE-01")
