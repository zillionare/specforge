"""AC-FR0501-01 / AC-FR1001-01 — IF-HOST-RUNNER-01 contract.

Cross-module: ``Host Required-Test Adapter`` × ``ATDD Checkpoint`` ×
``Runtime Facts``.

The host runner is the only piece that touches ``tests/e2e/run-project-venv``
with both a deterministic discovery contract (no inline fallback) and an
evidence normaliser that produces IF-HOST-TEST-EVIDENCE-01 payloads.

What the integration test pins down:
* ``execute_host_tests`` is keyword-only and accepts
  ``project_root, contract_path, bundle_path, phase, candidate_identity,
  evidence_path``;
* the ``phase`` parameter is gated by a closed enum
  (``pre-red | required-green | restored-green | closure``) so that
  Shield cannot smuggle a different lifecycle tag past the gate;
* the function raises ``NotImplementedError("IF-HOST-RUNNER-01")`` to
  bind the stub's RED to the contract anchor.
"""

from __future__ import annotations

import inspect
from pathlib import Path


from louke.runtime import host_required_tests


EXPECTED_PHASES = ("pre-red", "required-green", "restored-green", "closure")


def _sig(fn):
    return inspect.signature(fn)


def test_ac_fr1001_01_execute_host_tests_phase_set_is_closed() -> None:
    """AC-FR1001-01: ``phase`` must be one of the four documented values.

    The contract enumerates exactly four phases. We probe through the
    public surface: a function call with each phase value must either
    be accepted by the (eventual) implementation or fall into one of
    the supported branches in the closed phase set. Since today the
    stub raises ``NotImplementedError`` before any branch logic
    runs, we instead assert the contract validity at the **enumeration
    level**: a public symbol (enum / Literal / Final constant list)
    that enumerates exactly the four phases, OR — while the stub
    still raises — that each phase name is recognised as a string
    literal consistent with IF-HOST-RUNNER-01.

    The closure check is performed via :data:`EXPECTED_PHASES` and
    surfaces back through this test by treating the stub's raise as
    proof that the phase is acknowledged (any unknown phase must
    surface a distinct error path, which we cannot check while the
    function is uniform-stub). Therefore we additionally require the
    module to expose a *closed* phase declaration — either as an
    enum, a ``Literal[...]`` annotation, or a module-level tuple of
    the exact four phases.
    """
    import enum
    import typing

    src_text = Path(host_required_tests.__file__).read_text(encoding="utf-8")
    module_attrs = {
        n: getattr(host_required_tests, n) for n in dir(host_required_tests)
    }

    phase_enum: type | None = None
    # 1. Enum named ``*Phase*``.
    for name, attr in module_attrs.items():
        if isinstance(attr, type) and issubclass(attr, enum.Enum):
            phase_enum = attr
            break

    # 2. Literal annotation on ``execute_host_tests.phase``.
    sig = _sig(host_required_tests.execute_host_tests)
    phase_param = sig.parameters["phase"]
    literal_match: tuple[str, ...] | None = None
    annotation = (
        typing.get_type_hints(host_required_tests.execute_host_tests).get("phase")
        if hasattr(typing, "get_type_hints")
        else phase_param.annotation
    )
    if typing.get_origin(annotation) is typing.Literal:
        literal_match = tuple(typing.get_args(annotation))

    # 3. Module-level tuple constant carrying the four phases.
    tuple_constant: tuple[str, ...] | None = None
    for name, attr in module_attrs.items():
        if (
            isinstance(attr, tuple)
            and len(attr) == 4
            and set(attr) == set(EXPECTED_PHASES)
        ):
            tuple_constant = attr

    declared = (
        (phase_enum, "enum")
        if phase_enum
        else ("literal", "annotation")
        if literal_match
        else (tuple_constant, "tuple")
        if tuple_constant
        else (None, "")
    )

    decl_value, decl_kind = declared
    assert decl_value is not None, (
        "AC-FR1001-01: the closed phase set "
        f"{EXPECTED_PHASES!r} must be declared on the public surface "
        "of ``louke.runtime.host_required_tests``. Acceptable forms: "
        "(a) an ``enum.Enum`` class declaring exactly the four phases, "
        "(b) a ``typing.Literal[...]`` annotation on "
        "``execute_host_tests.phase``, "
        "(c) a module-level tuple constant matching the four phases. "
        f"Got enum={phase_enum!r}, literal={literal_match!r}, "
        f"tuple={tuple_constant!r}. Source bytes "
        f"({len(src_text)}) were scanned but contain no enumerated declaration."
    )

    if phase_enum is not None:
        members = set(member.value for member in phase_enum)
        assert members == set(EXPECTED_PHASES), (
            f"AC-FR1001-01: declared phase enum {phase_enum!r} must carry "
            f"exactly the four closed phases {sorted(EXPECTED_PHASES)!r}; "
            f"got {sorted(members)!r}"
        )
    elif literal_match is not None:
        assert set(literal_match) == set(EXPECTED_PHASES), (
            f"AC-FR1001-01: typing.Literal annotation on phase must be "
            f"exactly the four closed phases {sorted(EXPECTED_PHASES)!r}; "
            f"got {sorted(literal_match)!r}"
        )


def test_ac_fr1001_01_execute_host_tests_signature_has_all_run_kwargs() -> None:
    """AC-FR1001-01: execute_host_tests accepts the 6 documented kwargs.

    Each kwarg is bound into the evidence envelope (per IF-HOST-TEST-EVIDENCE-01);
    dropping one would let Shield run without a candidate identity, which
    AC-FR1101-02 closes.
    """
    fn = host_required_tests.execute_host_tests
    expected = {
        "project_root",
        "contract_path",
        "bundle_path",
        "phase",
        "candidate_identity",
        "evidence_path",
    }
    actual = set(_sig(fn).parameters)
    assert actual == expected, (
        f"AC-FR1001-01: execute_host_tests kwargs drifted: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_ac_fr1001_01_execute_host_tests_only_keyword_only() -> None:
    """AC-FR1001-01: execute_host_tests must use keyword-only parameters.

    A positional caller could misorder ``phase`` / ``candidate_identity``
    silently. The contract treats every public ATDD API as keyword-only.
    """
    params = list(_sig(host_required_tests.execute_host_tests).parameters.values())
    kinds = {p.kind for p in params}
    assert inspect.Parameter.KEYWORD_ONLY in kinds, (
        "AC-FR1001-01: execute_host_tests must declare at least one keyword-only "
        f"parameter; got kinds={kinds}"
    )
    # All non-self parameters should be keyword-only.
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params), (
        "AC-FR1001-01: every parameter of execute_host_tests must be keyword-only."
    )


def test_ac_fr1001_01_execute_host_tests_raises_if_runner_token() -> None:
    """The stub raises NotImplementedError with the IF-host-runner-01 token.

    This binds RED evidence to the correct contract anchor. Without
    this assertion the test would still fail (NotImplementedError), but
    the attribution would be lost.
    """
    import re

    src = Path(host_required_tests.__file__).read_text(encoding="utf-8")
    assert re.search(
        r"""NotImplementedError\(["']IF-HOST-RUNNER-01["']\)""",
        src,
    ), (
        "AC-FR1001-01: execute_host_tests must raise "
        'NotImplementedError("IF-HOST-RUNNER-01") to bind RED to the '
        "contract anchor; current source lacks that exact string."
    )
