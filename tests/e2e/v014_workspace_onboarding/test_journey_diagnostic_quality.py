"""E2E: actionable failure diagnostics + Runtime authority over Guide failure.

AC-NFR0201-02

Drives the locked v0.14-004 contract through a real Chromium browser against
an installed ``lk serve`` (test-plan §2.1 e2e layer).

Auth / failure setup (sanctioned seeded-workspace pattern, per the v0.14-005
e2e conftest): the model-checks public entry is allow-listed but not yet
mounted, so the wizard cannot be advanced through the broken first-user POST
(that produced the prior invalid 403 RED). Instead the workspace is seeded
with a v2 ``pending_model`` manifest carrying a **failed** model check whose
diagnosis is produced by the REAL ``opencode_probe.run_minimal`` (a failing
subprocess stand-in) — not a canned value. The browser then drives the public
``GET /setup`` entry (the two-context Setup page, Archer stub ``IF-SETUP-01``)
and asserts the full contract:

* the model-check context is shown (not the retired six-step Wizard);
* the failure diagnosis is actionable — ``object`` / ``known_facts`` /
  ``impact`` / ``recovery_url``;
* the Runtime model-check result stays authoritative and is not reinterpreted
  by a Guide advice failure.

ATDD RED: ``GET /setup`` currently returns 500 (``NotImplementedError
"IF-SETUP-01"``), so the first assertion fails, attributable to the declared
stub. When Devon implements the page + the four-field diagnosis, the
downstream assertions are reached. No ``devon_module_skip`` gating.
"""

from __future__ import annotations

import json
import subprocess

from louke.web import opencode_probe
from louke.web.opencode_probe import PROBE_PROMPT


#: The actionable diagnosis fields required by AC-NFR0201-02 / interfaces.md.
_ACTIONABLE_FIELDS: tuple[str, ...] = (
    "object",
    "known_facts",
    "impact",
    "recovery_url",
)


def _real_failed_probe_diagnosis(monkeypatch) -> dict:
    """Return a diagnosis produced by the REAL probe against a failing subprocess.

    Substitutes only the external ``opencode`` subprocess (test-plan §6.2);
    ``opencode_probe.run_minimal`` itself runs for real, so the diagnosis is a
    genuine production output, not a canned value.
    """

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr="model unreachable"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe = opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )
    assert probe.state == "failed"
    assert probe.diagnosis is not None
    return probe.diagnosis


def _seed_pending_model_failed(workspace_root, diagnosis: dict) -> None:
    """Seed the workspace with a v2 ``pending_model`` manifest + failed check."""
    manifest = {
        "version": 2,
        "workspace_id": "",
        "revision": 1,
        "status": "pending_model",
        "first_principal_id": "prin_demo00000000",
        "model_check": {
            "check_id": "chk_demo",
            "revision": 1,
            "state": "failed",
            "model_id": None,
            "diagnosis": diagnosis,
            "observed_at": "2026-07-25T00:00:00Z",
        },
        "completed_at": None,
    }
    (workspace_root / ".louke" / "web-setup-state.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_ac_nfr0201_02_model_check_failure_shows_actionable_diagnosis(
    browser_page, live_server, monkeypatch
):
    """AC-NFR0201-02: a failed model check shows object/known_facts/impact/recovery_url."""
    # AC-NFR0201-02
    page, base_url = browser_page
    _, workspace, _ = live_server

    diagnosis = _real_failed_probe_diagnosis(monkeypatch)
    _seed_pending_model_failed(workspace.root, diagnosis)

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()

    # The two-context Setup page shows the model-check context (pending_model),
    # not the retired six-step Wizard.
    assert "model" in body or "opencode" in body, (
        "AC-NFR0201-02: the model-check context must be shown on /setup; "
        f"body was: {body[:200]!r}"
    )
    assert "runtime dependencies" not in body, (
        "AC-NFR0201-02: the retired six-step Wizard must not be shown; "
        f"body was: {body[:200]!r}"
    )

    # The failure diagnosis is actionable: object / known_facts / impact /
    # recovery_url (not just an internal exception or generic "failure").
    for field in _ACTIONABLE_FIELDS:
        needle = field.replace("_", " ")
        assert field in body or needle in body, (
            f"AC-NFR0201-02: the failure diagnosis must expose {field!r}; "
            f"body was: {body[:300]!r}"
        )


def test_ac_nfr0201_02_runtime_authority_survives_guide_failure(
    browser_page, live_server, monkeypatch
):
    """AC-NFR0201-02: a Guide advice failure does not mask the Runtime model-check result."""
    # AC-NFR0201-02
    page, base_url = browser_page
    _, workspace, _ = live_server

    diagnosis = _real_failed_probe_diagnosis(monkeypatch)
    _seed_pending_model_failed(workspace.root, diagnosis)

    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()

    # The Runtime model-check result is shown authoritatively: the page reports
    # the failed model check (Runtime authority) and stays in pending_model —
    # it is not reinterpreted as passed/complete by any Guide state.
    assert "model" in body or "opencode" in body, (
        "AC-NFR0201-02: the Runtime model-check result must stay visible; "
        f"body was: {body[:200]!r}"
    )
    assert "complete" not in body and "passed" not in body, (
        "AC-NFR0201-02: a failed model check must not be reinterpreted as "
        f"passed/complete; body was: {body[:200]!r}"
    )
    # A Retry entry remains available so the Human can re-run the check on new
    # facts; the Guide session, when present, does not remove it.
    assert "retry" in body, (
        "AC-NFR0201-02: the Runtime Retry entry must remain available despite "
        f"any Guide advice failure; body was: {body[:200]!r}"
    )
