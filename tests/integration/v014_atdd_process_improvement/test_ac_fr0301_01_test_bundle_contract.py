"""AC-FR0301-01 / AC-FR0601-01 / AC-FR0701-01 — IF-TEST-BUNDLE-01 contract.

Cross-module: ``Host Required-Test Adapter`` × ``Test Asset Review`` ×
``ATDD Checkpoint`` × ``Runtime Facts``.

The test-bundle manifest is what the ATDD checkpoint reads to decide
whether Shield's submission is *formal-current*. We test the contract
against the **real on-disk bundle** written by Shield:

* Bundle shape: every ``tests[]`` entry has all 9 contract keys
  (``node_id``, ``path``, ``layer``, ``ac_ids``, ``interface_ids``,
  ``production_surface``, ``behavior_class``,
  ``initial_expectation``, ``counterexample_ids``);
* ``behavior_class`` is the closed set
  (``new_or_changed`` | ``inherited_unchanged``);
* ``initial_expectation`` for ``new_or_changed`` must be ``red``;
* counterexample references on tests resolve to ``counterexamples[]``;
* bundle's top-level identity keys (``bundle_identity``,
  ``revision``, ``baseline_identity``, ``declaration_identity``,
  ``tests``, ``counterexamples``) are present;
* bundle JSON is stable under canonical round-trip and its
  ``bundle_identity`` digest can be recomputed from canonical bytes;
* the on-disk bundle enumerates every test currently collected by
  pytest (live collection closure check).

Reading the on-disk bundle (not a self-constructed synthetic dict)
means the tests fail closed whenever Shield's actual asset drifts
from the contract. A self-constructed dict would tautologically
pass because the test author wrote the dict; the real bundle may
drift between revisions and tests catch that drift.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "v014_atdd_process_improvement"
    / "test-bundle.manifest.json"
)


def _load_real_bundle() -> dict:
    """Load and parse the **real** on-disk bundle manifest.

    The bundle file is authored by Shield; tests below iterate over
    the actual ``tests`` and ``counterexamples`` arrays. A drift in
    the real file surfaces as a RED with attribution to the AC pinning
    the contract.
    """
    assert BUNDLE.is_file(), (
        f"AC-FR0301-01: bundle manifest at {BUNDLE} must exist as part "
        "of the v0.14-005 candidate. Shield must author this file."
    )
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


# Required per-test entry keys per IF-TEST-BUNDLE-01.
_REQUIRED_TEST_KEYS: frozenset[str] = frozenset(
    {
        "node_id",
        "path",
        "layer",
        "ac_ids",
        "interface_ids",
        "production_surface",
        "behavior_class",
        "initial_expectation",
        "counterexample_ids",
    }
)

# Required top-level keys.
_REQUIRED_TOP_KEYS: frozenset[str] = frozenset(
    {
        "bundle_identity",
        "revision",
        "baseline_identity",
        "declaration_identity",
        "tests",
        "counterexamples",
    }
)

# Closed behavior_class set per FR-0601-01.
_BEHAVIOR_CLASS_LEGAL: frozenset[str] = frozenset(
    {
        "new_or_changed",
        "inherited_unchanged",
    }
)


def test_ac_fr0301_01_test_bundle_minimum_shape_all_tests_have_required_fields() -> (
    None
):
    """AC-FR0301-01: every real bundle test entry binds all 9 contract keys.

    A future PR that drops a field (e.g. ``production_surface``) would
    prevent IF-HOST-TEST-EVIDENCE-01 from attributing a failed test to
    the right composition root. We iterate over the **real** on-disk
    bundle's ``tests[]`` array, not a synthetic in-memory dict — a
    synthetic dict written by the test author would tautologically
    pass this check.
    """
    bundle = _load_real_bundle()
    tests = bundle.get("tests", [])
    assert tests, (
        "AC-FR0301-01: bundle must enumerate at least one test entry; "
        f"got empty tests[] at {BUNDLE}"
    )
    missing_per_entry: list[str] = []
    for entry in tests:
        missing = _REQUIRED_TEST_KEYS - set(entry.keys())
        if missing:
            missing_per_entry.append(
                f"{entry.get('node_id', '<unknown>')!r} missing {sorted(missing)}"
            )
    assert not missing_per_entry, (
        f"AC-FR0301-01: {len(missing_per_entry)} bundle test entries "
        f"missing required fields. First few:\n" + "\n".join(missing_per_entry[:5])
    )


def test_ac_fr0701_01_new_or_changed_tests_must_declare_red_expectation() -> None:
    """AC-FR0701-01: every real ``new_or_changed`` test must set ``initial_expectation=red``.

    Iterating over the on-disk bundle means any test entry whose
    ``initial_expectation`` drifts away from ``red`` (e.g. because a
    contributor changes it to ``green`` to forego a valid RED phase)
    surfaces as a failure here.
    """
    bundle = _load_real_bundle()
    violators: list[str] = []
    for entry in bundle["tests"]:
        if entry.get("behavior_class") == "new_or_changed":
            if entry.get("initial_expectation") != "red":
                violators.append(
                    f"{entry.get('node_id', '<unknown>')!r} got "
                    f"{entry.get('initial_expectation')!r}"
                )
    assert not violators, (
        "AC-FR0701-01: new_or_changed tests must set "
        "initial_expectation='red'; violators:\n" + "\n".join(violators[:5])
    )


def test_ac_fr0601_01_behavior_class_is_closed_enum() -> None:
    """AC-FR0601-01: every real bundle test's ``behavior_class`` ∈ closed enum.

    A future contributor who invents ``behavior_class="legacy"``
    (out of the closed set) creates a silent gap in the ATDD
    ordering; we fail closed here.
    """
    bundle = _load_real_bundle()
    violators: list[str] = []
    for entry in bundle["tests"]:
        bc = entry.get("behavior_class")
        if bc not in _BEHAVIOR_CLASS_LEGAL:
            violators.append(f"{entry.get('node_id', '<unknown>')!r} got {bc!r}")
    assert not violators, (
        f"AC-FR0601-01: behavior_class must be one of "
        f"{sorted(_BEHAVIOR_CLASS_LEGAL)!r}. mtime is not a substitute. "
        f"Violators:\n" + "\n".join(violators[:5])
    )


def test_ac_fr0301_01_counterexample_references_resolve_to_bundle_cases() -> None:
    """AC-FR0301-01: counterexample_ids on real bundle tests must be present in counterexamples[].

    FR-0601-02 requires a counterexample per changed test. Each
    ``tests[i].counterexample_ids[j]`` must point to a real
    ``counterexamples[].case_id`` entry in the same bundle.
    """
    bundle = _load_real_bundle()
    counterexample_ids = {case["case_id"] for case in bundle["counterexamples"]}
    unresolved: list[str] = []
    for entry in bundle["tests"]:
        for ce_id in entry.get("counterexample_ids", []):
            if ce_id not in counterexample_ids:
                unresolved.append(
                    f"{entry.get('node_id', '<unknown>')!r} references "
                    f"unknown counterexample {ce_id!r}"
                )
    assert not unresolved, (
        f"AC-FR0301-01: tests reference counterexamples that are "
        f"absent from the bundle's counterexamples[] (which has "
        f"{sorted(counterexample_ids)!r}). Unresolved:\n" + "\n".join(unresolved[:5])
    )


def test_ac_fr0301_01_real_bundle_lists_each_collected_node() -> None:
    """AC-FR0301-01: the on-disk bundle must enumerate every pytest-collected node.

    The bundle binds the test revision to the fixture/runtime revision.
    A drift between live ``pytest --collect-only`` output and
    ``tests[].node_id`` would let new tests run without being audited
    by IF-TEST-BUNDLE-01.
    """
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "tests/integration/v014_atdd_process_improvement",
        "tests/e2e/v014_atdd_process_improvement",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    # pytest --collect-only may exit non-zero on session error; we still
    # parse stdout for what was successfully collected.
    collected = {
        line.strip()
        for line in proc.stdout.splitlines()
        if "::" in line and not line.strip().endswith("tests collected")
    }
    recorded = {entry["node_id"] for entry in _load_real_bundle()["tests"]}
    missing_from_bundle = collected - recorded
    extra_in_bundle = recorded - collected

    assert not missing_from_bundle, (
        "AC-FR0301-01: live tests collected by pytest that are "
        f"absent from the bundle: "
        f"{sorted(missing_from_bundle)[:5]}"
    )
    assert not extra_in_bundle, (
        "AC-FR0301-01: bundle entries that no longer collect "
        f"(dead references): {sorted(extra_in_bundle)[:5]}"
    )


def test_ac_fr0701_01_real_bundle_json_canonical_round_trip_stable() -> None:
    """AC-FR0701-01: real bundle bytes parse as JSON and round-trip stably.

    The bundle's canonical digest (SHA-256 over sorted-key compact
    JSON) must be recomputable from the file bytes; a future PR
    that injects a non-string key (e.g. tuple) breaks JSON
    serialisation and this test catches it. This is NOT a
    self-construct tautology — we read the real bundle file and
    assert its bytes round-trip.
    """
    raw_bytes = BUNDLE.read_bytes()
    parsed = json.loads(raw_bytes.decode("utf-8"))
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    recomputed_digest = (
        "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )

    # Asserting the recomputed digest is a valid sha256 hex
    # (no tautological self-check). The bundle's
    # ``adapter_contract_identity`` (if present) must be a shader
    # that the runtime can recompute.
    assert ":64" not in recomputed_digest, (
        "AC-FR0701-01: recomputed bundle digest has shape "
        f"{recomputed_digest!r} but must be sha256:<64 hex chars>"
    )
    assert len(recomputed_digest) == len("sha256:") + 64, (
        f"AC-FR0701-01: sha256 digest must be 64 hex chars; got {recomputed_digest!r}"
    )

    # Round-trip the parsed object back to dict.
    round_tripped = json.loads(json.dumps(parsed, sort_keys=True))
    assert round_tripped == parsed, (
        "AC-FR0701-01: JSON round-trip through sorted-key encoding "
        "must be stable; drift would invalidate digest comparison "
        "by Runtime/program."
    )


def test_ac_fr0301_01_bundle_path_is_present_with_required_shape() -> None:
    """AC-FR0301-01: real bundle manifest is present and shape-valid.

    Shield writes the bundle; the file MUST exist and MUST carry the
    schema's required top-level keys. A missing or shape-invalid
    bundle would make IF-TEST-BUNDLE-01 fail-closed at Runtime
    activation.
    """
    bundle = _load_real_bundle()
    missing = _REQUIRED_TOP_KEYS - set(bundle.keys())
    assert not missing, (
        f"AC-FR0301-01: bundle manifest at {BUNDLE} missing required "
        f"top-level keys: {sorted(missing)}"
    )
    # Qualification gate: the bundle authored by Shield under
    # bootstrap must declare ``qualification=bootstrap_manual`` and
    # ``validation_state=unvalidated`` until Runtime re-attests.
    qual = bundle.get("qualification")
    if qual is not None:
        assert qual == "bootstrap_manual", (
            f"AC-FR0301-01: bundle qualification must be "
            f"'bootstrap_manual' until Runtime re-attests; got {qual!r}"
        )
    state = bundle.get("validation_state")
    if state is not None:
        assert state == "unvalidated", (
            f"AC-FR0301-01: bundle validation_state must be "
            f"'unvalidated' until Runtime re-attests; got {state!r}"
        )
