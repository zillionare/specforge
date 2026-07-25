"""IF-ATDD-CHECKPOINT-01: M-IMPL/M-TEST ATDD checkpoint公开骨架。"""

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
    unexpected_extra_kwarg: str = "MUTANT",
) -> Mapping[str, object]:
    """生成绑定current design baseline的Shield准备任务。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def record_shield_submission(
    *,
    project_root: Path,
    task_path: Path,
    bundle_path: Path,
    red_evidence_path: Path,
    expected_run_revision: int,
) -> Mapping[str, object]:
    """记录Shield测试bundle、counterexample和有效RED提交。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def freeze_test_bundle(
    *,
    project_root: Path,
    submission_identity: str,
    prism_review_path: Path,
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    """在程序证据和独立审查current时冻结测试bundle。"""
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
    """生成绑定current freeze与完整权威输入的Devon任务。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")


def request_declaration_revision(
    *,
    project_root: Path,
    task_id: str,
    contract_anchor: str,
    reason: str,
    expected_run_revision: int,
    evidence_path: Path,
) -> Mapping[str, object]:
    """请求声明修订并公开cooldown/stale返回语义。"""
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
    """记录真实production candidate及required GREEN证据。"""
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
    """记录M-TEST语义判别、恢复GREEN和AC闭包。"""
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")
