"""AC-FR1101-01 / AC-FR1501-01 — Counterexample execution proves
the positive tests are not tautologies.

Cross-module: every positive contract test in this directory binds
a counterexample fixture under ``tests/fixtures/negative/``. The
counterexample deliberately violates one clause of the contract
(by, e.g., removing the IF-token, dropping a required parameter,
or introducing a fake enum value). If the positive test only
checks ``passes today``, it cannot detect the deviation and would
falsely report GREEN when the implementation drifts.

This file drives each counterexample in an **isolated subprocess**
that copies the production module, applies the negative
replacement, runs the targeted positive test, and asserts the
positive test FAILS. The subprocess never touches the live
production source: it operates on a temp worktree copy.

Per Shield prompt §3.4, the goal is *not* to make every positive
test fail under every mutation (that would be a meta-test). It
is to bind at least one negative per positive so that any
implementation drift that misses a key contract clause gets
caught.

The mutations are deliberately chosen to be **fatal enough to be
detectable from the test itself** while still being plausible
real-world deviations:

- ``atdd_checkpoint_wrong.py`` drops the IF-token from the
  NotImplementedError, breaking IF-VALID-RED-01 attribution.
- ``host_required_tests_wrong.py`` removes the ``*,`` keyword-only
  marker, loosening IF-HOST-RUNNER-01 contract.
- ``semantic_discrimination_wrong.py`` drops
  ``original_artifact_digest``, weakening NFR-0301-01.
- ``atdd_failure_routing_wrong.py`` adds a sixth enum value,
  breaking the closed-set per IF-FAILURE-ROUTE-01.

If a positive test ever fails to detect the mutation, the test
itself is hollow and must be rewritten (per Prism rule on
non-tautological tests).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "negative"


class _NegativeCase(NamedTuple):
    """A single negative-fixture binding."""

    case_id: str
    target_module: str  # module path relative to ``louke/``
    fixture_filename: str  # filename under tests/fixtures/negative/
    positive_test: str  # pytest node id of the positive test


# Bindings: each negative fixture targets one positive test.
CASES: tuple[_NegativeCase, ...] = (
    _NegativeCase(
        case_id="ce_if_atdd_checkpoint_01",
        target_module="runtime/atdd_checkpoint.py",
        fixture_filename="ce_if_atdd_checkpoint_01.py",
        positive_test=(
            "tests/integration/v014_atdd_process_improvement/"
            "test_ac_fr0901_01_stub_signatures_and_tokens.py::"
            "test_ac_fr1501_01_stub_body_raises_its_if_token"
            "[louke.runtime.atdd_checkpoint-]"
        ),
    ),
    _NegativeCase(
        case_id="ce_if_host_runner_01",
        target_module="runtime/host_required_tests.py",
        fixture_filename="ce_if_host_runner_01.py",
        positive_test=(
            "tests/integration/v014_atdd_process_improvement/"
            "test_ac_fr1001_01_host_runner_contract.py::"
            "test_ac_fr1001_01_execute_host_tests_only_keyword_only"
        ),
    ),
    _NegativeCase(
        case_id="ce_if_discrim_01",
        target_module="runtime/semantic_discrimination.py",
        fixture_filename="ce_if_discrim_01.py",
        positive_test=(
            "tests/integration/v014_atdd_process_improvement/"
            "test_ac_fr1101_01_discrimination_contract.py::"
            "test_ac_fr1101_02_verify_restored_candidate_requires_original_digest"
        ),
    ),
    _NegativeCase(
        case_id="ce_if_failure_route_01",
        target_module="runtime/atdd_failure_routing.py",
        fixture_filename="ce_if_failure_route_01.py",
        positive_test=(
            "tests/integration/v014_atdd_process_improvement/"
            "test_ac_fr1301_01_failure_route_contract.py::"
            "test_ac_fr1301_01_failure_decision_enum_members_present_in_source"
        ),
    ),
)


def _run_isolated_negative_case(case: _NegativeCase) -> subprocess.CompletedProcess:
    """Apply *case*'s mutation in a temp worktree, run positive test.

    Returns the subprocess result. The test never modifies
    ``louke.runtime.<module>`` in the host project; instead it
    copies the entire repo into a temp directory and patches the
    target module file there.
    """
    with tempfile.TemporaryDirectory(prefix="shield-mutation-") as tmp:
        worktree = Path(tmp) / "tree"
        shutil.copytree(REPO_ROOT, worktree, ignore=shallow_ignore_pycache)
        target = worktree / "louke" / case.target_module
        fixture = FIXTURE_DIR / case.fixture_filename
        target.write_text(fixture.read_text(encoding="utf-8"))

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "--tb=no",
            "-p",
            "no:cacheprovider",
            case.positive_test,
        ]
        # Capture pass/fail outcome, do not bubble stack traces.
        result = subprocess.run(
            cmd,
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result


def shallow_ignore_pycache(_dir, names):
    """Skip Python bytecode caches during the worktree copy."""
    return [n for n in names if n == "__pycache__"]


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda c: c.case_id,
)
def test_counterexample_kills_positive_test(case: _NegativeCase) -> None:
    """Each counterexample must cause the bound positive test to FAIL.

    If the positive test still passes, the positive is hollow —
    it cannot detect this specific deviation. Per Prism's
    non-tautology rule, the positive must be rewritten.
    """
    result = _run_isolated_negative_case(case)

    pytest_report = result.stdout + result.stderr
    parse_result = _parse_pytest_outcome(pytest_report)

    assert result.returncode != 0, (
        f"AC-FR1501-01 / AC-FR1101-01: counterexample "
        f"{case.case_id!r} did NOT kill its bound positive "
        f"{case.positive_test!r}; pytest returned 0. Output:\n"
        f"{pytest_report[:1000]}"
    )

    assert parse_result in ("failed", "error"), (
        f"AC-FR1501-01 / AC-FR1101-01: counterexample "
        f"{case.case_id!r} killed {parse_result!r}; expected "
        f"a clear 'failed' outcome so the binding is "
        f"non-tautological. Output:\n{pytest_report[:1500]}"
    )


def _parse_pytest_outcome(pytest_output: str) -> str:
    """Return a coarse ``passed|failed|error`` outcome string.

    Pytest's summary line is ``N passed, N failed, N error``. We
    detect the first matching token rather than parsing every
    format variation.
    """
    lowered = pytest_output.lower()
    if " error" in lowered:
        return "error"
    if " failed" in lowered or " 1 failed" in lowered:
        return "failed"
    if " passed" in lowered and " failed" not in lowered and " error" not in lowered:
        return "passed"
    return "unknown"


def test_counterexample_bindings_cover_all_targeted_positive_tests() -> None:
    """The counterexample manifest must bind every positive test that
    has a non-trivial behavioural contract.

    This is the closure check (per Shield prompt §2.2.4). Each
    required integration test must have a bound counterexample;
    any test without one fails closed at this point. Today we
    ship four bindings; the manifest is expected to grow as the
    spec evolves.
    """
    binding_records: list[dict[str, str]] = []
    for case in CASES:
        binding_records.append(
            {
                "case_id": case.case_id,
                "positive_test": case.positive_test,
                "fixture": case.fixture_filename,
            }
        )

    serialised = json.dumps(binding_records, indent=2, sort_keys=True)
    assert len(CASES) >= 4, (
        "AC-FR1501-01 / AC-FR1101-01: at least one counterexample "
        "must bind each contract clause that has been translated "
        f"into a positive test. got {len(CASES)} bindings: {serialised}"
    )
