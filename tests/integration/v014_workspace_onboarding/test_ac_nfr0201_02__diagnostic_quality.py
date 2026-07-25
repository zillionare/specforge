"""AC-NFR0201-02 — actionable, non-secret failure diagnostics (integration layer).

AC-NFR0201-02

Representative failure results across the external checks (OpenCode/model,
``gh``, Git) must carry an actionable diagnosis shaped
``{object, known_facts, impact, recovery_url}`` — not just an internal
exception, a run ID, or a generic "failure" — and the diagnosis must be
non-secret (interfaces §IF-ENV-01 ``EnvironmentStep.diagnosis``, §IF-SETUP-03
``ModelCheck.diagnosis``; acceptance AC-NFR0201-02).

These tests drive the real ``louke.web.opencode_probe`` and
``louke.web.environment_gate`` modules. Only the external ``opencode``
subprocess is substituted (monkeypatched), per test-plan §6.2; the modules
under test are never stubbed.

ATDD RED: the shipped probe diagnosis is ``{"reason", "exit_code",
"stderr_snippet"}`` (no actionable four-field shape, and ``stderr_snippet``
can leak a provider secret), so the diagnosis-shape and non-secret tests
fail until the diagnostic contract lands.
"""

from __future__ import annotations

import subprocess

from louke.web import environment_gate, opencode_probe
from louke.web.opencode_probe import PROBE_PROMPT


#: The actionable diagnosis fields required by AC-NFR0201-02 / interfaces.md.
_ACTIONABLE_FIELDS: tuple[str, ...] = (
    "object",
    "known_facts",
    "impact",
    "recovery_url",
)


def test_ac_nfr0201_02_timeout_diagnosis_is_actionable(monkeypatch) -> None:
    """AC-NFR0201-02: a timed-out probe diagnosis carries the four actionable fields."""

    # AC-NFR0201-02
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )
    assert result.state == "uncertain"
    assert result.diagnosis is not None, (
        "AC-NFR0201-02: a failed probe must carry a diagnosis"
    )
    for field_name in _ACTIONABLE_FIELDS:
        assert field_name in result.diagnosis, (
            "AC-NFR0201-02: diagnosis must carry actionable field "
            f"{field_name!r}; got {sorted(result.diagnosis)}"
        )


def test_ac_nfr0201_02_nonzero_exit_diagnosis_is_actionable(monkeypatch) -> None:
    """AC-NFR0201-02: a non-zero-exit probe diagnosis carries the four actionable fields."""

    # AC-NFR0201-02
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr="boom"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )
    assert result.state == "failed"
    assert result.diagnosis is not None
    for field_name in _ACTIONABLE_FIELDS:
        assert field_name in result.diagnosis, (
            "AC-NFR0201-02: diagnosis must carry actionable field "
            f"{field_name!r}; got {sorted(result.diagnosis)}"
        )


def test_ac_nfr0201_02_diagnosis_never_leaks_provider_secret(monkeypatch) -> None:
    """AC-NFR0201-02: a secret in provider stderr must be redacted from the diagnosis."""
    # AC-NFR0201-02
    secret = "SECRET_V014004_PROVIDER_TOKEN"

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr=f"auth failed: {secret}"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )
    assert result.diagnosis is not None
    blob = repr(result.diagnosis)
    assert secret not in blob, (
        "AC-NFR0201-02: provider secret must be redacted from the diagnosis; "
        f"diagnosis was {result.diagnosis!r}"
    )


def test_ac_nfr0201_02_env_step_contract_exposes_diagnosis_slot() -> None:
    """AC-NFR0201-02: every environment step exposes a diagnosis slot for actionable failure."""
    # AC-NFR0201-02
    check = environment_gate.start_check(workspace_id="ws_nfr0201")
    assert check["steps"], "AC-NFR0201-02: environment check must expose its steps"
    for step in check["steps"]:
        assert "diagnosis" in step, (
            f"AC-NFR0201-02: step {step.get('id')!r} must expose a diagnosis slot"
        )
