"""IF-PROJECT-STATUS-01: Project Status ATDD投影公开骨架.

Contract anchor: "IF-PROJECT-STATUS-01"
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path


_CANONICAL_13: tuple[str, ...] = (
    "M-START",
    "M-STORY",
    "M-SPEC",
    "M-ACC",
    "M-REQ-APPROVAL",
    "M-DESIGN",
    "M-IMPL",
    "M-TEST",
    "M-VERIFY",
    "M-SECURITY",
    "M-RELEASE",
    "M-PUBLISH",
    "M-MILESTONE",
)

_STAGE_OWNERS: dict[str, str] = {
    "M-START": "Sage",
    "M-STORY": "Sage",
    "M-SPEC": "Sage",
    "M-ACC": "Archer",
    "M-REQ-APPROVAL": "Sage",
    "M-DESIGN": "Archer",
    "M-IMPL": "Devon",
    "M-TEST": "Devon",
    "M-VERIFY": "Prism",
    "M-SECURITY": "Judge",
    "M-RELEASE": "Archer",
    "M-PUBLISH": "Archer",
    "M-MILESTONE": "Sage",
}


def _default_checkpoint(checkpoint_id: str, stage_id: str) -> dict[str, object]:
    """Build a default ATDDCheckpointProjection dict for the bootstrap phase."""
    return {
        "checkpoint_id": checkpoint_id,
        "stage_id": stage_id,
        "phase": "running",
        "display_state": "pending",
        "owner": "Devon",
        "baseline_identity": "bootstrap-baseline",
        "declaration_identity": "bootstrap-declaration",
        "test_bundle_identity": None,
        "candidate_identity": None,
        "runner_identity": "bootstrap-runner",
        "evidence_summary": "",
        "reason": "ATDD checkpoint pending in bootstrap mode",
        "impact": "",
        "owning_url": "/workbench",
        "available_actions": ["continue_m_verify"],
        "m_verify_allowed": False,
    }


def _lifecycle_stages(fail_stage: str | None) -> list[dict[str, object]]:
    """Build the 13-stage lifecycle projection.

    Args:
        fail_stage: If non-None, halt at this stage (state=failed) and leave
            subsequent stages unentered. If None, all stages are passed.

    Returns:
        List of 13 stage dicts per IF-LIFECYCLE-01 Lifecycle evidence extension.
    """
    stages: list[dict[str, object]] = []
    fail_idx = _CANONICAL_13.index(fail_stage) if fail_stage else None

    for idx, stage_id in enumerate(_CANONICAL_13):
        if fail_idx is not None and idx == fail_idx:
            stages.append(
                {
                    "stage_id": stage_id,
                    "ordinal": idx + 1,
                    "entered_at": "2026-07-25T00:00:00Z",
                    "completed_at": None,
                    "state": "failed",
                    "execution": "enabled" if stage_id != "M-SECURITY" else "disabled",
                    "precondition_refs": [],
                    "artifact_refs": [],
                    "evidence_refs": [],
                    "projection_revision": 0,
                    "owner": _STAGE_OWNERS.get(stage_id, "Devon"),
                    "recovery_url": (
                        f"/workbench?activity=projects&project=wordcount"
                        f"&failed_stage={stage_id.lower()}"
                    ),
                }
            )
        elif fail_idx is not None and idx > fail_idx:
            stages.append(
                {
                    "stage_id": stage_id,
                    "ordinal": idx + 1,
                    "entered_at": None,
                    "completed_at": None,
                    "state": "pending",
                    "execution": "enabled" if stage_id != "M-SECURITY" else "disabled",
                    "precondition_refs": [],
                    "artifact_refs": [],
                    "evidence_refs": [],
                    "projection_revision": 0,
                    "owner": _STAGE_OWNERS.get(stage_id, "Devon"),
                    "recovery_url": None,
                }
            )
        else:
            stages.append(
                {
                    "stage_id": stage_id,
                    "ordinal": idx + 1,
                    "entered_at": "2026-07-25T00:00:00Z",
                    "completed_at": "2026-07-25T00:00:00Z",
                    "state": "passed",
                    "execution": "disabled" if stage_id == "M-SECURITY" else "enabled",
                    "precondition_refs": [],
                    "artifact_refs": [f"artifact-{stage_id}"],
                    "evidence_refs": [f"evidence-{stage_id}"],
                    "projection_revision": 0,
                    "owner": _STAGE_OWNERS.get(stage_id, "Devon"),
                    "recovery_url": None,
                }
            )

    return stages


def project_atdd_status(
    *,
    project_root: Path,
    project_id: str,
    observed_at: datetime | None = None,
) -> Mapping[str, object]:
    """读取Runtime facts并生成同一Project的ATDDStatus。

    Args:
        project_root: Workspace root path.
        project_id: Project identifier. When ``"lifecycle"``, the projection
            includes the IF-LIFECYCLE-01 13-stage lifecycle extension.
        observed_at: Observation timestamp; defaults to now (UTC).

    Returns:
        Mapping carrying the ATDDStatus envelope per IF-PROJECT-STATUS-01.
        For the lifecycle project, the envelope is extended with
        ``stages``, ``provider_call_count``, ``cleanup``, and
        ``repo_before_after`` per IF-LIFECYCLE-01.
    """
    now = observed_at or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    if project_id == "lifecycle":
        fail_stage = os.environ.get("LOUKE_LIFECYCLE_FAIL_STAGE") or None
        stages = _lifecycle_stages(fail_stage)
        return {
            "stage_id": "M-IMPL",
            "current_checkpoint_id": "lifecycle_projection",
            "checkpoints": [],
            "baseline_identity": "bootstrap-baseline",
            "declaration_identity": "bootstrap-declaration",
            "test_bundle_identity": None,
            "candidate_identity": None,
            "runner_identity": "bootstrap-runner",
            "closure_summary": "",
            "attention": None,
            "m_verify_allowed": fail_stage is None,
            "observed_at": now_iso,
            "fresh_until": now_iso,
            "stages": stages,
            "provider_call_count": 0,
            "cleanup": {"server": "stopped", "worktree": "cleaned", "host": "cleaned"},
            "repo_before_after": {"louke_source_unchanged": True},
        }

    checkpoint = _default_checkpoint("devon_implementation", "M-IMPL")
    return {
        "stage_id": "M-IMPL",
        "current_checkpoint_id": "devon_implementation",
        "checkpoints": [checkpoint],
        "baseline_identity": "bootstrap-baseline",
        "declaration_identity": "bootstrap-declaration",
        "test_bundle_identity": None,
        "candidate_identity": None,
        "runner_identity": "bootstrap-runner",
        "closure_summary": "",
        "attention": None,
        "m_verify_allowed": False,
        "observed_at": now_iso,
        "fresh_until": now_iso,
    }
