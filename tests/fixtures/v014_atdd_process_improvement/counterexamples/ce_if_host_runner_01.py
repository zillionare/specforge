"""IF-HOST-RUNNER-01: project-local required suite执行公开骨架（COUNTEREXAMPLE）。"""

from __future__ import annotations

from collections.abc import Mapping


def execute_host_tests(
    project_root,  # 负样本：去掉 keyword-only marker
    contract_path,
    bundle_path,
    phase,
    candidate_identity,
    evidence_path,
) -> Mapping[str, object]:
    """负样本：去掉 keyword-only 标记，使 FR-1001-01 keyword-only 测试失败。"""
    raise NotImplementedError("IF-HOST-RUNNER-01")
