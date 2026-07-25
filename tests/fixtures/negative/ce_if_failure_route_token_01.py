"""IF-FAILURE-ROUTE-01: IF-token drift counterexample."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def classify_atdd_failure(
    *,
    project_root: Path,
    evidence_paths: Sequence[Path],
    contract_paths: Sequence[Path],
    prism_diagnostic_path: Path | None,
    output_path: Path,
) -> Mapping[str, object]:
    """负样本：去掉 IF-token。"""
    raise NotImplementedError("missing contract anchor")
