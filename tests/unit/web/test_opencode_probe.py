"""Unit tests for the OpenCode probe diagnosis contract (IF-SETUP-03 / AC-NFR0201-02).

The probe diagnosis must be *actionable* — shaped
``{object, known_facts, impact, recovery_url}`` (interfaces §IF-SETUP-03
``ModelCheck.diagnosis``, acceptance AC-NFR0201-02) — while preserving the
``reason`` discriminator the Setup projection contract relies on, and must
never leak a provider secret carried in subprocess stderr.

Only the external ``opencode`` subprocess is substituted (monkeypatched);
``opencode_probe.run_minimal`` itself runs for real.
"""

from __future__ import annotations

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


def _run(monkeypatch, completed: subprocess.CompletedProcess | None = None,
         exc: Exception | None = None) -> opencode_probe.ProbeResult:
    """Drive ``run_minimal`` against a substituted subprocess."""

    def fake_run(*args, **kwargs):
        if exc is not None:
            raise exc
        return completed

    monkeypatch.setattr(subprocess, "run", fake_run)
    return opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )


def test_timeout_diagnosis_is_actionable_and_uncertain(monkeypatch) -> None:
    """AC-NFR0201-02: a timed-out probe is ``uncertain`` with the four fields."""
    result = _run(
        monkeypatch,
        exc=subprocess.TimeoutExpired(cmd=["opencode"], timeout=15),
    )
    assert result.state == "uncertain"
    assert result.diagnosis is not None
    assert result.diagnosis["reason"] == "timeout"
    for field_name in _ACTIONABLE_FIELDS:
        assert field_name in result.diagnosis


def test_nonzero_exit_diagnosis_is_actionable_and_failed(monkeypatch) -> None:
    """AC-NFR0201-02: a non-zero exit is ``failed`` with the four fields."""
    result = _run(
        monkeypatch,
        completed=subprocess.CompletedProcess(
            args=["opencode"], returncode=1, stdout="", stderr="boom"
        ),
    )
    assert result.state == "failed"
    assert result.diagnosis is not None
    assert result.diagnosis["reason"] == "nonzero_exit"
    for field_name in _ACTIONABLE_FIELDS:
        assert field_name in result.diagnosis


def test_executable_not_found_diagnosis_is_actionable(monkeypatch) -> None:
    """AC-NFR0201-02: a missing executable carries the four actionable fields."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("opencode")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = opencode_probe.run_minimal(
        model_id="minimax/m2", prompt=PROBE_PROMPT, deadline_seconds=15
    )
    assert result.state == "failed"
    assert result.diagnosis is not None
    for field_name in _ACTIONABLE_FIELDS:
        assert field_name in result.diagnosis


def test_diagnosis_never_leaks_provider_secret(monkeypatch) -> None:
    """AC-NFR0201-02: a secret in provider stderr is redacted from the diagnosis."""
    secret = "SECRET_V014004_PROVIDER_TOKEN"
    result = _run(
        monkeypatch,
        completed=subprocess.CompletedProcess(
            args=["opencode"], returncode=1, stdout="", stderr=f"auth failed: {secret}"
        ),
    )
    assert result.diagnosis is not None
    assert secret not in repr(result.diagnosis)


def test_passed_probe_has_no_diagnosis(monkeypatch) -> None:
    """AC-FR0201-01: exit 0 means ``passed`` with no diagnosis."""
    result = _run(
        monkeypatch,
        completed=subprocess.CompletedProcess(
            args=["opencode"], returncode=0, stdout="hi", stderr=""
        ),
    )
    assert result.state == "passed"
    assert result.diagnosis is None
