"""IF-HOST-RUNNER-01: project-local required suite执行公开骨架。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def execute_host_tests(
    *,
    project_root: Path,
    contract_path: Path,
    bundle_path: Path,
    phase: str,
    candidate_identity: str,
    evidence_path: Path,
) -> Mapping[str, object]:
    """按宿主合同执行测试并规范化公开evidence。"""
    raise NotImplementedError("IF-HOST-RUNNER-01")
