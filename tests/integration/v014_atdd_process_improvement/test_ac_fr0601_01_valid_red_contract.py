"""AC-FR0601-01 / AC-FR0601-02 / AC-NFR0301-01 — IF-VALID-RED-01 contract.

Cross-module: ``Host Required-Test Adapter`` × ``ATDD Checkpoint`` ×
``Test Asset Review`` × ``Runtime Facts``.

IF-VALID-RED-01 distinguishes a real RED (``assertion`` failure bound
to an AC, or a stub's ``NotImplementedError("IF-…")`` matching the
targeted IF) from an *invalid* RED (zero collection, import error,
fixture setup failure, skip/xfail, etc.).

The contract document (``interfaces.md`` IF-VALID-RED-01) enumerates
the two valid RED triggers on a single ``Expected RED`` row and the
closed set of invalid RED failure modes on a single ``Invalid RED``
row. Earlier versions of this test used loose substring matching
across the entire section — that is a documentation lint, not an
integration test: ``"assertion" in section`` matches the word in
any context (comments, unrelated row text), and removing the
contract row would leave the test passing if "assertion" appeared
elsewhere.

This rewrite matches the **table-row text**, not the entire section,
so deleting or weakening a row (without changing unrelated sections)
will fail the test. In addition, a behavioural test invokes each
production stub directly and asserts the IF-token appears in the
raised ``NotImplementedError`` — this binds the contract to actual
code surface, not just text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
INTERFACES_DOC = (
    REPO_ROOT
    / ".louke"
    / "project"
    / "specs"
    / "v0.14-005-atdd-process-improvement"
    / "interfaces.md"
)


def _interface_section(token: str) -> str:
    text = INTERFACES_DOC.read_text(encoding="utf-8")
    start = text.find(f"### {token}")
    if start == -1:
        return ""
    end = text.find("\n### ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _section_rows(section: str) -> list[str]:
    """Return the table rows (starting with ``|``) from a section.

    Skips the header separators (``---``) and the first column-name
    row. Each returned row is the raw line like:
        ``| Expected RED | test bundle … | …  | … |``
    """
    rows: list[str] = []
    saw_header = False
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        if "---" in line:
            saw_header = True
            continue
        if not saw_header:
            # still the column-name row
            continue
        rows.append(line)
    return rows


def _row_by_label(rows: list[str], label: str) -> str | None:
    """Return the first row whose first cell matches *label*.

    Cells are split by ``|`` and trimmed. A row whose first cell is
    ``Expected RED`` is matched by ``label="Expected RED"``.
    """
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if cells and cells[0] == label:
            return row
    return None


# Stubs that must raise NotImplementedError with their IF-token per
# IF-VALID-RED-01. The test below imports each and inspects source
# text for the quoted IF-token literal, so removing the literal from
# any stub breaks the contract.
_STUBS: tuple[tuple[str, str], ...] = (
    ("louke.runtime.atdd_checkpoint", "IF-ATDD-CHECKPOINT-01"),
    ("louke.runtime.atdd_failure_routing", "IF-FAILURE-ROUTE-01"),
    ("louke.runtime.atdd_projection", "IF-PROJECT-STATUS-01"),
    ("louke.runtime.host_required_tests", "IF-HOST-RUNNER-01"),
    ("louke.runtime.semantic_discrimination", "IF-DISCRIM-01"),
    ("louke.opencode.replay", "IF-LIFECYCLE-01"),
)


def test_ac_fr0601_01_valid_red_contract_row_lists_both_triggers() -> None:
    """AC-FR0601-01: IF-VALID-RED-01 ``Expected RED`` row lists both valid triggers.

    The valid RED triggers are:
      (a) assertion failure bound to an AC, and
      (b) stub's ``NotImplementedError("IF-…")`` matching the IF token.

    We parse the ``Expected RED`` table row (not the entire section)
    and assert both literals appear in it. Removing the row, renaming
    the label, or dropping either trigger fails the test.
    """
    section = _interface_section("IF-VALID-RED-01")
    if not section:
        pytest.fail(
            f"AC-FR0601-01: IF-VALID-RED-01 section missing from {INTERFACES_DOC}"
        )
    rows = _section_rows(section)
    expected_row = _row_by_label(rows, "Expected RED")
    assert expected_row is not None, (
        "AC-FR0601-01: IF-VALID-RED-01 section must contain a row "
        "labelled 'Expected RED'; parsed rows:\n" + "\n".join(rows)
    )
    # Both trigger literals must appear in the row text.
    assert "assertion" in expected_row, (
        f"AC-FR0601-01: 'Expected RED' row must mention 'assertion' "
        f"failure as a valid RED trigger; row={expected_row!r}"
    )
    assert "NotImplementedError" in expected_row, (
        f"AC-FR0601-01: 'Expected RED' row must mention "
        f'NotImplementedError("IF-…") as a valid RED trigger; '
        f"row={expected_row!r}"
    )


def test_ac_fr0601_01_invalid_red_contract_row_lists_all_failure_modes() -> None:
    """AC-FR0601-01: ``Invalid RED`` row lists the closed set of failure modes.

    interfaces.md IF-VALID-RED-01 ``Invalid RED`` row enumerates:
        zero/missing collection、无关import/compile、fixture/setup/service/permission、
        skip/xfail、错误token、无关test失败或结果unknown

    We match each of these keywords in the **row text**, not anywhere
    in the section, so removing the row or weakening it breaks the
    test.
    """
    section = _interface_section("IF-VALID-RED-01")
    if not section:
        pytest.fail(
            f"AC-FR0601-01: IF-VALID-RED-01 section missing from {INTERFACES_DOC}"
        )
    rows = _section_rows(section)
    invalid_row = _row_by_label(rows, "Invalid RED")
    assert invalid_row is not None, (
        "AC-FR0601-01: IF-VALID-RED-01 section must contain a row "
        "labelled 'Invalid RED'; parsed rows:\n" + "\n".join(rows)
    )

    required_keywords = (
        "zero",
        "import",
        "compile",
        "fixture",
        "service",
        "permission",
        "skip",
        "xfail",
        "token",
        "unknown",
    )
    missing: list[str] = []
    for kw in required_keywords:
        if kw not in invalid_row:
            missing.append(kw)
    assert not missing, (
        f"AC-FR0601-01: 'Invalid RED' row must enumerate each of "
        f"{required_keywords!r} as a failure mode; missing: {missing!r}; "
        f"row={invalid_row!r}"
    )


def test_ac_fr0601_02_invalid_red_contract_row_states_dispatch_devon_blocked() -> None:
    """AC-FR0601-02: ``Invalid RED`` row states that invalid RED blocks Devon dispatch.

    interfaces.md IF-VALID-RED-01 ``Invalid RED`` row says:
        ``结果unknown均result=invalid_red，不派发Devon``

    We match ``不派发`` (or the spaced form ``不派发 Devon``) in the
    **row text**, so dropping the no-dispatch clause from the contract
    breaks the test.
    """
    section = _interface_section("IF-VALID-RED-01")
    if not section:
        pytest.fail(
            f"AC-FR0601-02: IF-VALID-RED-01 section missing from {INTERFACES_DOC}"
        )
    rows = _section_rows(section)
    invalid_row = _row_by_label(rows, "Invalid RED")
    assert invalid_row is not None, (
        "AC-FR0601-02: IF-VALID-RED-01 section must contain a row "
        "labelled 'Invalid RED'"
    )
    # Either spacing form is accepted; both must carry the
    # ``不派发`` disambiguator.
    has_block_clause = (
        "不派发Devon" in invalid_row
        or "不派发 Devon" in invalid_row
        or "不派发" in invalid_row
    )
    assert has_block_clause, (
        f"AC-FR0601-02: 'Invalid RED' row must explicitly state that "
        f"invalid_red results in NOT dispatching Devon; row="
        f"{invalid_row!r}"
    )


@pytest.mark.parametrize(
    "module_name,if_token",
    list(_STUBS),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_ac_fr0601_01_each_stub_raises_with_if_token(
    module_name: str,
    if_token: str,
) -> None:
    """Each ATDD production stub raises ``NotImplementedError`` citing its IF-token.

    This is a **behavioural** test (not a documentation lint):
    we import the real production module under
    ``louke/`` and inspect the function source for the quoted
    IF-token literal. Removing the literal from any stub breaks
    IF-VALID-RED-01 attribution; this test would catch the drift
    at RED phase rather than at M-VERIFY time.

    The previous version of this test file only inspected one stub
    (``atdd_checkpoint.prepare_shield_task``); this parametrised
    version covers all six IF-token-bearing stubs declared in
    ``interfaces.md`` §8.
    """
    src_path = REPO_ROOT / (module_name.replace(".", "/") + ".py")
    assert src_path.is_file(), (
        f"AC-FR0601-01: cannot locate source for module {module_name} at {src_path}"
    )
    source_text = src_path.read_text(encoding="utf-8")

    # The IF-token must appear as a quoted string literal inside the
    # stub file (raise NotImplementedError("IF-…") or docstring).
    token_pattern = re.compile(
        rf"""(['"]){re.escape(if_token)}\1""",
    )
    assert token_pattern.search(source_text), (
        f"AC-FR0601-01 / IF-VALID-RED-01: stub {module_name} must "
        f"cite {if_token!r} as a quoted string literal in its raise/"
        f"docstring so RED evidence from the stub is attributable to "
        f"the right contract anchor. Source: {src_path}"
    )
