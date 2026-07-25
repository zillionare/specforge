"""IF-DISCRIM-01: 隔离counterexample判别与恢复公开骨架。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def run_discrimination(
    project_root: Path,
    adapter_contract_path: Path,
    counterexample_manifest_path: Path,
    candidate_identity: str,
    phase: str,
    evidence_path: Path,
) -> Mapping[str, object]:
    """在隔离worktree/artifact上执行pre或post-GREEN判别。"""
    raise NotImplementedError("IF-DISCRIM-01")


def verify_restored_candidate(
    *,
    project_root: Path,
    candidate_identity: str,
    original_artifact_digest: str,
    affected_bundle_path: Path,
    full_bundle_path: Path,
    evidence_path: Path,
) -> Mapping[str, object]:
    """复核原candidate身份及受影响和全量required GREEN。"""
    raise NotImplementedError("IF-DISCRIM-01")
