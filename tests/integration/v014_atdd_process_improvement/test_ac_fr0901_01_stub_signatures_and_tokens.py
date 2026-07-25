"""AC-FR0901-01 / AC-FR1501-01 — ATDD interface stubs raise their IF-tokens.

Cross-module: every interface listed in interfaces.md §8 has a stub in the
real production module path. The stubs raise
``NotImplementedError("IF-…")`` so that:

* Shield's collection / RED phase can attribute the failure to the
  contract anchor (IF-token), not to a generic error;
* Devon's stub→implementation contract is mechanically observable: the
  signature must be importable, the token must be the same one listed in
  ``interfaces.md``, and the body must contain no business logic other
  than the raise.

A stub whose signature diverges from interfaces.md makes Devon substitute
behavior under a wrong contract; a stub whose token diverges makes Shield
bind RED evidence to the wrong anchor. Both directions fail closed.
"""

from __future__ import annotations

import inspect
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


def _stub_lock_list() -> list[dict[str, object]]:
    """Parse the interface stub lock list from interfaces.md §8.

    Each row yields a dict with ``token``, ``source_paths`` (list[str]),
    ``declarations`` (list[str]). Some rows have multiple source paths
    joined by ``、` (Chinese full-width comma + backtick), e.g.
    ``louke/web/api/project_status.py``、`louke/web/app.py``.
    """
    text = INTERFACES_DOC.read_text(encoding="utf-8")
    rows: list[dict[str, object]] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("## 8."):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"Token", "---"}:
            continue
        token = cells[0].strip("`").strip()
        source_cell = cells[1]
        declarations_raw = cells[2]
        # The source cell may use 、 (Chinese full-width comma), or
        # ``、` (CJK comma + backtick), or no separator at all.
        # Replace the CJK separator with ASCII comma before splitting.
        normalised_source = (
            source_cell.replace("`、", ",").replace("、", ",").replace("，", ",")
        )
        sources = [
            seg.strip().strip("`").strip()
            for seg in normalised_source.split(",")
            if seg.strip()
        ]
        rows.append(
            {
                "token": token,
                "sources": sources,
                "declarations": [
                    piece.strip().strip("`").strip()
                    for piece in declarations_raw.replace("`、", ",")
                    .replace("、", ",")
                    .split(",")
                    if piece.strip()
                ],
            }
        )
    return rows


# Map of stub module path → list of ``(symbol_name, kind)`` expected on disk.
# ``kind`` is informational; the test imports each name and inspects its
# signature against the declarations listed in interfaces.md §8.
EXPECTED_STUBS = {
    "louke.runtime.atdd_checkpoint": {
        "module_token": "IF-ATDD-CHECKPOINT-01",
        "names": [
            "prepare_shield_task",
            "record_shield_submission",
            "freeze_test_bundle",
            "prepare_devon_task",
            "request_declaration_revision",
            "record_implementation_result",
            "record_m_test_closure",
        ],
    },
    "louke.runtime.host_required_tests": {
        "module_token": "IF-HOST-RUNNER-01",
        "names": ["execute_host_tests"],
    },
    "louke.runtime.semantic_discrimination": {
        "module_token": "IF-DISCRIM-01",
        "names": ["run_discrimination", "verify_restored_candidate"],
    },
    "louke.runtime.atdd_failure_routing": {
        "module_token": "IF-FAILURE-ROUTE-01",
        "names": ["classify_atdd_failure"],
    },
    "louke.runtime.atdd_projection": {
        "module_token": "IF-PROJECT-STATUS-01",
        "names": ["project_atdd_status"],
    },
    "louke.opencode.replay": {
        "module_token": "IF-LIFECYCLE-01",
        "names": ["load_replay_adapter"],
    },
}


def test_ac_fr0901_01_stub_module_paths_align_with_interfaces_md() -> None:
    """Every stub row in interfaces.md §8 must correspond to a real module file.

    A spurious entry would let Devon implement the wrong surface; a missing
    one would leave Shield unable to attribute RED evidence.
    """
    rows = _stub_lock_list()
    declared_modules: set[str] = set()
    for row in rows:
        for path in row["sources"]:
            # The source cell already ends with ``.py``; keep verbatim.
            declared_modules.add(path)

    expected_modules = {key.replace(".", "/") + ".py" for key in EXPECTED_STUBS}
    expected_modules.add("louke/web/api/project_status.py")
    expected_modules.add("louke/web/app.py")  # Listed alongside project_status

    extras = declared_modules - expected_modules
    missing = expected_modules - declared_modules

    assert not extras and not missing, (
        "AC-FR0901-01: stub lock list mismatch.\n"
        f"  extras not in EXPECTED_STUBS: {sorted(extras)}\n"
        f"  EXPECTED_STUBS not in lock list: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    "module_name,expected",
    list(EXPECTED_STUBS.items()),
    ids=lambda value, *_: value if isinstance(value, str) else "",
)
def test_ac_fr0901_01_stub_signatures_present_and_keyword_only(
    module_name: str,
    expected: dict[str, object],
) -> None:
    """Each stub must import cleanly, expose the listed names, and use
    keyword-only ``*`` arguments as written by interfaces.md.

    Shield's RED-capture relies on positional vs keyword distinction
    (e.g. ``expected_run_revision``); if Devon relaxes ``*,`` the
    contract silently widens.
    """
    module = __import__(module_name, fromlist=["*"])
    for name in expected["names"]:
        assert hasattr(module, name), (
            f"AC-FR0901-01: stub {module_name}.{name} missing from "
            f"interfaces.md §8 declarations."
        )
        fn = getattr(module, name)
        sig = inspect.signature(fn)
        assert "*" in [p.kind.name for p in sig.parameters.values()] or any(
            p.kind is inspect.Parameter.KEYWORD_ONLY for p in sig.parameters.values()
        ), (
            f"AC-FR0901-01: {module_name}.{name} must declare keyword-only "
            f"parameters (interfaces.md intends all ATDD public APIs to be "
            f"keyword-only). Got {sig!r}"
        )


@pytest.mark.parametrize(
    "module_name,expected",
    list(EXPECTED_STUBS.items()),
    ids=lambda value, *_: value if isinstance(value, str) else "",
)
def test_ac_fr1501_01_stub_body_raises_its_if_token(
    module_name: str,
    expected: dict[str, object],
) -> None:
    """Calling the stub must raise ``NotImplementedError`` with the IF-token.

    This is what lets IF-VALID-RED-01 attribute the RED to the contract
    anchor instead of a generic error. A stub that raises with the
    wrong token would bind RED evidence to the wrong IF, so the parameter
    list and the raise message must both reference the IF token.
    """
    target_token = str(expected["module_token"])

    for name in expected["names"]:
        # Inspect every string literal the stub references. Each stub
        # file is small enough that scanning its text source for the
        # required token is robust and does not require invoking the
        # function (which would raise and abort pytest).
        src_path = REPO_ROOT / module_name.replace(".", "/") / "__init__.py"
        candidates = [REPO_ROOT / f"{module_name.replace('.', '/')}.py", src_path]
        actual_path = next((p for p in candidates if p.is_file()), None)
        assert actual_path is not None, (
            f"AC-FR1501-01: cannot locate source for {module_name}"
        )
        source_text = actual_path.read_text(encoding="utf-8")
        # The IF-token must appear at least once as a string literal inside
        # the stub (raise NotImplementedError("IF-…") or docstring).
        token_pattern = re.compile(
            rf"""(['"]){re.escape(target_token)}\1""",
            re.MULTILINE,
        )
        assert token_pattern.search(source_text), (
            f"AC-FR1501-01: stub {module_name}.{name} must mention "
            f"{target_token!r} as a literal string so IF-VALID-RED-01 "
            f"can attribute RED evidence to the correct contract anchor."
        )


def test_ac_fr0901_01_web_app_routes_register_stub_handlers() -> None:
    """IF-PROJECT-STATUS-01 composition root: three production routes in create_app().

    Cross-module: ``louke.web.app.create_app()`` wires the ATDD
    Project Status routes via ``louke.web.api.project_status``.
    Without these imports, the installed server would 404 on the same
    surface that AC-FR0901-01 / AC-FR1201-01 need.
    """
    from louke.web.app import create_app

    app = create_app(project_root=str(REPO_ROOT))
    paths = {route.path for route in app.router.routes}

    required = (
        "/api/projects/{project_id}/status",
        "/api/projects/{project_id}/status/checkpoints/{checkpoint_id}",
        (
            "/api/projects/{project_id}/status/checkpoints/"
            "{checkpoint_id}/actions/{action_id}"
        ),
    )
    for needle in required:
        assert any(
            needle == route.path or needle in route.path for route in app.router.routes
        ), (
            f"AC-FR0901-01: composition root create_app() must register "
            f"production route {needle!r}; got routes={sorted(paths)}"
        )
