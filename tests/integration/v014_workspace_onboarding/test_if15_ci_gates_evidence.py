"""IF-15: CI gates and evidence contract.

AC-FR1501-01, AC-NFR0501-01

Integration tests verify that the CI traceability tool discovers v0.14-004
AC references in the integration test directory, and that the agent
boundary enforcement prevents Maestro from being created as a new agent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


from louke.web.agent_boundaries import can_create_agent, session_kind

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The locked v0.14-004 integration contract-test closed set. These are the
#: real ``test_ac_*`` files that carry the spec's AC coverage (the retired
#: ``test_if01..14`` six-step Wizard tests are withdrawn and deliberately
#: excluded). ``test_if15`` validates this set is present, AC-bearing, and
#: actually executable.
EXPECTED_AC_CLOSED_SET: frozenset[str] = frozenset(
    {
        "test_ac_fr0001__if_web01_setup_gate.py",
        "test_ac_fr0101_0301_0201__if_setup01_02_03.py",
        "test_ac_fr0401_0501__if_project01_guide01.py",
        "test_ac_fr0601_0701_0801__if_env01_02.py",
        "test_ac_fr0901_1001_1101_1501__if_draft_preview_create_identity.py",
        "test_ac_fr1201_1301_1401__if_status_attempt_return_doc.py",
        "test_ac_fr1501_nfr01_04__if_compat_audit.py",
        "test_ac_nfr0001_0201__persistence_freshness.py",
        "test_ac_nfr0201_02__diagnostic_quality.py",
        "test_ac_nfr0301_02__focus_reachability.py",
        "test_ac_synthetic_host__isolation.py",
        "test_ac_wiring__setup_gate_in_create_app.py",
    }
)


def test_maestro_cannot_be_created_as_new_agent():
    """AC-FR1501-01: Maestro cannot be created as a new specialist agent."""
    # AC-FR1501-01
    assert can_create_agent("maestro") is False


def test_guide_cannot_be_created_as_new_agent():
    """AC-FR1501-01: Guide cannot appear as a new agent in Agent picker."""
    # AC-FR1501-01
    assert can_create_agent("guide") is False


def test_specialist_agent_can_be_created():
    """AC-FR1501-01: specialist agents like Scribe, Archer, Devon can be created."""
    # AC-FR1501-01
    assert can_create_agent("Scribe") is True
    assert can_create_agent("Archer") is True
    assert can_create_agent("Devon") is True


def test_historical_maestro_is_read_only():
    """AC-FR1501-01: historical Maestro session is read-only."""
    # AC-FR1501-01
    kind, read_only = session_kind("Maestro", historical=True)
    assert kind == "historical_maestro"
    assert read_only is True


def test_specialist_agent_session_kind():
    """AC-FR1501-01: specialist agent has correct session kind."""
    # AC-FR1501-01
    kind, read_only = session_kind("scribe", historical=False)
    assert kind == "specialist_agent"


def test_integration_tests_have_ac_references():
    """AC-NFR0501-01: the v0.14-004 ``test_ac_*`` closed set is exact and fail-closed.

    Replaces the retired ``len(test_if*.py) >= 14`` file-count check. The gate
    now fails closed:

    * the on-disk ``test_ac_*`` basenames must equal the locked closed set
      exactly (rejects both missing and extra files);
    * every file carries an AC reference;
    * the collected node IDs bind to the closed set (zero collection fails);
    * the executed run binds to the collected count and rejects any
      skip / xfail / setup / service / permission error. ATDD RED assertion
      failures are allowed (Devon has not shipped the production surface yet).
    """
    # AC-NFR0501-01
    test_dir = REPO_ROOT / "tests" / "integration" / "v014_workspace_onboarding"
    py_files = sorted(test_dir.glob("test_ac_*.py"))
    basenames = {p.name for p in py_files}

    # Closed set: basename EXACT equality (rejects missing AND extra files).
    assert basenames == EXPECTED_AC_CLOSED_SET, (
        "AC-NFR0501-01: test_ac_* closed set mismatch; "
        f"missing={sorted(EXPECTED_AC_CLOSED_SET - basenames)}, "
        f"extra={sorted(basenames - EXPECTED_AC_CLOSED_SET)}"
    )

    # Every contract test carries an AC reference.
    for f in py_files:
        content = f.read_text(encoding="utf-8")
        assert "AC-FR" in content or "AC-NFR" in content, (
            f"AC-NFR0501-01: {f.name} carries no AC reference"
        )

    file_args = [str(p) for p in py_files]

    # Phase 1 — collect: bind collected node IDs to the closed set; fail closed
    # on zero collection.
    collect = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *file_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    assert collect.returncode == 0, (
        "AC-NFR0501-01: collection failed "
        f"(rc={collect.returncode}):\n{collect.stdout}\n{collect.stderr}"
    )
    collected_nodes = [
        line.strip() for line in collect.stdout.splitlines() if "::" in line
    ]
    assert collected_nodes, "AC-NFR0501-01: zero tests collected (fail-closed)"
    collected_basenames = {
        node.split("::")[0].rsplit("/", 1)[-1] for node in collected_nodes
    }
    assert collected_basenames == EXPECTED_AC_CLOSED_SET, (
        "AC-NFR0501-01: collected node IDs do not bind to the closed set; "
        f"collected={sorted(collected_basenames)}"
    )

    # Phase 2 — execute: bind executed results to the collected count; reject
    # skip / xfail / setup / service / permission errors. ATDD RED assertion
    # failures (pytest exit 1) are allowed.
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            *file_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,
    )
    out = run.stdout + "\n" + run.stderr
    # Fail closed on infrastructure outcomes: interrupted(2), internal(3),
    # usage(4), no-collection(5).
    assert run.returncode not in (2, 3, 4, 5), (
        "AC-NFR0501-01: pytest infrastructure failure "
        f"(rc={run.returncode}):\n{out[-800:]}"
    )
    # Parse the summary line counts.
    summary_lines = [line for line in run.stdout.splitlines() if line.strip()]
    summary_line = summary_lines[-1] if summary_lines else ""
    counts = {
        label: int(num)
        for num, label in re.findall(
            r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?|deselected)",
            summary_line,
        )
    }
    assert counts.get("skipped", 0) == 0, (
        f"AC-NFR0501-01: skips are not allowed: {counts!r} :: {summary_line!r}"
    )
    assert counts.get("xfailed", 0) == 0 and counts.get("xpassed", 0) == 0, (
        f"AC-NFR0501-01: xfail is not allowed: {counts!r} :: {summary_line!r}"
    )
    assert counts.get("error", 0) == 0 and counts.get("errors", 0) == 0, (
        "AC-NFR0501-01: setup/service/permission errors are not allowed: "
        f"{counts!r} :: {summary_line!r}"
    )
    executed = counts.get("passed", 0) + counts.get("failed", 0)
    assert executed == len(collected_nodes), (
        "AC-NFR0501-01: executed count does not bind to collected node IDs: "
        f"executed={executed}, collected={len(collected_nodes)}, {counts!r}"
    )
    assert executed > 0, "AC-NFR0501-01: zero tests executed (fail-closed)"


def test_traceability_tool_finds_v014_004_acs():
    """AC-NFR0501-01: traceability scanner closes v0.14-004 ACs within the spec scope.

    The locked Acceptance baseline contains 44 unique ACs. The gate is scoped
    to v0.14-004's own integration + e2e test directories (multi-root
    ``--tests``) so cross-spec AC tokens cannot mask a coverage gap in this
    spec. Every AC requires at least integration coverage (test-plan §7.2),
    so scoping to integration + e2e still exercises all 44 ACs.
    """
    # AC-NFR0501-01
    acceptance = (
        REPO_ROOT
        / ".louke/project/specs/v0.14-004-workspace-onboarding-workflow-status/acceptance.md"
    )
    result = subprocess.run(
        [
            sys.executable,
            "tools/check_ac_traceability.py",
            "--acceptance",
            str(acceptance),
            "--tests",
            "tests/integration/v014_workspace_onboarding",
            "tests/e2e/v014_workspace_onboarding",
            "--expected-count",
            "44",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"traceability scan failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "44/44 covered" in result.stdout
