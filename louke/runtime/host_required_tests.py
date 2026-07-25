"""IF-HOST-RUNNER-01: project-local required suite执行公开骨架。"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from pathlib import Path


class HostTestPhase(enum.Enum):
    """Closed set of host-test lifecycle phases per IF-HOST-RUNNER-01.

    The ``phase`` parameter of :func:`execute_host_tests` must be one of
    these four values; any other value is a contract violation.
    """

    PRE_RED = "pre-red"
    REQUIRED_GREEN = "required-green"
    RESTORED_GREEN = "restored-green"
    CLOSURE = "closure"


def execute_host_tests(
    *,
    project_root: Path,
    contract_path: Path,
    bundle_path: Path,
    phase: str,
    candidate_identity: str,
    evidence_path: Path,
) -> Mapping[str, object]:
    """按宿主合同执行测试并规范化公开evidence。

    Args:
        project_root: Workspace root path.
        contract_path: Path to the host-runner contract JSON.
        bundle_path: Path to the frozen test-bundle manifest JSON.
        phase: One of ``pre-red``, ``required-green``, ``restored-green``,
            ``closure`` (see :class:`HostTestPhase`).
        candidate_identity: Identity of the implementation candidate under test.
        evidence_path: Path to write the normalised IF-HOST-TEST-EVIDENCE-01
            evidence JSON.

    Returns:
        Mapping carrying the normalised evidence envelope.

    Raises:
        NotImplementedError: IF-HOST-RUNNER-01 stub.
    """
    raise NotImplementedError("IF-HOST-RUNNER-01")
