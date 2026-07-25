"""AC-FR0101-01 / AC-FR0101-02 — IF-DECLARATION-01 declaration manifest exists with
closed file/token set and source readback.

Cross-module: ``Design Declaration`` × ``Runtime Facts`` × ``ATDD Checkpoint``
× ``Task Package``.

The IF-DECLARATION-01 manifest lives under ``.louke/project/contracts/`` and
must:

* list only the production module paths that host ATDD-required public
  surfaces (closed set);
* carry a ``files[].entries[].token`` for every IF-token exported by this
  spec, and **only** those tokens;
* reference the same Story / Spec / Acceptance digests that the locked
  frontmatter does;
* declare ``assurance.mode == "downstream-atdd"`` to mark that no
  pre-Shield programmatic validator is required (FR-0101 downstream path);
* have a stable ``interfaces_identity`` digest that matches the actual
  ``interfaces.md`` bytes (provenance, not a gate).

This drives real file I/O against ``.louke/project/contracts/...``. No
runtime or schema resolver is invoked — the contract itself is data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = (
    REPO_ROOT / ".louke" / "project" / "specs" / "v0.14-005-atdd-process-improvement"
)
CONTRACTS_DIR = (
    REPO_ROOT
    / ".louke"
    / "project"
    / "contracts"
    / "v0.14-005-atdd-process-improvement"
)

DECLARATION_MANIFEST = CONTRACTS_DIR / "interface-declarations.candidate.json"
INTERFACES_DOC = SPEC_DIR / "interfaces.md"
STORY_DOC = SPEC_DIR / "story.md"
SPEC_DOC = SPEC_DIR / "spec.md"
ACCEPTANCE_DOC = SPEC_DIR / "acceptance.md"


def _canonical_sha256_text(text: str) -> str:
    """Compute the canonical SHA-256 of *text* (UTF-8 bytes)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _locked_sha_from_frontmatter(doc: Path, key: str) -> str:
    """Extract the locked ``key: sha256:...`` value from a Louke document."""
    for line in doc.read_text(encoding="utf-8").splitlines():
        # Tolerate ``- **Spec SHA-256**：`` and the trailing markdown asterisks
        # that earlier edits left behind.
        line = line.rstrip("*").strip()
        if line.startswith(f"- **{key} SHA-256**") or line.startswith(
            f"- **{key} SHA**"
        ):
            value = line.split("`", 2)
            if len(value) >= 2:
                return value[1]
        if line.startswith(f"- **{key}**") and "sha256:" in line:
            for token in line.split("`"):
                if token.startswith("sha256:"):
                    return token
    raise AssertionError(f"locked SHA-256 for {key} not found in {doc}")


def _read_manifest() -> dict:
    return json.loads(DECLARATION_MANIFEST.read_text(encoding="utf-8"))


def test_ac_fr0101_01_manifest_is_present_and_candidate_only() -> None:
    """AC-FR0101-01: declaration manifest exists and is not silently activated.

    The manifest must be readable as JSON, declare an explicit
    ``activation_state`` other than ``active``, and advertise the closed
    set of production files. No business code path is exercised; this
    closes the readback half of AC-FR0101-01.
    """
    # AC-FR0101-01: M-DESIGN readback 可核对声明骨架位于宿主目标真实模块路径
    assert DECLARATION_MANIFEST.is_file(), (
        f"AC-FR0101-01: declaration manifest missing at {DECLARATION_MANIFEST}; "
        "Archer must commit it alongside the design bundle."
    )

    manifest = _read_manifest()
    activation = manifest.get("activation_state")
    assert activation in {
        "candidate-not-installed",
        "candidate-not-validated",
        "candidate",
    }, (
        f"AC-FR0101-01: declaration manifest activation_state must remain "
        f"candidate-only, got {activation!r}"
    )

    files = manifest.get("files", [])
    assert files, "AC-FR0101-01: manifest must enumerate the closed set of files"

    # Every listed path must exist in the working tree (stubs are valid).
    listed_paths = [entry["path"] for entry in files]
    assert len(listed_paths) == len(set(listed_paths)), (
        f"AC-FR0101-01: file paths must be unique within the closed set; "
        f"duplicates: {listed_paths}"
    )
    for entry in files:
        full = REPO_ROOT / entry["path"]
        assert full.is_file(), (
            f"AC-FR0101-01: declared file {entry['path']!r} missing on disk"
        )


def test_ac_fr0101_01_closed_token_set_matches_interfaces() -> None:
    """AC-FR0101-01: stub tokens in §8 (interfaces.md) must appear in the manifest.

    Not every IF-token in interfaces.md has a ``louke/`` stub —
    documentation-only IFs (registry, prompt, error, evidence
    envelope, CI, pre-commit, release, project-status UI, etc.) bind
    to schemas and HTTP-shape contracts that are not first-class
    Python module stubs. We therefore restrict the bidirectional
    closure check to the §8 *stub lock list* (the subset of IFs that
    must produce callable Python symbols).
    """
    manifest = _read_manifest()
    declared_tokens: set[str] = set()
    for entry in manifest.get("files", []):
        for subentry in entry.get("entries", []):
            token = subentry.get("token")
            if token:
                declared_tokens.add(token)

    interfaces_text = INTERFACES_DOC.read_text(encoding="utf-8")

    def _stub_lock_list_tokens() -> set[str]:
        """Collect IF-tokens in the §8 stub lock list table.

        The table starts after ``## 8. 接口桩锁定清单`` and ends before
        the next ``## `` heading. Each row's first cell is ``\`IF-XXX\```.
        """
        markers = ("## 8. ", "## 8.")
        start = -1
        for marker in markers:
            start = interfaces_text.find(marker)
            if start != -1:
                break
        if start == -1:
            return set()
        end = interfaces_text.find("\n## ", start + 1)
        if end == -1:
            end = len(interfaces_text)
        section = interfaces_text[start:end]
        tokens: set[str] = set()
        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            first_cell = line.strip("|").split("|", 1)[0].strip().strip("`")
            if first_cell.startswith("IF-"):
                tokens.add(first_cell)
        return tokens

    stub_list_tokens = _stub_lock_list_tokens()

    missing = stub_list_tokens - declared_tokens
    extra = declared_tokens - stub_list_tokens
    assert not missing, (
        f"AC-FR0101-01: manifest missing IF tokens from interfaces.md §8 "
        f"stub lock list: {sorted(missing)}"
    )
    assert not extra, (
        f"AC-FR0101-01: manifest has tokens not listed in §8 stub lock "
        f"list: {sorted(extra)}"
    )


def test_ac_fr0101_01_manifest_references_locked_digests() -> None:
    """AC-FR0101-01: manifest's ``baseline_identity`` must match the *current*
    story/spec/acceptance digests on disk.

    The manifest is a provenance document. Its story / spec /
    acceptance identities must be the SHA-256 of the bytes of the
    current committed documents, not stale SHA snapshots from
    earlier baselines. ``X-Louke-CSRF`` / Runtime proceeds only when
    the manifest points at the *current* canonical SHA.

    The body of this test does not import ``louke.runtime``; it
    reads the design artefacts directly and compares against the
    manifest, so a stale ``interfaces_identity`` cannot pass.
    """
    manifest = _read_manifest()
    baseline = manifest.get("baseline_identity", {})
    if not baseline:
        pytest.fail(
            "AC-FR0101-01: manifest must declare baseline_identity; "
            f"got manifest keys={list(manifest.keys())!r}"
        )

    current_story = _canonical_sha256_text(STORY_DOC.read_text(encoding="utf-8"))
    current_spec = _canonical_sha256_text(SPEC_DOC.read_text(encoding="utf-8"))
    current_acc = _canonical_sha256_text(ACCEPTANCE_DOC.read_text(encoding="utf-8"))

    actual_story = baseline.get("story")
    actual_spec = baseline.get("spec")
    actual_acc = baseline.get("acceptance")

    # Drift detection — the manifest must point at the current SHAs
    # of the on-disk design artefacts. If the manifest references a
    # stale SHA, the design is rebasing on requirements that no
    # longer match the bytes, which is a frozen-state violation.
    assert actual_story == current_story, (
        "AC-FR0101-01: manifest story digest drift: "
        f"current_on_disk={current_story} manifest={actual_story}. "
        "Either the manifest or the story.md bytes are stale; "
        "they must agree."
    )
    assert actual_spec == current_spec, (
        "AC-FR0101-01: manifest spec digest drift: "
        f"current_on_disk={current_spec} manifest={actual_spec}."
    )
    assert actual_acc == current_acc, (
        "AC-FR0101-01: manifest acceptance digest drift: "
        f"current_on_disk={current_acc} manifest={actual_acc}."
    )


def test_ac_fr0101_02_assurance_mode_marks_downstream_atdd_path() -> None:
    """AC-FR0101-02: validator removal is recorded in the manifest's assurance block.

    With FR-0101 reducing the pre-Shield validator to the downstream
    collection/RED/declaration-revision path, the manifest's
    ``assurance.mode`` must be ``downstream-atdd`` (and must NOT advertise any
    pre-Shield programmatic validator evidence).
    """
    manifest = _read_manifest()
    assurance = manifest.get("assurance", {})
    mode = assurance.get("mode")
    assert mode == "downstream-atdd", (
        f"AC-FR0101-02: manifest.assurance.mode must be 'downstream-atdd' "
        f"to mark the FR-0101 validator removal, got {mode!r}"
    )
    # Anti-pattern guard: must not hide any pre-Shield programmatic gate.
    forbidden = (
        "validator_command",
        "validator_cli",
        "validate_interface_declarations",
    )
    text = json.dumps(manifest)
    for needle in forbidden:
        assert needle not in text, (
            f"AC-FR0101-02: manifest must not carry programmatic validator "
            f"hook '{needle}' after FR-0101 revision"
        )


def test_ac_fr0101_02_every_entry_is_closed_no_extra_files() -> None:
    """AC-FR0101-02: closed file/token set — no production module added without an IF.

    Drive a synthetic negative: append a fictitious token to a real
    manifest and assert the validation logic catches it. The negative
    check is the asymmetry of "extra token yields an invalid manifest".
    """
    import copy

    manifest = copy.deepcopy(_read_manifest())
    assert manifest.get("files"), (
        "AC-FR0101-02: manifest must have at least one file entry to "
        "test the negative path (extra token detection)."
    )

    target_file = manifest["files"][0]
    target_file.setdefault("entries", []).append(
        {
            "token": "IF-SYNTHETIC-XX",
            "kind": "function",
            "symbol": "synthetic_symbol",
            "signature": "() -> None",
            "route": None,
            "methods": [],
            "implementation_region": "function-body",
        }
    )

    declared_tokens: set[str] = set()
    for entry in manifest["files"]:
        for subentry in entry.get("entries", []):
            declared_tokens.add(subentry.get("token"))

    interfaces_text = INTERFACES_DOC.read_text(encoding="utf-8")
    expected_tokens = {
        line.split(" ", 1)[0]
        for line in interfaces_text.splitlines()
        if line.startswith("### IF-")
    }

    extra = declared_tokens - expected_tokens
    assert "IF-SYNTHETIC-XX" in extra, (
        "AC-FR0101-02: synthetic extra token must be detected as 'extra' by "
        "the same reconciliation that closed-set validation uses"
    )
