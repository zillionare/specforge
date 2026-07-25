"""COUNTEREXAMPLE: M-IMPL/M-TEST ATDD checkpoint (IF-token stripped)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def prepare_shield_task(
    *,
    project_root: Path,
    run_id: str,
    attempt_id: str,
    baseline_identity: str,
    expected_run_revision: int,
    output_path: Path,
) -> Mapping[str, object]:
    """负样本：去掉 contract anchor."""
    raise NotImplementedError("missing contract anchor")


def record_shield_submission(
    *,
    project_root: Path,
    task_path: Path,
    bundle_path: Path,
    red_evidence_path: Path,
    expected_run_revision: int,
) -> Mapping[str, object]:
    raise NotImplementedError("missing contract anchor")


def freeze_test_bundle(
    *,
    project_root: Path,
    submission_identity: str,
    prism_review_path: Path,
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("missing contract anchor")


def prepare_devon_task(
    *,
    project_root: Path,
    run_id: str,
    attempt_id: str,
    frozen_bundle_identity: str,
    expected_run_revision: int,
    output_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("missing contract anchor")


def request_declaration_revision(
    *,
    project_root: Path,
    task_id: str,
    contract_anchor: str,
    reason: str,
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("missing contract anchor")


def record_implementation_result(
    *,
    project_root: Path,
    task_id: str,
    candidate_identity: str,
    runner_evidence_paths: Sequence[Path],
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("missing contract anchor")


def record_m_test_closure(
    *,
    project_root: Path,
    candidate_identity: str,
    discrimination_evidence_path: Path,
    restored_green_evidence_path: Path,
    closure_evidence_path: Path,
    expected_run_revision: int,
) -> Mapping[str, object]:
    """负样本：去掉 m_verify_allowed."""
    raise NotImplementedError("missing contract anchor")
