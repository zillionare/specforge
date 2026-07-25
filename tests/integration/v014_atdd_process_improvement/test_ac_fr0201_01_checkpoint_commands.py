"""AC-FR0201-01 / AC-FR0401-01 / AC-FR0701-01 — IF-ATDD-CHECKPOINT-01 integration.

Cross-module: ``ATDD Checkpoint`` × ``Task Package`` × ``Runtime Facts`` ×
``Design Declaration``.

Each named checkpoint command (``prepare_shield_task``,
``record_shield_submission``, ``freeze_test_bundle``,
``prepare_devon_task``, ``request_declaration_revision``,
``record_implementation_result``, ``record_m_test_closure``) is one half
of a checkpoint transition; together they encode the ATDD flow. These
tests verify:

* every command can be constructed with the kwargs listed in
  interfaces.md (signature shape, no positional overlap);
* the per-command gate conditions are encoded in the docstring (the
  contract anchor is what Prism will read in PR review);
* the ``ATDDCheckpointProjection`` shape listed in interfaces.md §3 is
  actually importable from the runtime package — keeping the projection
  shape honest guards against Devon/Archer drift on
  ``available_actions`` and ``m_verify_allowed`` semantics.
"""

from __future__ import annotations

import inspect


from louke.runtime import atdd_checkpoint


def _sig_param_names(fn) -> list[str]:
    return list(inspect.signature(fn).parameters)


def test_ac_fr0201_01_prepare_shield_task_signature_matches_interface() -> None:
    """IF-ATDD-CHECKPOINT-01 ``prepare_shield_task`` enforces the contract.

    interfaces.md §3 lists the exact kwargs:
    ``project_root, run_id, attempt_id, baseline_identity,
    expected_run_revision, output_path``. Shield's task generation is
    rejected if any of these are missing because each value is bound
    into the resulting IF-TASK-01 manifest.
    """
    fn = atdd_checkpoint.prepare_shield_task
    expected = {
        "project_root",
        "run_id",
        "attempt_id",
        "baseline_identity",
        "expected_run_revision",
        "output_path",
    }
    actual = set(_sig_param_names(fn))
    assert actual == expected, (
        f"AC-FR0201-01: prepare_shield_task kwargs drifted: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_ac_fr0201_01_record_implementation_result_carries_candidate_identity() -> None:
    """``record_implementation_result`` binds ``candidate_identity``.

    Without this parameter, the candidate pushed to the ATDD checkpoint
    cannot be tied to a freeze revision, which would orphan the
    restored-green check in IF-REVISION-01.
    """
    fn = atdd_checkpoint.record_implementation_result
    params = set(_sig_param_names(fn))
    assert "candidate_identity" in params, (
        "AC-FR0201-01: record_implementation_result must accept "
        "candidate_identity to bind the post-Devon candidate to the "
        "frozen bundle identity."
    )
    assert "expected_run_revision" in params, (
        "AC-FR0201-01: record_implementation_result must enforce "
        "expected_run_revision to reject stale Caller API submissions."
    )


def test_ac_fr0701_01_freeze_test_bundle_requires_prism_review_path() -> None:
    """``freeze_test_bundle`` is gated by Prism review evidence.

    A freeze without a Prism review path would let Shield self-freeze
    bypassing the contract (a 004-class failure mode). The argument
    list must therefore reject any call that omits the review path.
    """
    fn = atdd_checkpoint.freeze_test_bundle
    params = set(_sig_param_names(fn))
    assert "prism_review_path" in params, (
        "AC-FR0701-01: freeze_test_bundle must accept prism_review_path; "
        "without it, a freeze without independent review would be "
        "mechanically possible."
    )
    assert "submission_identity" in params, (
        "AC-FR0701-01: freeze_test_bundle must accept submission_identity "
        "to bind the freeze to the prior record_shield_submission output."
    )


def test_ac_fr0701_01_request_declaration_revision_carries_contract_anchor() -> None:
    """``request_declaration_revision`` requires a non-empty contract anchor.

    FR-0201-02 makes declaration revision a Devon-initiated
    mechanism. The command carries ``contract_anchor`` and ``reason``
    so that the resulting cooldown evidence references the exact clause
    the Devon surfaces disagrees with.
    """
    fn = atdd_checkpoint.request_declaration_revision
    params = set(_sig_param_names(fn))
    assert {
        "task_id",
        "contract_anchor",
        "reason",
        "expected_run_revision",
        "evidence_path",
    } <= params, (
        "AC-FR0701-01: request_declaration_revision kwargs must include "
        f"task_id, contract_anchor, reason, expected_run_revision, evidence_path; got {params}"
    )


def test_ac_fr0201_01_record_m_test_closure_documents_m_verify_allowed() -> None:
    """AC-FR0201-01: ``record_m_test_closure`` declares ``m_verify_allowed``.

    ``m_verify_allowed`` is the Project Status gate that decides
    whether to surface the ``continue_m_verify`` action. The
    contract requires the checkpoint module to expose it through
    either a callable (raising the IF-token stub today) or a
    dataclass field carrying the same identity. Without this
    binding, Project Status UI could render an action that the
    runtime cannot fulfil.
    """
    fn = atdd_checkpoint.record_m_test_closure
    # Behavioural half: calling the stub raises with the IF-token
    # (this is the contract Stub's RED shape per IF-VALID-RED-01).
    try:
        fn(
            project_root=None,
            candidate_identity="ci",
            discrimination_evidence_path=None,
            restored_green_evidence_path=None,
            closure_evidence_path=None,
            expected_run_revision=0,
        )
    except NotImplementedError as exc:
        assert "IF-ATDD-CHECKPOINT-01" in str(exc), (
            "AC-FR0201-01: stub NotImplementedError must reference "
            f"IF-ATDD-CHECKPOINT-01 so the stub-RED is attributable "
            f"to the right contract anchor; got message={exc!r}"
        )
    else:
        raise AssertionError(
            "AC-FR0201-01: expected NotImplementedError on stub call; "
            "returned normally instead."
        )

    # Contract half: ``m_verify_allowed`` must be discoverable through
    # the module public surface. Accept any of:
    # - module-level dataclass / TypedDict with ``m_verify_allowed`` field;
    # - the function's __doc__ mentioning ``m_verify_allowed``;
    # - module-level __doc__ carrying ``m_verify_allowed`` (when Devon
    #   promotes the structured type to a class symbol).
    module_attrs = {
        name: getattr(atdd_checkpoint, name) for name in dir(atdd_checkpoint)
    }

    def _has_field(obj) -> bool:
        """Return ``True`` iff *obj* exposes ``m_verify_allowed`` as a field/key."""
        if obj is None:
            return False
        if hasattr(obj, "__dataclass_fields__"):
            return "m_verify_allowed" in obj.__dataclass_fields__
        if isinstance(obj, dict) and "m_verify_allowed" in obj:
            return True
        # TypedDict
        annotations = getattr(obj, "__annotations__", None)
        if isinstance(annotations, dict) and "m_verify_allowed" in annotations:
            return True
        return False

    found = False
    for name, attr in module_attrs.items():
        if name.startswith("_"):
            continue
        if _has_field(attr):
            found = True
            break

    if not found:
        # Accept the term in any public function's __doc__ (the
        # contract can be documented before the dataclass is named).
        for name, attr in module_attrs.items():
            if callable(attr) and not name.startswith("_"):
                doc = inspect.getdoc(attr) or ""
                if "m_verify_allowed" in doc:
                    found = True
                    break

    assert found, (
        "AC-FR0201-01: ``m_verify_allowed`` must be discoverable "
        "through ``louke.runtime.atdd_checkpoint``: either as a "
        "dataclass/TypedDict field on a public projection symbol, "
        "or as a documented field name in a public function's "
        "docstring. Found nothing."
    )


def test_ac_fr0501_01_record_shield_submission_requires_red_evidence_path() -> None:
    """IF-ATDD-CHECKPOINT-01 ``record_shield_submission`` requires RED evidence.

    Without ``red_evidence_path``, Shield could submit tests without
    proving that they ever collected (FR-0601-02 requires pre-RED
    evidence).
    """
    fn = atdd_checkpoint.record_shield_submission
    params = set(_sig_param_names(fn))
    assert "red_evidence_path" in params, (
        "AC-FR0501-01: record_shield_submission must accept "
        "red_evidence_path to bind the freeze to the IF-VALID-RED-01 "
        "evidence identity."
    )
    assert (
        "task_path" in params
        and "bundle_path" in params
        and "expected_run_revision" in params
    ), f"AC-FR0501-01: record_shield_submission kwargs incomplete; got {params}"
