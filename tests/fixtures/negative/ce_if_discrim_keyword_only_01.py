"""IF-DISCRIM-01: keyword-only drift counterexample."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def run_discrimination(
    # 负样本：去掉 keyword-only marker
    project_root: Path,
    adapter_contract_path: Path,
    counterexample_manifest_path: Path,
    candidate_identity: str,
    phase: str,
    evidence_path: Path,
) -> Mapping[str, object]:
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
    raise NotImplementedError("IF-DISCRIM-01")
