"""IF-FAILURE-ROUTE-01: ATDD失败分类与返回公开骨架。"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class FailureClassification(enum.Enum):
    """Closed classification set per IF-FAILURE-ROUTE-01."""

    INFRASTRUCTURE_OR_TEST_ASSET = "infrastructure_or_test_asset"
    TEST_CONTRACT_MISMATCH = "test_contract_mismatch"
    IMPLEMENTATION_OR_COMPOSITION = "implementation_or_composition"
    DESIGN_GAP = "design_gap"
    REQUIREMENT_GAP = "requirement_gap"
    SAFETY_ATTENTION = "safety_attention"


class FailureOwner(enum.Enum):
    """Closed owner set per IF-FAILURE-ROUTE-01."""

    SHIELD = "Shield"
    DEVON = "Devon"
    ARCHER = "Archer"
    RUNTIME = "Runtime"
    HUMAN_CONTROLLED_REQUIREMENTS = "HumanControlledRequirements"


class FailureReturnTarget(enum.Enum):
    """Closed return-target set per IF-FAILURE-ROUTE-01."""

    M_IMPL_SHIELD = "M-IMPL:Shield"
    M_IMPL_DEVON = "M-IMPL:Devon"
    M_DESIGN = "M-DESIGN"
    M_SPEC = "M-SPEC"
    M_ACC = "M-ACC"
    ATTENTION = "ATTENTION"


@dataclass(frozen=True)
class FailureDecision:
    """IF-FAILURE-ROUTE-01 FailureDecision shape.

    Attributes:
        decision_id: Stable identifier for this failure decision.
        classification: One of the six closed classification values.
        owner: Agent role responsible for the return target.
        return_target: Where the failure should be routed.
        contract_anchors: Contract clauses referenced in the decision.
        test_identity: Identity of the failing test (may be empty).
        candidate_identity: Identity of the implementation candidate (may be null).
        runner_identity: Identity of the host runner contract.
        prism_diagnostic_identity: Prism diagnostic digest (null if no Prism review).
        current: Current revision/facts at decision time.
        reason: Human-readable explanation of the decision.
        recovery_url: URL the Human can follow to initiate recovery.
    """

    decision_id: str
    classification: str
    owner: str
    return_target: str
    contract_anchors: list[str]
    test_identity: str
    candidate_identity: str | None
    runner_identity: str
    prism_diagnostic_identity: str | None
    current: str
    reason: str
    recovery_url: str


def classify_atdd_failure(
    *,
    project_root: Path,
    evidence_paths: Sequence[Path],
    contract_paths: Sequence[Path],
    prism_diagnostic_path: Path | None,
    output_path: Path,
) -> Mapping[str, object]:
    """依据current合同和证据返回FailureDecision。"""
    raise NotImplementedError("IF-FAILURE-ROUTE-01")
