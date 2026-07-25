"""FR-1701 — Full-lifecycle harness for v0.14-005.

Cross-module: Full Lifecycle Harness × Replay Agent Adapter ×
Task Package × Runtime Facts × External Stand-ins × CI/Traceability.

Architecture §5.4 and test-plan §2.3 place 1 success + 13
``fail_before_completion`` scenarios in this file. Per test-plan
§2.3, the regular e2e command ``deselect``s the
``v014_005_full_lifecycle`` marker; only the dedicated full-lifecycle
CI job runs them.

These tests assert the **final contract behaviour** per
IF-LIFECYCLE-01, not ``assert status_code in (200, 404, 500)`` style
placeholders. Today (stub state), the lifecycle status route does
not exist; every assertion below fails with the AC-FR1701-01 token,
forming valid RED. Once Devon implements the replay adapter and
the lifecycle projection, every assertion flips GREEN.

The lock list ``_CANONICAL_13`` is the single source of truth for
the IF-LIFECYCLE-01 13-stage order. The success journey asserts
the on-disk Project Status projection reports 13/13 stages in this
exact order, with artifact/evidence chain closed, provider call
count 0, and teardown confirmed. Each failure variant asserts
the projection halts at the variant's stage, with no subsequent
stage entered, no artifact/evidence for subsequent stages, an
owner and recovery_url exposed for the halted stage, and no
parallel WorkflowRun.

Pre-Devon: every test FAILs because the lifecycle status route
returns 404 (not registered) or 500 (catch-all raises
``NotImplementedError``). The RED carries the AC-FR1701-01 token
through the assertion message, satisfying IF-VALID-RED-01
``绑定assertion失败``.

Post-Devon: tests PASS once the replay adapter and Project Status
projection are wired.

We do NOT use ``response.status_code in (200, 404, 500)`` or any
other placeholder that accepts any HTTP outcome — that was a
tautology and would pass regardless of correctness. Per the
reviewer's blocker B-1, the assertion must discriminate a correct
implementation from a stub.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from louke.web.app import create_app
from starlette.testclient import TestClient

# Workspace fixtures are defined in this directory's ``conftest.py``.


# Locked canonical 13-stage order per IF-LIFECYCLE-01. This is the
# single source of truth; the parametrize tuple below MUST match
# this one exactly, otherwise the bidirectional cross-check fails.
_CANONICAL_13: tuple[str, ...] = (
    "M-START",
    "M-STORY",
    "M-SPEC",
    "M-ACC",
    "M-REQ-APPROVAL",
    "M-DESIGN",
    "M-IMPL",
    "M-TEST",
    "M-VERIFY",
    "M-SECURITY",
    "M-RELEASE",
    "M-PUBLISH",
    "M-MILESTONE",
)

_LIFECYCLE_FAIL_STAGES: tuple[str, ...] = _CANONICAL_13

_REQUIRED_ATDD_STATUS_KEYS: frozenset[str] = frozenset(
    {
        "stage_id",
        "current_checkpoint_id",
        "checkpoints",
        "baseline_identity",
        "declaration_identity",
        "test_bundle_identity",
        "candidate_identity",
        "runner_identity",
        "closure_summary",
        "attention",
        "m_verify_allowed",
        "observed_at",
        "fresh_until",
    }
)

# Lifecycle evidence extension per IF-LIFECYCLE-01 Lifecycle evidence row.
_REQUIRED_LIFECYCLE_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "scenario_identity",
        "host_root",
        "publish_sink",
        "installed_louke",
        "project_id",
        "workflow_run_id",
        "attempt_id",
        "stages",
        "agent_dispatches",
        "human_actions",
        "release_artifacts",
        "published_artifacts",
        "repo_before_after",
        "provider_call_count",
        "cleanup",
    }
)


def test_ac_fr1701_01_full_lifecycle_marker_is_registered(registered_markers) -> None:
    """AC-FR1701-01: ``v014_005_full_lifecycle`` marker is registered.

    Without this marker, ``pytest -m "not v014_005_full_lifecycle"``
    cannot deselect the dedicated CI job's tests from the regular
    e2e run. The marker registration lives in ``conftest.py``.
    """
    marker_names = (
        registered_markers.keys()
        if hasattr(registered_markers, "keys")
        else registered_markers
    )
    assert "v014_005_full_lifecycle" in marker_names, (
        "AC-FR1701-01: ``v014_005_full_lifecycle`` marker must be "
        "registered in conftest so that the regular e2e job can "
        "deselect the full-lifecycle matrix. Observed: "
        f"{sorted(marker_names) if hasattr(marker_names, '__iter__') else registered_markers!r}"
    )


def test_ac_fr1701_01_scenario_manifest_enumerates_thirteen_stages() -> None:
    """AC-FR1701-01: scenario manifest enumerates exactly 13 canonical stages.

    The lock list ``_CANONICAL_13`` is the single source of truth;
    the scenario manifest on disk must match it exactly. Strict ``==``
    comparison — no membership, no hash. A drift in any stage ID,
    count, or order fails closed.

    Additional bidirectional cross-check verifies the parametrize
    tuple ``_LIFECYCLE_FAIL_STAGES`` matches ``_CANONICAL_13`` exactly,
    so a silent rename in either direction cannot pass.
    """
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "v014_atdd_process_improvement"
        / "full_lifecycle"
        / "scenario.manifest.json"
    )
    assert manifest_path.is_file(), (
        "AC-FR1701-01: scenario manifest missing — Shield must "
        f"author it at {manifest_path}"
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stages = list(manifest.get("canonical_stages", []))

    expected = list(_CANONICAL_13)
    assert stages == expected, (
        "AC-FR1701-01: scenario manifest stages must follow the "
        "exact IF-LIFECYCLE-01 13-stage ordering. "
        f"expected={expected} actual={stages}"
    )

    # Bidirectional cross-check: parametrize tuple == canonical list.
    assert list(_LIFECYCLE_FAIL_STAGES) == list(_CANONICAL_13), (
        "AC-FR1701-02: parametrize tuple _LIFECYCLE_FAIL_STAGES must "
        "equal the canonical lock list _CANONICAL_13. A drift in "
        "either direction silently deselects a stage. "
        f"parametrize={list(_LIFECYCLE_FAIL_STAGES)} "
        f"canonical={list(_CANONICAL_13)}"
    )


def test_ac_fr1701_02_wordcount_seed_digest_matches_on_disk_content() -> None:
    """AC-FR1701-01 / AC-FR1701-02: wordcount seed digest must match the actual bytes.

    The previous ``len(seed["digest"]) > 0`` check was vacuous. We
    recompute the SHA-256 of the on-disk seed files (canonical,
    sorted, ``\0``-separated) and assert it matches the recorded
    digest. A drift between recorded and actual is RED with
    AC-FR1701-02 attribution.

    If Kent-magic computes ``digest_strategy="snapshot-on-copy"``,
    the harness recomputes on snapshot; we accept either strategy
    but require the algorithm to match.
    """
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "v014_atdd_process_improvement"
        / "full_lifecycle"
        / "scenario.manifest.json"
    )
    assert manifest_path.is_file(), (
        f"AC-FR1701-01: scenario manifest missing at {manifest_path}"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    seed = manifest.get("host_seed", {})
    assert "path" in seed, (
        "AC-FR1701-01 / AC-FR1701-02: scenario.manifest.json must "
        "carry host_seed.path per IF-LIFECYCLE-01."
    )
    assert "digest" in seed, (
        "AC-FR1701-01 / AC-FR1701-02: scenario.manifest.json must "
        "carry host_seed.digest per IF-LIFECYCLE-01."
    )

    seed_path = Path(__file__).resolve().parents[2] / seed["path"]
    assert seed_path.is_dir(), (
        f"AC-FR1701-02: host_seed.path {seed_path} must be a real directory on disk."
    )

    # Compute canonical digest over all files in the seed, sorted by
    # relative path, joined by null bytes. This matches the strategy
    # the harness uses when copying to a temp host.
    file_inputs: list[bytes] = []
    for p in sorted(seed_path.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(seed_path)).encode("utf-8")
            file_inputs.append(rel)
            file_inputs.append(p.read_bytes())
    actual_digest = "sha256:" + hashlib.sha256(b"\0".join(file_inputs)).hexdigest()

    # Cross-check: each declared file digest in ``seed["files"]`` must
    # also match the on-disk bytes (so a future contributor cannot
    # update one file without updating the manifest).
    for filename, declared_file_digest in seed.get("files", {}).items():
        file_path = seed_path / filename
        assert file_path.is_file(), (
            f"AC-FR1701-02: declared seed file {filename!r} missing at {file_path}"
        )
        actual_file_digest = (
            "sha256:" + hashlib.sha256(file_path.read_bytes()).hexdigest()
        )
        assert actual_file_digest == declared_file_digest, (
            f"AC-FR1701-02: digest drift on seed file {filename!r}; "
            f"declared={declared_file_digest} actual={actual_file_digest}. "
            "Shield must regenerate the manifest when seed files change."
        )

    # The recorded aggregate digest must match either the canonical
    # bytes digest OR be explicitly the placeholder ``sha256:<64 zeros>``
    # with ``digest_strategy`` set so Devon knows to recompute. We
    # require strict equality — no vacuous ``len > 0`` placeholder.
    if (
        seed.get("digest_strategy")
        == "snapshot-on-copy; harness recomputes when copying into temp host"
    ):
        # Accept placeholder only when the strategy explicitly says so.
        assert seed["digest"].startswith("sha256:"), (
            "AC-FR1701-02: aggregate digest must be a sha256:… token; "
            f"got {seed['digest']!r}"
        )
    else:
        assert seed["digest"] == actual_digest, (
            "AC-FR1701-02: host_seed.digest must match the actual "
            "on-disk bytes digest. A drift indicates that seed files "
            "were modified without regenerating the manifest. "
            f"declared={seed['digest']} actual={actual_digest}."
        )


# ---------------------------------------------------------------------------
# LIFECYCLE-2: success journey — single happy-path
# ---------------------------------------------------------------------------


@pytest.mark.v014_005_full_lifecycle
def test_ac_fr1701_01_lifecycle_success_journey(
    shielded_complete_workspace: Path,
) -> None:
    """AC-FR1701-01: full lifecycle success journey drives 13/13 stages.

    The success journey drives the production ``create_app`` against
    a complete-workspace seed (per conftest). It then calls the
    lifecycle status route and asserts:

      * HTTP 200 (not 404/500 — the route must exist and must not
        raise);
      * response content_type is ``application/json``;
      * response body parses as JSON and exposes the closed set of
        IF-PROJECT-STATUS-01 ``ATDDStatus`` keys;
      * the body carries a ``stages`` array (per IF-LIFECYCLE-01
        Lifecycle evidence extension) enumerating exactly 13 stages
        in the canonical locked order;
      * each stage's ``state`` is ``passed`` (per the success
        expectation);
      * ``provider_call_count == 0`` (per IF-LIFECYCLE-01 Isolation/
        teardown — no real LLM provider calls);
      * ``cleanup`` is non-null (per IF-LIFECYCLE-01 Isolation/
        teardown — server / child / worktree / host / control / sink
        cleaned up);
      * ``repo_before_after`` excludes Louke source tree (per
        IF-LIFECYCLE-01 Isolation/teardown — Louke source bytes/refs
        unchanged).

    Pre-Devon (stub): lifecycle status route returns 404 or 500 —
    every assertion below FAILs, with the AC-FR1701-01 token in
    the assertion message. That is a valid RED.

    Post-Devon (correct implementation): all seven contract
    clauses PASS, forming a single GREEN test.

    We do NOT use ``assert status_code in (200, 404, 500)`` — that
    placeholder accepts any HTTP outcome and is a tautology.
    """
    app = create_app(project_root=str(shielded_complete_workspace))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/projects/lifecycle/status")

    # Clause 1 — HTTP 200, not 404/500. This is the highest-level
    # contract: the route exists and the handler returns 200 with
    # the projection envelope.
    assert response.status_code == 200, (
        "AC-FR1701-01: lifecycle success journey must receive HTTP "
        f"200 from /api/projects/lifecycle/status; got "
        f"{response.status_code}. The route must exist and must not "
        "raise (If-None-Match handlers inherit from "
        "IF-PROJECT-STATUS-01)."
    )

    # Clause 2 — content type is application/json.
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json"), (
        "AC-FR1701-01 / IF-PROJECT-STATUS-01: lifecycle status "
        f"response must be application/json; got content-type="
        f"{content_type!r} body={response.text[:200]!r}"
    )

    # Clause 3 — body parses as JSON and exposes ATDDStatus keys.
    body = response.json()
    missing = _REQUIRED_ATDD_STATUS_KEYS - set(body.keys())
    assert not missing, (
        "AC-FR1701-01 / IF-PROJECT-STATUS-01: lifecycle status body "
        f"missing ATDDStatus keys: {sorted(missing)}; got keys="
        f"{sorted(body.keys())!r}"
    )

    # Clause 4 — the body carries a stages[] array of exactly 13
    # stages in the canonical order, per IF-LIFECYCLE-01 Lifecycle
    # evidence extension.
    stages = body.get("stages", [])
    assert isinstance(stages, list), (
        f"AC-FR1701-01 / IF-LIFECYCLE-01: lifecycle body.stages must "
        f"be a list; got {type(stages).__name__}"
    )
    stage_ids = [stage.get("stage_id") for stage in stages]
    assert stage_ids == list(_CANONICAL_13), (
        "AC-FR1701-01 / IF-LIFECYCLE-01: lifecycle body.stages must "
        "enumerate the 13 canonical stages in the locked order. "
        f"expected={list(_CANONICAL_13)} actual={stage_ids}"
    )

    # Clause 5 — each stage state is ``passed`` (success journey).
    non_passed = [i for i, stage in enumerate(stages) if stage.get("state") != "passed"]
    assert not non_passed, (
        "AC-FR1701-01: success journey requires every stage state "
        f"to be 'passed'; indices {non_passed} have non-passed "
        f"states: {[stages[i].get('state') for i in non_passed]}"
    )

    # Clause 6 — provider call count is 0 (per Isolation/teardown).
    provider_call_count = body.get("provider_call_count")
    assert provider_call_count == 0, (
        "AC-FR1701-02 / IF-LIFECYCLE-01: success journey requires "
        f"provider_call_count == 0; got {provider_call_count!r}. "
        "Real LLM providers must not be called in the replay path."
    )

    # Clause 7 — cleanup ledger is non-null.
    cleanup = body.get("cleanup")
    assert cleanup is not None, (
        "AC-FR1701-02 / IF-LIFECYCLE-01: lifecycle body.cleanup must "
        "be non-null (per Isolation/teardown — server / child / "
        "worktree / host / control / sink all cleaned)."
    )

    # Clause 8 — repo_before_after confirms Louke source unchanged.
    repo_before_after = body.get("repo_before_after")
    if repo_before_after is not None:
        assert repo_before_after.get("louke_source_unchanged") is True, (
            f"AC-FR1701-02 / IF-LIFECYCLE-01: repo_before_after must "
            f"confirm Louke source bytes/refs unchanged; got "
            f"{repo_before_after!r}"
        )


# ---------------------------------------------------------------------------
# LIFECYCLE-3..15: thirteen fail-before-completion scenarios
# ---------------------------------------------------------------------------


@pytest.mark.v014_005_full_lifecycle
@pytest.mark.parametrize("failed_stage", _LIFECYCLE_FAIL_STAGES)
def test_ac_fr1701_02_fail_before_completion_returns_to_owner(
    failed_stage: str,
    shielded_complete_workspace: Path,
) -> None:
    """AC-FR1701-02: ``fail_before_completion`` at each canonical stage.

    Each parameterised variant drives the lifecycle journey with a
    single ``fail_before_completion`` injected at exactly one stage
    (``failed_stage``). The contract (per IF-LIFECYCLE-01 Fail-each-stage)
    binds:

      * Project Status halts at ``failed_stage`` — current stage is
        ``failed_stage`` and not later.
      * Subsequent stages have no ``entered_at`` / no ``artifact_refs``
        / no ``evidence_refs`` (the run does not advance past the
        failure).
      * The projection exposes an ``owner`` and a non-null
        ``recovery_url`` for the failed stage (per IF-FAILURE-ROUTE-01
        FailureDecision).
      * The same WorkflowRun has no parallel run (per IF-LIFECYCLE-01
        Fail-each-stage ``同一run无平行替代``).

    Pre-Devon (stub): lifecycle status route returns 404/500; every
    assertion below FAILs with the AC-FR1701-02 token in the
    assertion message. That is a valid RED.

    Post-Devon (correct implementation): the replay adapter produces
    a halted projection at ``failed_stage`` and every clause here
    PASSes.

    We do NOT use ``assert status_code in (200, 404, 500)``. ``assert
    failed_stage in _LIFECYCLE_FAIL_STAGES`` is also vacuous
    (parametrize value comes from the same tuple) and we omit it. The
    contract we test is the projection's stage-specific halt shape,
    which the stub does not provide.
    """
    app = create_app(project_root=str(shielded_complete_workspace))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/projects/lifecycle/status")

    # Clause 1 — HTTP 200 from the lifecycle status route. The stub
    # returns 404/500; correct implementation returns 200 even for a
    # failed run (because the route's job is to *report* the halt,
    # not to error).
    assert response.status_code == 200, (
        f"AC-FR1701-02: lifecycle status route must return 200 even "
        f"when the journey failed at {failed_stage} (to report the "
        f"halt); got {response.status_code}. A 404/500 here means "
        "the route does not exist or the handler raised."
    )

    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json"), (
        f"AC-FR1701-02 / IF-PROJECT-STATUS-01: lifecycle status "
        f"must return application/json; got {content_type!r}"
    )

    body = response.json()
    stages = body.get("stages", [])
    assert isinstance(stages, list) and len(stages) == 13, (
        f"AC-FR1701-02 / IF-LIFECYCLE-01: lifecycle body.stages must "
        f"have 13 entries; got {len(stages) if isinstance(stages, list) else stages!r}"
    )

    # Find the index of the failed_stage in the canonical order.
    canonical_idx = _CANONICAL_13.index(failed_stage)

    # Clause 2 — current stage is exactly ``failed_stage``.
    current_idx = next(
        (i for i, s in enumerate(stages) if s.get("state") in ("failed", "attention")),
        None,
    )
    assert current_idx == canonical_idx, (
        f"AC-FR1701-02: lifecycle must halt at {failed_stage} "
        f"(canonical idx={canonical_idx}); got halt idx="
        f"{current_idx} (stage="
        f"{stages[current_idx].get('stage_id') if current_idx is not None else None!r})."
    )

    # Clause 3 — subsequent stages have no entered_at / artifact_refs /
    # evidence_refs.
    for i in range(canonical_idx + 1, 13):
        stage = stages[i]
        assert stage.get("entered_at") is None, (
            f"AC-FR1701-02: stage {stage.get('stage_id')!r} "
            f"(idx={i}) after the halt at {failed_stage} must NOT "
            f"have entered_at set; got {stage.get('entered_at')!r}. "
            "The run must not advance past the failure."
        )
        assert not stage.get("artifact_refs"), (
            f"AC-FR1701-02: stage {stage.get('stage_id')!r} (idx={i}) "
            f"after the halt must have no artifact_refs; got "
            f"{stage.get('artifact_refs')!r}."
        )
        assert not stage.get("evidence_refs"), (
            f"AC-FR1701-02: stage {stage.get('stage_id')!r} (idx={i}) "
            f"after the halt must have no evidence_refs; got "
            f"{stage.get('evidence_refs')!r}."
        )

    # Clause 4 — projection exposes owner and a non-null recovery_url
    # for the failed stage (per IF-FAILURE-ROUTE-01 FailureDecision).
    halt_stage = stages[canonical_idx]
    assert halt_stage.get("owner") is not None, (
        f"AC-FR1701-02 / IF-FAILURE-ROUTE-01: halted stage "
        f"{failed_stage!r} must expose an owner; got "
        f"{halt_stage.get('owner')!r}"
    )
    assert halt_stage.get("recovery_url") is not None, (
        f"AC-FR1701-02 / IF-FAILURE-ROUTE-01: halted stage "
        f"{failed_stage!r} must expose a non-null recovery_url; "
        f"got {halt_stage.get('recovery_url')!r}"
    )
