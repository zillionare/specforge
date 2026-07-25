"""AC-NFR0001-01 / AC-NFR0201-01 / AC-NFR0301-01 — Host-neutral, evidence integrity, safety.

Cross-module: ``Runtime Facts`` × ``External Stand-ins`` ×
``CI/Traceability``.

These NFRs bind meta-rules that span every layer. We test them by:
* requiring host-neutral discovery (no language-extension sniffing);
* requiring evidence envelopes carry the documented minimum identity
  fields with stable digests;
* requiring isolation guarantees on the candidate/control directories
  for replay/counterexample work.

Each test reads the actual ``interfaces.md`` text or the actual
project.toml / registry / counterexamples directory and asserts a
**concrete** contract outcome. No ``for ... pass`` bodies — every
loop iteration makes an assertion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = (
    REPO_ROOT / ".louke" / "project" / "specs" / "v0.14-005-atdd-process-improvement"
)
INTERFACES_DOC = SPEC_DIR / "interfaces.md"


def _interface_section(token: str) -> str:
    text = INTERFACES_DOC.read_text(encoding="utf-8")
    start = text.find(f"### {token}")
    if start == -1:
        return ""
    end = text.find("\n### ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_ac_nfr0001_01_runner_command_in_project_toml_does_not_specifically_target_python() -> (
    None
):
    """AC-NFR0001-01: the [integration]/[e2e] commands reference the project runner.

    The runner is language-agnostic. Requiring a direct pytest command
    at the project.toml layer would defeat the host-neutral contract.
    """
    text = (REPO_ROOT / ".louke" / "project" / "project.toml").read_text(
        encoding="utf-8"
    )
    # Python-specific commands are forbidden at project.toml layer; the
    # runner script wraps the host toolchain.
    run_lines = re.findall(r"run\s*=\s*\"[^\"]*\"", text)
    for needle in run_lines:
        assert "tests/e2e/run-project-venv" in needle, (
            f"AC-NFR0001-01: project.toml run={needle!r} must use the "
            f"host-local runner wrapper, not a direct language CLI."
        )
    assert "run-project-venv" in text, (
        "AC-NFR0001-01: project.toml must reference the host-local runner."
    )


def test_ac_nfr0201_01_evidence_envelope_minimum_fields_in_interfaces() -> None:
    """AC-NFR0201-01: minimum evidence identity fields are documented.

    interfaces.md IF-EVIDENCE-01 binds the minimum identity envelope.
    Any drift in the field names invalidates every digest over time.
    """
    section = _interface_section("IF-EVIDENCE-01")
    if not section:
        pytest.fail(
            f"AC-NFR0201-01: IF-EVIDENCE-01 section missing from {INTERFACES_DOC}"
        )
    required_fields = (
        "schema_version",
        "evidence_id",
        "kind",
        "qualification",
        "validation_state",
        "workspace_id",
        "project_id",
        "run_id",
        "attempt_id",
        "baseline_identity",
        "candidate_identity",
        "source_revision",
        "test_revision",
        "runner_identity",
        "environment_identity",
        "command",
        "started_at",
        "finished_at",
        "result",
        "reason",
        "artifact_refs",
        "evidence_digest",
    )
    # Each required field must appear in the IF-EVIDENCE-01 section so
    # the contract document binds the envelope shape. We assert one at
    # a time so the failure message names the missing field.
    missing: list[str] = [field for field in required_fields if field not in section]
    assert not missing, (
        f"AC-NFR0201-01: IF-EVIDENCE-01 missing required identity "
        f"fields in {INTERFACES_DOC}: {missing}"
    )


def test_ac_nfr0201_01_bootstrap_qualification_cannot_pass_gates() -> None:
    """AC-NFR0201-01: ``qualification=bootstrap_manual`` cannot unlock any gate.

    interfaces.md IF-EVIDENCE-01 says:
        ``qualification=bootstrap_manual`` 或
        ``validation_state=unvalidated`` 只能显示attention；
        不得解锁正式baseline、Shield/Devon派发、freeze、M-VERIFY或publish。

    This test parses the IF-EVIDENCE-01 ``Bootstrap`` table row and
    asserts each forbidden gate (``baseline``, ``派发``, ``freeze``,
    ``M-VERIFY``, ``publish``) appears in that single row. A
    contract that drops any gate from the row (downgrading the no-go
    list) would break the test.
    """
    section = _interface_section("IF-EVIDENCE-01")
    if not section:
        pytest.fail(
            f"AC-NFR0201-01: IF-EVIDENCE-01 section missing from {INTERFACES_DOC}"
        )

    # The Bootstrap row's text must mention both the qualifier
    # (``bootstrap_manual``) and the list of gates it cannot unlock.
    bootstrap_rows = [
        line
        for line in section.splitlines()
        if line.startswith("|") and "Bootstrap" in line
    ]
    assert bootstrap_rows, (
        "AC-NFR0201-01: IF-EVIDENCE-01 must have a row labelled "
        "'Bootstrap'; got none in the parsed section"
    )
    bootstrap_text = bootstrap_rows[0]
    assert "bootstrap_manual" in bootstrap_text, (
        "AC-NFR0201-01: Bootstrap row must reference "
        f"'bootstrap_manual'; got row={bootstrap_text!r}"
    )

    # Each forbidden gate must appear in the same row, so dropping any
    # gate from the contract surface breaks the test. ``pass`` was a
    # tautology; we now assert each gate is explicitly listed as
    # blocked by bootstrap_manual.
    blocked_gates = ("baseline", "派发", "freeze", "M-VERIFY", "publish")
    missing_gates: list[str] = []
    for gate in blocked_gates:
        if gate not in bootstrap_text:
            missing_gates.append(gate)
    assert not missing_gates, (
        "AC-NFR0201-01: bootstrap_manual must remain unable to "
        f"unlock each of {blocked_gates!r}. Missing from the "
        f"Bootstrap row: {missing_gates!r}"
    )


def test_ac_nfr0301_01_counterexample_path_is_outside_main_tests() -> None:
    """AC-NFR0301-01: counterexamples live under ``tests/fixtures/v014_atdd_process_improvement/counterexamples/``.

    A counterexample co-located with the test tree would be discovered
    by pytest collection and produce a false RED.
    """
    counterexamples_dir = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "v014_atdd_process_improvement"
        / "counterexamples"
    )
    assert counterexamples_dir.is_dir(), (
        "AC-NFR0301-01: counterexamples must live under "
        "tests/fixtures/v014_atdd_process_improvement/counterexamples/, "
        "outside the integration test tree."
    )
    # The directory must contain at least one ``ce_if_*.py`` patch so
    # the binding between tests and counterexamples is non-vacuous.
    ce_files = sorted(counterexamples_dir.glob("ce_if_*.py"))
    assert ce_files, (
        "AC-NFR0301-01: counterexamples dir must contain at least "
        "one ce_if_*.py patch — an empty dir passes the is_dir() "
        "check without exercising the contract."
    )


def test_ac_nfr0301_01_lifecycle_harness_uses_temp_dirs() -> None:
    """AC-NFR0301-01: lifecycle harness materialises wordcount host + control in temp dirs.

    interfaces.md IF-LIFECYCLE-01 states:
        wordcount源码/生成artifact只在temp host，scenario/replay资产只在独立temp control

    Both phrases (``temp host`` and ``temp control``) must appear in
    the IF-LIFECYCLE-01 section, so removing either isolation
    requirement breaks the test. The previous ``for ... pass`` loop
    was vacuous.
    """
    section = _interface_section("IF-LIFECYCLE-01")
    if not section:
        pytest.fail(
            f"AC-NFR0301-01: IF-LIFECYCLE-01 section missing from {INTERFACES_DOC}"
        )

    # Assert each isolation phrase appears in the section. We assert
    # one at a time so the failure message names the missing phrase.
    required_phrases = ("temp host", "temp control")
    missing_phrases: list[str] = []
    for phrase in required_phrases:
        if phrase not in section:
            missing_phrases.append(phrase)
    assert not missing_phrases, (
        f"AC-NFR0301-01: IF-LIFECYCLE-01 must enumerate both "
        f"isolation phrases {required_phrases!r}; missing: "
        f"{missing_phrases!r}"
    )

    # Cross-check: the Isolation/teardown row of IF-LIFECYCLE-01
    # restates the contract. Its cells must contain both phrases.
    isolation_row = next(
        (
            line
            for line in section.splitlines()
            if line.startswith("|") and "Isolation" in line
        ),
        "",
    )
    if isolation_row:
        for phrase in required_phrases:
            assert phrase in isolation_row, (
                f"AC-NFR0301-01: IF-LIFECYCLE-01 Isolation/teardown "
                f"row must mention {phrase!r}; got row="
                f"{isolation_row!r}"
            )


def test_ac_nfr0201_01_registry_candidate_explicitly_blocks_activation_state_active() -> (
    None
):
    """AC-NFR0201-01: registry explicit activation_state is candidate, never active.

    A drift from ``candidate`` to ``active`` would deploy an
    unverified contract, breaking NFR-0201.
    """
    registry_path = (
        REPO_ROOT
        / ".louke"
        / "project"
        / "contracts"
        / "v0.14-005-atdd-process-improvement"
        / "registry.candidate.json"
    )
    parsed = json.loads(registry_path.read_text(encoding="utf-8"))
    assert parsed.get("activation_state") == "candidate", (
        f"AC-NFR0201-01: registry activation_state must be 'candidate' "
        f"prior to atomic activation, got {parsed.get('activation_state')!r}"
    )
    assert parsed.get("owner") == "Runtime/program", (
        "AC-NFR0201-01: registry owner must be Runtime/program, not any Agent"
    )
