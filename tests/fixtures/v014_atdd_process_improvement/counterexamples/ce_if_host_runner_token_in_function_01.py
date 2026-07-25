"""IF-HOST-RUNNER-01: token stripped (mutant)."""

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
    """Mutant: raise without contract anchor."""
    raise NotImplementedError("MUTANT_NO_TOKEN")
