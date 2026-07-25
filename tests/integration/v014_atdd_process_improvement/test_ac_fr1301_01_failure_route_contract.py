"""AC-FR1301-01 / AC-FR1301-02 — IF-FAILURE-ROUTE-01 contract.

Cross-module: ``Failure Routing`` × ``Test Asset Review`` × ``ATDD
Checkpoint`` × ``Runtime Facts``.

``classify_atdd_failure`` is the single API that maps a frozen
test/contract/runner identity mismatch into a ``FailureDecision``. The
shape of that decision is the contract the Project Status UI renders,
so regressions there are user-visible.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path


from louke.runtime import atdd_failure_routing


EXPECTED_DECISION_FIELDS = {
    "decision_id",
    "classification",
    "owner",
    "return_target",
    "contract_anchors",
    "test_identity",
    "candidate_identity",
    "runner_identity",
    "prism_diagnostic_identity",
    "current",
    "reason",
    "recovery_url",
}


EXPECTED_CLASSIFICATIONS = {
    "infrastructure_or_test_asset",
    "test_contract_mismatch",
    "implementation_or_composition",
    "design_gap",
    "requirement_gap",
    "safety_attention",
}


EXPECTED_OWNERS = {
    "Shield",
    "Devon",
    "Archer",
    "Runtime",
    "HumanControlledRequirements",
}


EXPECTED_RETURN_TARGETS = {
    "M-IMPL:Shield",
    "M-IMPL:Devon",
    "M-DESIGN",
    "M-SPEC",
    "M-ACC",
    "ATTENTION",
}


def test_ac_fr1301_01_classify_signature_accepts_prism_diagnostic_optional() -> None:
    """AC-FR1301-01: ``prism_diagnostic_path`` is optional (Python ``| None``).

    When Prism has not yet reviewed, ``FailureDecision.prism_diagnostic_identity``
    is null; when Prism has reviewed, it carries the diagnostic digest.
    Without the optional marker, the Python API would force callers to
    invent a fake path.
    """
    sig = inspect.signature(atdd_failure_routing.classify_atdd_failure)
    param = sig.parameters["prism_diagnostic_path"]
    assert param.annotation is not inspect.Parameter.empty and "None" in str(
        param.annotation
    ), (
        "AC-FR1301-01: classify_atdd_failure must mark "
        "prism_diagnostic_path as Optional (None) so Prism-less "
        "failures can still be classified."
    )


def test_ac_fr1301_01_required_kwargs_present() -> None:
    """AC-FR1301-01: classify_atdd_failure accepts the closed kwarg set.

    interfaces.md IF-FAILURE-ROUTE-01 lists
    ``project_root, evidence_paths, contract_paths, prism_diagnostic_path,
    output_path``. Each kwarg feeds into the FailureDecision fields.
    """
    expected = {
        "project_root",
        "evidence_paths",
        "contract_paths",
        "prism_diagnostic_path",
        "output_path",
    }
    actual = set(
        inspect.signature(atdd_failure_routing.classify_atdd_failure).parameters
    )
    assert actual == expected, (
        f"AC-FR1301-01: classify_atdd_failure kwargs drifted: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_ac_fr1301_01_failure_decision_enum_members_present_in_source() -> None:
    """AC-FR1301-01: the closed set of classifications, owners, and return targets.

    interfaces.md IF-FAILURE-ROUTE-01 binds these as closed strings
    (``classification``, ``owner``, ``return_target``). The contract
    is enforced through three public enums / Literal-typed
    declarations on :mod:`louke.runtime.atdd_failure_routing`. A
    future Spec that adds a sixth classification must rebind the
    test AND update interfaces.md at the same time.
    """
    import enum as _enum_mod
    import typing as _typing

    module_attrs = {
        n: getattr(atdd_failure_routing, n) for n in dir(atdd_failure_routing)
    }

    def _enum_members(value: type) -> set[str]:
        members: set[str] = set()
        for m in value:
            members.add(m.value if isinstance(m.value, str) else m.name)
        return members

    def _literal_members(value) -> set[str]:
        if _typing.get_origin(value) is _typing.Literal:
            return set(_typing.get_args(value))
        return set()

    def _is_locally_defined(attr) -> bool:
        own_module = getattr(atdd_failure_routing, "__name__", None)
        attr_module = getattr(attr, "__module__", None)
        return attr_module is not None and attr_module == own_module

    def _resolve_closed_enum_or_literal(
        candidate_names: tuple[str, ...],
    ) -> tuple[set[str], str, str]:
        """Return ``(members, kind, source_name)`` for the first matching enum/Literal.

        Searches by symbol-name hints (``*Classification*``, ``*Owner*``,
        ``*ReturnTarget*``). Restricts to symbols whose ``__module__``
        is this runtime module, so imports of ``Enum`` subclasses from
        elsewhere are not picked up.
        """
        for name, attr in module_attrs.items():
            if name.startswith("_"):
                continue
            if not (isinstance(attr, type) and issubclass(attr, _enum_mod.Enum)):
                continue
            if not _is_locally_defined(attr):
                continue
            if any(hint in name for hint in candidate_names):
                return _enum_members(attr), "enum", name
        for name, attr in module_attrs.items():
            if name.startswith("_"):
                continue
            lit = _literal_members(attr)
            if lit:
                return lit, "literal", name
        return set(), "", ""

    # Classification: must be exactly the 6 closed strings.
    class_members, class_kind, class_source = _resolve_closed_enum_or_literal(
        ("Classification", "Class")
    )
    assert class_members == EXPECTED_CLASSIFICATIONS, (
        f"AC-FR1301-01: classification enum/Literal ({class_source!r}, "
        f"kind={class_kind!r}) must equal exactly "
        f"{sorted(EXPECTED_CLASSIFICATIONS)!r}; got {sorted(class_members)!r}"
    )

    # Owner: must be exactly the 5 closed strings.
    owner_members, owner_kind, owner_source = _resolve_closed_enum_or_literal(
        ("Owner",)
    )
    assert owner_members == EXPECTED_OWNERS, (
        f"AC-FR1301-01: owner enum/Literal ({owner_source!r}, "
        f"kind={owner_kind!r}) must equal exactly "
        f"{sorted(EXPECTED_OWNERS)!r}; got {sorted(owner_members)!r}"
    )

    # ReturnTarget: must be exactly the 6 closed strings.
    return_members, return_kind, return_source = _resolve_closed_enum_or_literal(
        ("ReturnTarget", "Target")
    )
    assert return_members == EXPECTED_RETURN_TARGETS, (
        f"AC-FR1301-01: return_target enum/Literal ({return_source!r}, "
        f"kind={return_kind!r}) must equal exactly "
        f"{sorted(EXPECTED_RETURN_TARGETS)!r}; got {sorted(return_members)!r}"
    )


def test_ac_fr1301_01_stub_raises_with_if_token() -> None:
    """AC-FR1301-01: classify_atdd_failure raises NotImplementedError with IF token.

    RED-binding to the contract anchor is mandatory for IF-VALID-RED-01
    attribution; without this literal, the token would be missing from
    the implementation and Prism would see a silent cause.
    """
    src = Path(atdd_failure_routing.__file__).read_text(encoding="utf-8")
    assert re.search(r"""NotImplementedError\(["']IF-FAILURE-ROUTE-01["']\)""", src), (
        "AC-FR1301-01: classify_atdd_failure must raise "
        'NotImplementedError("IF-FAILURE-ROUTE-01") to bind RED to the '
        "contract anchor; current source lacks that exact string."
    )


def test_ac_fr1301_01_decision_includes_all_required_fields() -> None:
    """AC-FR1301-01: ``FailureDecision`` shape encompasses the interfaces.md fields.

    interfaces.md IF-FAILURE-ROUTE-01 binds the decision JSON shape.
    We enforce this through the *public* surface: a dataclass
    (recommended) or TypedDict carrying the required field names.
    Without this binding, the Project Status UI could render fields
    whose meaning the runtime cannot fulfil.
    """
    module_attrs = {
        n: getattr(atdd_failure_routing, n)
        for n in dir(atdd_failure_routing)
        if not n.startswith("_")
    }

    def _is_locally_defined(attr) -> bool:
        """Return ``True`` iff *attr*'s ``__module__`` is this runtime module.

        Imported names (``Mapping``, ``Sequence``, ``Path`` from
        ``collections.abc``/``pathlib``) have a different ``__module__``
        and must be excluded from dataclass/TypedDict candidate
        holders.
        """
        own_module = getattr(atdd_failure_routing, "__name__", None)
        attr_module = getattr(attr, "__module__", None)
        return attr_module is not None and attr_module == own_module

    def _candidate_field_holders() -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        for name, attr in module_attrs.items():
            if attr is None:
                continue
            if not _is_locally_defined(attr):
                continue
            # dataclass
            if hasattr(attr, "__dataclass_fields__"):
                out.append((name, attr))
                continue
            # TypedDict
            annotations = getattr(attr, "__annotations__", None)
            if isinstance(annotations, dict):
                out.append((name, annotations))
        return out

    holders = _candidate_field_holders()
    assert holders, (
        "AC-FR1301-01: at least one public dataclass/TypedDict must "
        "be declared on ``louke.runtime.atdd_failure_routing`` to "
        "carry the FailureDecision contract; none found."
    )

    for field in EXPECTED_DECISION_FIELDS:
        hits = [
            name
            for name, holder in holders
            if (
                hasattr(holder, "__dataclass_fields__")
                and field in holder.__dataclass_fields__
            )
            or (isinstance(holder, dict) and field in holder)
        ]
        assert hits, (
            f"AC-FR1301-01: FailureDecision must declare field {field!r} "
            f"on a public dataclass/TypedDict; checked {len(holders)} "
            f"candidate(s) {[n for n, _ in holders]!r}, none carried {field!r}."
        )
