"""IF-ATDD-CHECKPOINT-01: freeze kwargs drift counterexample."""

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
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def record_shield_submission(
    *,
    project_root: Path,
    task_path: Path,
    bundle_path: Path,
    expected_run_revision: int,  # 负样本：去掉 red_evidence_path
) -> Mapping[str, object]:
    """负样本：去掉 red_evidence_path。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def freeze_test_bundle(
    *,
    project_root: Path,
    prism_review_path: Path,  # 负样本：去掉 submission_identity
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    """负样本：freeze 缺 submission_identity。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def prepare_devon_task(
    *,
    project_root: Path,
    run_id: str,
    attempt_id: str,
    frozen_bundle_identity: str,
    expected_run_revision: int,
    output_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def request_declaration_revision(
    *,
    project_root: Path,
    contract_anchor: str,  # 负样本：去掉 task_id / reason / evidence_path
    expected_run_revision: int,
) -> Mapping[str, object]:
    """负样本：request_declaration_revision 缺 task_id。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def record_implementation_result(
    *,
    project_root: Path,
    task_id: str,
    candidate_identity: str,
    runner_evidence_paths: Sequence[Path],
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def record_m_test_closure(
    *,
    project_root: Path,
    candidate_identity: str,
    discrimination_evidence_path: Path,
    restored_green_evidence_path: Path,
    closure_evidence_path: Path,
    expected_run_revision: int,
) -> Mapping[str, object]:
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")
