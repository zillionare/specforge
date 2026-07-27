"""Freshness, idempotency, and secret-free Login readiness contracts.

AC-NFR0001-01, AC-NFR0001-02, AC-NFR0201-01, AC-NFR0101-01

The removed Setup manifest is intentionally not referenced here: current
readiness is a fresh projection, while durable release previews remain owned
by Runtime. These tests exercise the real model probe and browser-draft
surface, not a private Setup state machine.
"""

from __future__ import annotations

import subprocess

from louke.web.draft_storage import create_draft


def test_browser_draft_payload_omits_forbidden_fields() -> None:
    """AC-NFR0001-01: browser drafts carry no credential or identity fields."""
    # AC-NFR0001-01
    draft = create_draft(
        workspace_id="github.com/example/fixture",
        principal_id="fixture-human",
        story="draft story",
    )
    forbidden = {
        "credential",
        "password",
        "token",
        "repository_url",
        "preview_id",
        "preview_token",
        "project_identity",
    }
    assert not (forbidden & set(draft.keys())), (
        f"draft leaked forbidden keys: {forbidden & set(draft.keys())}"
    )


def test_opencode_probe_timeout_classifies_uncertain(monkeypatch) -> None:
    """AC-NFR0201-01: timeout is uncertain and never falsely passed."""
    # AC-NFR0201-01
    from louke.web.opencode_probe import run_minimal

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_minimal(model_id="fixture/model", deadline_seconds=15)
    assert result.state == "uncertain"
    assert result.diagnosis is not None


def test_opencode_probe_executable_missing_is_failed(monkeypatch) -> None:
    """AC-NFR0201-01: missing executable is failed with a diagnosis."""
    # AC-NFR0201-01
    from louke.web.opencode_probe import run_minimal

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no such executable")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = run_minimal(model_id="fixture/model", deadline_seconds=15)
    assert result.state == "failed"
    assert result.diagnosis is not None


def test_synthetic_host_does_not_persist_real_secret(tmp_path) -> None:
    """AC-NFR0101-01: isolated host metadata remains free of a canary."""
    # AC-NFR0101-01
    canary = "SECRET_V014004_TEST"
    from tests.integration.v014_workspace_onboarding._mode_b import (
        synthetic_host_project,
    )

    with synthetic_host_project(marker="canary") as synth:
        project_toml = synth / ".louke" / "project" / "project.toml"
        before = project_toml.read_text(encoding="utf-8")
        assert canary not in before
        (synth / "canary.txt").write_text(canary, encoding="utf-8")
        after = project_toml.read_text(encoding="utf-8")
        assert before == after
        assert canary in (synth / "canary.txt").read_text(encoding="utf-8")
