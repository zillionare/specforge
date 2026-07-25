"""AC-FR1101-01 / AC-FR1101-02 / AC-NFR0301-01 — IF-DISCRIM-01 contract.

Cross-module: ``Semantic Discrimination Adapter`` × ``Host Required-Test
Adapter`` × ``External Stand-ins`` × ``Runtime Facts``.

``run_discrimination`` and ``verify_restored_candidate`` are the only two
API surfaces that mutate an isolated Git worktree and a product venv.
Drift in their keyword-only contract breaks the safety isolation that
NFR-0301-01 binds against.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path


from louke.runtime import semantic_discrimination


def _params(fn) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(fn).parameters)


def test_ac_fr1101_01_run_discrimination_kwargs_include_phase_and_manifest() -> None:
    """AC-FR1101-01: required kwargs must match interfaces.md IF-DISCRIM-01.

    Dropping ``phase`` would let ``pre-implementation`` and ``post-green``
    runs share state; dropping ``counterexample_manifest_path`` would let
    the adapter invent mutants on the fly (a 004 failure mode).
    """
    expected = {
        "project_root",
        "adapter_contract_path",
        "counterexample_manifest_path",
        "candidate_identity",
        "phase",
        "evidence_path",
    }
    actual = set(_params(semantic_discrimination.run_discrimination))
    assert actual == expected, (
        f"AC-FR1101-01: run_discrimination kwargs drifted: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_ac_fr1101_02_verify_restored_candidate_requires_original_digest() -> None:
    """AC-FR1101-02: restoration must verify ``original_artifact_digest``.

    Without the original digest the safety gate that prevents restoring a
    silently-mutated candidate cannot detect drift; this is the same
    failure mode that NFR-0301-01 closes (RUN can still show ``passed``
    after a worktree is dirty).
    """
    expected = {
        "project_root",
        "candidate_identity",
        "original_artifact_digest",
        "affected_bundle_path",
        "full_bundle_path",
        "evidence_path",
    }
    actual = set(_params(semantic_discrimination.verify_restored_candidate))
    assert actual == expected, (
        f"AC-FR1101-02: verify_restored_candidate kwargs drifted: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_ac_nfr0301_01_both_functions_raise_if_discrim_token() -> None:
    """Both stubs raise ``NotImplementedError("IF-DISCRIM-01")``.

    Without the contract token, IF-VALID-RED-01 cannot bind RED evidence
    to the IF; safety evidence becomes ungrouped.
    """
    src = Path(semantic_discrimination.__file__).read_text(encoding="utf-8")
    matches = re.findall(r"""NotImplementedError\(["']IF-DISCRIM-01["']\)""", src)
    assert len(matches) >= 2, (
        "AC-NFR0301-01: each public IF-DISCRIM-01 stub must raise "
        'NotImplementedError("IF-DISCRIM-01") to attribute RED to the '
        "contract anchor; found "
        f"{len(matches)} literal(s) in {semantic_discrimination.__file__}."
    )


def test_ac_nfr0301_01_all_parameters_keyword_only() -> None:
    """NFR-0301-01: every parameter of the discrimination adapter is keyword-only.

    A positional caller could silently swap ``affected_bundle_path``
    with ``full_bundle_path`` and pass the wrong bundle to restoration.
    The contract treats both APIs as keyword-only.
    """
    for fn in (
        semantic_discrimination.run_discrimination,
        semantic_discrimination.verify_restored_candidate,
    ):
        params = list(inspect.signature(fn).parameters.values())
        kinds = {p.kind for p in params}
        assert inspect.Parameter.KEYWORD_ONLY in kinds, (
            f"AC-NFR0301-01: {fn.__name__} must have keyword-only parameters; got {kinds}"
        )
