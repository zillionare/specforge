#!/usr/bin/env python3
"""AC traceability closure scanner for v0.14-001-workflow-reflow-spec.

Verifies that every AC ID declared in ``acceptance.md`` is referenced by at
least one test file under ``tests/``, that every test file references at
least one valid AC ID, and that no test references an unknown AC ID.

Exit codes:
    0: All 82 AC IDs are covered; no unknown IDs; no tests without AC.
    1: Otherwise.

Usage::

    python tools/check_ac_traceability.py \\
        --acceptance .louke/project/specs/v0.14-001-workflow-reflow-spec/acceptance.md \\
        --tests tests

The tool is independent of ``lk agent`` and does not import any ``louke.*``
module, so it can be run from a clean wheel install.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_AC_ID_PATTERN = re.compile(r"\bAC-(?:FR|NFR)\d{4}-\d{2}\b", re.IGNORECASE)
_REQUIREMENT_ID_PATTERN = re.compile(r"\b(?:FR|NFR)-\d{4}\b", re.IGNORECASE)
_TEST_EXTS: frozenset[str] = frozenset({".py", ".bats", ".js", ".ts"})


@dataclass(frozen=True)
class ClosureReport:
    """Result of :func:`build_closure_report`.

    Attributes:
        total_ac_count: Number of AC IDs declared in ``acceptance.md``.
        covered_ids: AC IDs referenced by at least one test.
        uncovered_ids: AC IDs declared but not referenced by any test.
        unknown_ids: AC IDs declared in ``acceptance.md`` whose FR/NFR
            requirement is absent from the sibling ``spec.md``.
        tests_without_ac: Test file names that do not reference any AC ID.
    """

    total_ac_count: int
    covered_ids: frozenset[str]
    uncovered_ids: frozenset[str]
    unknown_ids: frozenset[str]
    tests_without_ac: tuple[str, ...]


def extract_ac_ids(acceptance_path: Path) -> frozenset[str]:
    """Return the set of AC IDs declared in ``acceptance_path``.

    Args:
        acceptance_path: Path to ``acceptance.md``.

    Returns:
        A frozenset of uppercased AC IDs (e.g. ``AC-FR0100-01``).
    """
    text = acceptance_path.read_text(encoding="utf-8")
    return frozenset(m.group(0).upper() for m in _AC_ID_PATTERN.finditer(text))


def extract_requirement_ids(spec_path: Path) -> frozenset[str]:
    """Return the FR/NFR requirement IDs declared in ``spec.md``.

    Args:
        spec_path: Path to the specification document.

    Returns:
        A frozenset of uppercased requirement IDs such as ``FR-0100``.
    """
    text = spec_path.read_text(encoding="utf-8")
    return frozenset(m.group(0).upper() for m in _REQUIREMENT_ID_PATTERN.finditer(text))


def _requirement_id(ac_id: str) -> str:
    """Return the FR/NFR requirement ID associated with an AC ID."""
    match = re.fullmatch(r"AC-(FR|NFR)(\d{4})-\d{2}", ac_id, re.IGNORECASE)
    if match is None:
        raise ValueError(f"invalid AC ID: {ac_id}")
    return f"{match.group(1).upper()}-{match.group(2)}"


def _acceptance_ids_missing_from_spec(
    acceptance_ids: frozenset[str], spec_requirements: frozenset[str]
) -> frozenset[str]:
    """Return acceptance IDs whose parent requirement is absent from spec."""
    return frozenset(
        ac_id
        for ac_id in acceptance_ids
        if _requirement_id(ac_id) not in spec_requirements
    )


def _iter_test_files(tests_path: Path) -> Iterable[Path]:
    """Yield test files under ``tests_path`` recursively.

    Skips package markers (``__init__.py``), pytest fixtures
    (``conftest.py``) and runner scripts (``run_e2e.py``,
    ``run-project-venv``) since these are not automated tests and the
    spec/test-plan §1.4 #1 only requires *automated tests* to carry an AC
    reference.
    """
    _non_test_names: frozenset[str] = frozenset(
        {"__init__.py", "conftest.py", "run_e2e.py", "run-project-venv"}
    )
    for path in sorted(tests_path.rglob("*")):
        if not path.is_file():
            continue
        if path.name in _non_test_names:
            continue
        if path.suffix not in _TEST_EXTS:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


def _normalize_tests_paths(tests_path: Path | Iterable[Path]) -> tuple[Path, ...]:
    """Normalise ``tests_path`` to a tuple of one or more test roots.

    Accepts either a single :class:`Path` (backward compatible) or an
    iterable of paths (multi-root scoping). A single path lets the legacy
    ``--tests tests`` invocation keep working; multiple paths let a
    spec-scoped gate measure only that spec's own test directories so
    cross-spec AC tokens cannot mask a coverage gap.
    """
    if isinstance(tests_path, Path):
        return (tests_path,)
    return tuple(tests_path)


def collect_ac_refs(tests_path: Path | Iterable[Path]) -> frozenset[str]:
    """Return the set of AC IDs referenced by any test file under
    ``tests_path`` (a single root or an iterable of roots)."""
    refs: set[str] = set()
    for root in _normalize_tests_paths(tests_path):
        for path in _iter_test_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _AC_ID_PATTERN.finditer(text):
                refs.add(m.group(0).upper())
    return frozenset(refs)


def _tests_without_ac(tests_path: Path | Iterable[Path]) -> tuple[str, ...]:
    """Return test file names that do not reference any AC ID."""
    without: list[str] = []
    for root in _normalize_tests_paths(tests_path):
        for path in _iter_test_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not _AC_ID_PATTERN.search(text):
                without.append(path.name)
    return tuple(sorted(set(without)))


def build_closure_report(
    *,
    acceptance_path: Path,
    tests_path: Path | Iterable[Path],
    spec_path: Path | None = None,
) -> ClosureReport:
    """Build the AC closure report.

    Args:
        acceptance_path: Path to ``acceptance.md``.
        tests_path: A single ``tests/`` root or an iterable of roots.
            Multiple roots scope the scan to a spec's own test directories
            so cross-spec AC tokens cannot mask a coverage gap.
        spec_path: Optional path to ``spec.md``. Defaults to the sibling
            ``spec.md`` next to ``acceptance_path``.

    Returns:
        A :class:`ClosureReport` with covered/uncovered/unknown IDs and
        tests without AC.
    """
    declared = extract_ac_ids(acceptance_path)
    referenced = collect_ac_refs(tests_path)
    covered = declared & referenced
    uncovered = declared - referenced
    spec = spec_path or acceptance_path.with_name("spec.md")
    requirements = extract_requirement_ids(spec)
    unknown = _acceptance_ids_missing_from_spec(declared, requirements)
    tests_without = _tests_without_ac(tests_path)
    return ClosureReport(
        total_ac_count=len(declared),
        covered_ids=covered,
        uncovered_ids=uncovered,
        unknown_ids=unknown,
        tests_without_ac=tests_without,
    )


def _format_report(report: ClosureReport) -> str:
    """Format ``report`` as a human-readable multi-line string."""
    lines = [
        f"AC closure: {len(report.covered_ids)}/{report.total_ac_count} covered",
    ]
    if report.uncovered_ids:
        lines.append("Uncovered AC IDs: " + ", ".join(sorted(report.uncovered_ids)))
    if report.unknown_ids:
        lines.append(
            "Unknown AC IDs (declared in acceptance but not in spec): "
            + ", ".join(sorted(report.unknown_ids))
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` when all declared AC IDs are covered and no acceptance/spec
        drift is present; ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description="AC traceability closure scanner.")
    parser.add_argument(
        "--acceptance",
        type=Path,
        required=True,
        help="Path to acceptance.md",
    )
    parser.add_argument(
        "--tests",
        type=Path,
        nargs="+",
        required=True,
        help=(
            "One or more test roots. A single root scans the whole tree; "
            "multiple roots scope the scan to a spec's own test directories."
        ),
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="Expected number of declared acceptance IDs; mismatch fails closed",
    )
    args = parser.parse_args(argv)
    if not args.acceptance.is_file():
        print(f"acceptance file not found: {args.acceptance}", file=sys.stderr)
        return 1
    for tests_root in args.tests:
        if not tests_root.is_dir():
            print(f"tests directory not found: {tests_root}", file=sys.stderr)
            return 1
    report = build_closure_report(
        acceptance_path=args.acceptance,
        tests_path=args.tests,
    )
    print(_format_report(report))
    if args.expected_count is not None and report.total_ac_count != args.expected_count:
        print(
            f"Acceptance declaration count {report.total_ac_count} does not match "
            f"expected {args.expected_count}"
        )
        return 1
    if report.uncovered_ids or report.unknown_ids:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
