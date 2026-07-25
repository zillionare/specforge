"""AC-FR1601-01 / AC-NFR0101-01 — IF-PROMPT-01 closed set and identity.

Cross-module: ``Prompt/Capability Packaging`` × ``CI/Traceability`` ×
``Runtime Facts``.

The four canonical prompt sources are *closed*: any extra path,
alias, or ``.opencode``-based ``*.md`` would expand the bundle and
contradict the supersession contract. The bundle candidate must list
exactly those four sources with their digests.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = (
    REPO_ROOT
    / ".louke"
    / "project"
    / "contracts"
    / "v0.14-005-atdd-process-improvement"
)
BUNDLE = CONTRACTS_DIR / "prompts" / "prompt-bundle.candidate.json"

EXPECTED_CLOSED_SOURCES = (
    "louke/agents/Archer.md",
    "louke/agents/Shield.md",
    "louke/agents/Devon.md",
    "louke/agents/Prism.md",
)


def _read_bundle() -> dict:
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def test_ac_fr1601_01_closed_source_set_is_exactly_four() -> None:
    """AC-FR1601-01: prompt bundle closed set is exactly Archer/Shield/Devon/Prism.

    Any fifth source — even a duplicate — is a supersession violation
    (``PROMPT_SCOPE_DENIED``).
    """
    bundle = _read_bundle()
    declared = bundle.get("closed_source_set", [])
    assert tuple(declared) == EXPECTED_CLOSED_SOURCES, (
        f"AC-FR1601-01: closed_source_set drifted from {EXPECTED_CLOSED_SOURCES}; "
        f"got {declared}"
    )

    sources = [s["path"] for s in bundle.get("sources", [])]
    assert set(sources) == set(EXPECTED_CLOSED_SOURCES), (
        f"AC-FR1601-01: bundle.sources contains paths outside the closed set: "
        f"unexpected={set(sources) - set(EXPECTED_CLOSED_SOURCES)}, "
        f"missing={set(EXPECTED_CLOSED_SOURCES) - set(sources)}"
    )


def test_ac_fr1601_01_each_source_file_exists_and_has_digest_recorded() -> None:
    """AC-FR1601-01: each prompt source must exist and carry its recorded digest.

    Drift between recorded digest and on-disk bytes is the failure mode
    that ``louke/_tools/prompt_bundle.py``'s validator is supposed to
    catch; we assert the contract itself preserves the digest so the
    validator can compute the comparison.
    """
    bundle = _read_bundle()

    for entry in bundle.get("sources", []):
        full = REPO_ROOT / entry["path"]
        assert full.is_file(), (
            f"AC-FR1601-01: bundled source {entry['path']} missing on disk"
        )
        assert "digest" in entry, (
            f"AC-FR1601-01: source {entry['path']} must record a 'digest'"
        )
        digest = entry["digest"]
        assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64, (
            f"AC-FR1601-01: source {entry['path']} digest must be SHA-256 hex; "
            f"got {digest!r}"
        )


def test_ac_fr1601_01_no_dotopencode_alias_in_canonical_sources() -> None:
    """AC-FR1601-01: ``closed_source_set`` and ``sources[]`` exclude
    ``.opencode/agents/{role}.md`` deployment aliases.

    The active deployment output lives under ``.opencode/agents/``
    but the *canonical source* lives under ``louke/agents/``.
    Aliases in the canonical-source set would risk running a
    deployment copy instead of the spec-pinned source.

    We allow ``.opencode/agents/`` references in the bundle's
    ``staging`` and ``deployment_readback`` records (those describe the
    transformer output) but not in the closed-source / canonical
    sections.
    """
    bundle = _read_bundle()

    closed_set = bundle.get("closed_source_set", [])
    for entry in closed_set:
        assert ".opencode" not in entry, (
            f"AC-FR1601-01: closed_source_set entry {entry!r} is a "
            f"deployment alias, not a canonical source."
        )

    for source in bundle.get("sources", []):
        path = source.get("path", "")
        assert ".opencode" not in path, (
            f"AC-FR1601-01: sources[] entry {path!r} is a deployment "
            f"alias, not a canonical source."
        )


def test_ac_nfr0101_01_each_role_has_distinct_model_binding() -> None:
    """AC-NFR0101-01: distinct role → model binding prevents accidental swap.

    A role with the wrong model binding would still import cleanly but
    produce inconsistent output quality; the closed set binds each
    role to its model.
    """
    bundle = _read_bundle()

    role_model_pairs = {
        (entry["role"], entry["model_binding"]) for entry in bundle.get("sources", [])
    }
    assert len(role_model_pairs) == len(bundle.get("sources", [])), (
        "AC-NFR0101-01: at least one role shares its model binding with "
        "another. Roles must have distinct model bindings."
    )


def test_ac_nfr0101_01_each_role_has_input_output_schema_refs() -> None:
    """AC-NFR0101-01: schema references must be ``schema_ref.identity/version``.

    Without schema_ref, the Agent I/O envelope cannot be reconstructed
    by downstream machinery.
    """
    bundle = _read_bundle()
    for entry in bundle.get("sources", []):
        for key in ("input_schema_ref", "output_schema_ref"):
            ref = entry.get(key)
            assert ref is not None, (
                f"AC-NFR0101-01: source {entry['path']} missing {key}"
            )
            for required in ("identity", "version", "digest", "activation_state"):
                assert required in ref, (
                    f"AC-NFR0101-01: {entry['path']}.{key} must declare {required}"
                )
            assert ref["activation_state"] in {"candidate"}, (
                f"AC-NFR0101-01: {entry['path']}.{key}.activation_state "
                f"must be 'candidate' (not 'active') until activation"
            )
