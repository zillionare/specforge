"""IF-DISCRIM-01: 隔离counterexample判别与恢复公开骨架（COUNTEREXAMPLE）。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def run_discrimination(
    *,
    project_root: Path,
    adapter_contract_path: Path,
    counterexample_manifest_path: Path,
    candidate_identity: str,
    phase: str,
    evidence_path: Path,
) -> Mapping[str, object]:
    """原接口保留 raise."""
    raise NotImplementedError("IF-DISCRIM-01")


def verify_restored_candidate(
    *,
    project_root: Path,
    candidate_identity: str,
    affected_bundle_path: Path,
    full_bundle_path: Path,
    evidence_path: Path,
    # 负样本：移除 original_artifact_digest
) -> Mapping[str, object]:
    """负样本：移除 original_artifact_digest，破坏 IF-DISCRIM-01 完整性保护。"""
    raise NotImplementedError("IF-DISCRIM-01")
