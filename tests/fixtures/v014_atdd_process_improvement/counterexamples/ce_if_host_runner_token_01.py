"""IF-HOST-RUNNER-01: IF-token drift counterexample."""

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
    """负样本：去掉 IF-token。"""
    raise NotImplementedError("missing contract anchor")
