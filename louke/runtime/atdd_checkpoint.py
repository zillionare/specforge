"""IF-ATDD-CHECKPOINT-01: M-IMPL/M-TEST ATDD checkpoint公开骨架。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ATDDCheckpointProjection:
    """IF-ATDD-CHECKPOINT-01 §3 Projection shape.

    Attributes:
        checkpoint_id: Stable identifier for this checkpoint within the run.
        stage_id: ``M-IMPL`` or ``M-TEST``.
        phase: Lifecycle phase of the checkpoint.
        display_state: UI-visible state (pending|running|passed|failed|attention|cooldown|stale).
        owner: Agent role responsible for the current transition.
        baseline_identity: Locked baseline digest this checkpoint binds to.
        declaration_identity: Interface declaration manifest identity.
        test_bundle_identity: Frozen test bundle identity (null before freeze).
        candidate_identity: Implementation candidate identity (null before Devon).
        runner_identity: Host runner contract identity.
        evidence_summary: Short human-readable summary of current evidence.
        reason: Why the checkpoint is in its current state.
        impact: User-visible impact description.
        owning_url: URL to the surface that owns this checkpoint.
        available_actions: Runtime capabilities available to the Human.
        m_verify_allowed: Whether the M-VERIFY gate is unlocked (all required
            AC→IF→layer→test→surface→result→mutation closure passed and
            restored GREEN).
    """

    checkpoint_id: str
    stage_id: str
    phase: str
    display_state: str
    owner: str
    baseline_identity: str
    declaration_identity: str
    test_bundle_identity: str | None
    candidate_identity: str | None
    runner_identity: str
    evidence_summary: str
    reason: str
    impact: str
    owning_url: str
    available_actions: list[str] = field(default_factory=list)
    m_verify_allowed: bool = False


def prepare_shield_task(
    *,
    project_root: Path,
    run_id: str,
    attempt_id: str,
    baseline_identity: str,
    expected_run_revision: int,
    output_path: Path,
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
    """记录M-TEST语义判别、恢复GREEN和AC闭包。

    When every required AC→IF→layer→test→surface→result→mutation mapping
    is closed and restored GREEN is confirmed, ``m_verify_allowed`` is
    set to ``true`` on the resulting checkpoint projection, unlocking
    the ``continue_m_verify`` action in Project Status.
    """
    raise NotImplementedError("IF-ATDD-CHECKPOINT-01")
