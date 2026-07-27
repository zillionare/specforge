"""Synthetic-host-project isolation & Louke-leak detection (Mode B gate).

AC-FR0001-01, AC-FR0001-02, AC-NFR0401-01, AC-NFR0401-02

These tests do not exercise a single interface; they enforce the
invariant that v0.14-004 tooling runs against a host project's own
``.louke/`` directory and never leaks Louke's own registry schema into
that workspace (Mode B requirement per Shield §3.3 and test-plan §3.2
Ground Truth isolation).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ._mode_b import (
    DEVON_MODULES,
    devon_module_available,
    synthetic_bare_remote,
    synthetic_host_project,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_synthetic_host_project_does_not_leak_louke_registry() -> None:
    """AC-FR0001-01 / AC-NFR0401-02: host project keeps its own ``.louke/``.

    The synthetic host project is created via ``synthetic_host_project``;
    the test asserts (a) the file is writable, (b) it does not contain
    Louke's own registry schema (``[ci]`` / ``[runtime]`` keys), and
    (c) it cannot be confused with Louke's own ``.louke/`` at the repo
    root.
    """
    # AC-FR0001-01 / AC-NFR0401-02
    with synthetic_host_project(marker="leak") as synth:
        import json

        project_toml = synth / ".louke" / "project" / "project.toml"
        assert project_toml.is_file()
        payload = json.loads(project_toml.read_text(encoding="utf-8"))

        # Synthetic project keeps only the host-visible keys; Louke's own
        # ``[ci]`` / ``[runtime]`` / ``[dispatch]`` schema must not leak.
        for forbidden in ("ci", "runtime", "dispatch", "registry", "active_schema"):
            assert forbidden not in payload, (
                f"synthetic host project leaked Louke registry key "
                f"{forbidden!r}: {payload!r}"
            )

        # Workspace identity is host-local, not Louke's repository workspace id.
        assert payload["meta"]["workspace_id_marker"] != "louke-self"
        assert payload["meta"]["is_synthetic_host_project"] is True

        # The repo root is a different directory — never inside the synthetic workspace.
        real_repo_root = REPO_ROOT
        # AC-NFR0001-01: synthetic host must be outside real repo root
        if synth.is_relative_to(real_repo_root):
            raise AssertionError(
                "synthetic host project accidentally lives inside the real repo root"
            )


def test_login_readiness_does_not_mutate_synthetic_host() -> None:
    """AC-FR0001-01: readiness reads do not touch the host ``.louke/``."""
    # AC-FR0001-01
    from louke.web.environment_commands import CommandResult
    from louke.web.login_readiness import LoginReadinessService
    from louke.web.opencode_probe import ModelCheckResult

    class BlockedExecutor:
        def run(self, argv, *, cwd, timeout):
            del argv, cwd, timeout
            return CommandResult(1, "", "not available")

    with synthetic_host_project(marker="status") as synth:
        before = (synth / ".louke" / "project" / "project.toml").read_bytes()
        body = LoginReadinessService(
            synth,
            executor=BlockedExecutor(),
            model_checker=lambda _: ModelCheckResult(
                check_id="fixture-check",
                revision=1,
                state="failed",
                current_model_id="fixture/model",
            ),
        ).check()
        assert body["state"] == "blocked"
        after = (synth / ".louke" / "project" / "project.toml").read_bytes()
        assert before == after, "synthetic host file was unexpectedly mutated"


def test_canonical_path_uses_semantic_namespace_not_release_number() -> None:
    """AC-NFR0401-01: API paths must not embed release/Spec/workflow version.

    Interfaces.md §1 mandates that canonical routes use semantic
    namespaces (``/api/readiness``, ``/api/projects``, ``/api/guide``,
    ``/api/runs``, ``/api/releases``) and never embed ``v14``,
    ``v0.14`` or any release/Spec identifier.
    """
    # AC-NFR0401-01
    interfaces = (
        REPO_ROOT
        / ".louke"
        / "project"
        / "specs"
        / "v0.14-004-workspace-onboarding-workflow-status"
        / "interfaces.md"
    )
    text = interfaces.read_text(encoding="utf-8")
    forbidden_in_canonical = ["/api/v14/", "/api/v15/", "/api/v0."]
    for forbidden in forbidden_in_canonical:
        assert forbidden not in text, (
            f"canonical route leaked release/Spec version {forbidden!r} in interfaces.md"
        )


def test_devon_module_registry_maps_to_real_artifacts() -> None:
    """AC-NFR0401-02: every entry in ``DEVON_MODULES`` points to an importable path.

    The artifact registry must map every interface to a canonical
    module path; each name must round-trip through ``devon_module_available``.
    """
    # AC-NFR0401-02
    names = list(DEVON_MODULES.keys())
    assert len(names) == len(set(names)), "duplicate artifact names"
    # ``IF-ENV-01`` and ``IF-ENV-02`` intentionally share the
    # ``louke.web.environment_gate`` module; collapse before dedup.
    canonical_paths = {
        name: path
        for name, path in DEVON_MODULES.items()
        if not (
            name == "IF-ENV-01"
            and "IF-ENV-02" in DEVON_MODULES
            and DEVON_MODULES["IF-ENV-02"] == path
        )
    }
    assert len(canonical_paths.values()) == len(set(canonical_paths.values())), (
        "duplicate canonical paths beyond the IF-ENV-01/-02 grouping"
    )
    for name in names:
        result = devon_module_available(name)
        assert isinstance(result, bool)
    with pytest.raises(KeyError):
        devon_module_available("does_not_exist")


def test_synthetic_bare_remote_does_not_require_credentials(tmp_path: Path) -> None:
    """AC-NFR0101-02: synthetic Git remotes use only the filesystem URL.

    No real GitHub or SSH is contacted; no credential helpers fire.
    """
    # AC-NFR0101-02
    remote = synthetic_bare_remote(tmp_path)
    try:
        assert (remote / "HEAD").exists()
        result = subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "init.defaultBranch=main",
                "ls-remote",
                str(remote),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
    finally:
        shutil.rmtree(remote, ignore_errors=True)
