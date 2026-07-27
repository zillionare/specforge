"""Shared helpers for v0.14-004 workspace-onboarding integration tests.

This module intentionally does **not** ship a stub factory for
modules-under-test. Stubs are only acceptable for **external
systems** (filesystem layout, ``subprocess`` invocations against
the real Git binary, etc.) — never for the modules the tests are
exercising. The shared helpers here are limited to:

* ``synthetic_host_project`` — a real, isolated host-project
  ``.louke/`` directory so a test can write/read persistence under
  controlled paths without leaking into Louke's own ``.louke/``.
* ``synthetic_bare_remote`` — a real, loopback bare Git remote for
  IF-ENV-02 binding tests without invoking system Git credentials.
* ``assert_contract_shape`` — a value-based attribute presence
  check used to document the *required* public surface of a real
  artifact (not a stub).
* ``DEVON_MODULES`` — the canonical IF/FR → module path mapping
  used by the AC-traceability tool and by the synthetic-host
  isolation test. It is metadata, not a stub factory.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Synthetic host project (real layout, no stub)
# ---------------------------------------------------------------------------


def _seed_host_louke(target: Path, *, marker: str) -> None:
    """Write a synthetic host-project ``.louke/project/project.toml``.

    ``marker`` is a per-run prefix used so concurrent CI jobs do not
    accidentally share the same workspace_id. The payload is JSON-only
    — Louke tooling must read it without leaking its own internal
    schema into the host project.
    """
    louke_dir = target / ".louke"
    project_dir = louke_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "test_framework": "pytest",
            "workspace_id_marker": marker,
            "is_synthetic_host_project": True,
        },
        "integration": {"run": "noop", "paths": ["tests"], "cwd": "."},
        "e2e": {"run": "noop", "paths": ["tests/e2e"], "cwd": "."},
    }
    (project_dir / "project.toml").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


@contextmanager
def synthetic_host_project(marker: str | None = None) -> Iterator[Path]:
    """Yield a temp directory containing a synthetic host ``.louke/``.

    Per Mode B §3.3 (and ``test-plan`` §3.2 Ground Truth isolation),
    every v0.14-004 test that exercises Louke tooling must run inside
    a host-project layout; this context manager builds one with a
    per-run ``workspace_id_marker`` so two tests cannot collide.

    Note: this context manager does *not* chdir into the synthetic
    project; it only writes ``.louke/project/project.toml`` so the
    host-project layout exists in the temp directory. Tests that
    need to work from the synthetic project as the active cwd
    should ``os.chdir(yielded_path)`` themselves inside the body.
    """
    if marker is None:
        marker = "v014004-" + os.urandom(4).hex()
    tmp = Path(tempfile.mkdtemp(prefix=f"louke-synth-{marker}-"))
    _seed_host_louke(tmp, marker=marker)
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def synthetic_bare_remote(tmp_path: Path) -> Path:
    """Create an empty bare Git remote at ``tmp_path/bare.git``.

    No real network is involved; the URL is the local path. Stands in
    for the ``git-empty-remote`` fixture in test-plan §2.4 without
    requiring system git author/credential configuration.
    """
    remote = tmp_path / "bare.git"
    if remote.exists():
        shutil.rmtree(remote, ignore_errors=True)
    remote.mkdir()
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    return remote


# ---------------------------------------------------------------------------
# Contract shape (real-artifact assertion, not a stub)
# ---------------------------------------------------------------------------


def assert_contract_shape(
    instance: Any,
    required: tuple[str, ...],
    *,
    context: str,
) -> None:
    """Assert ``instance`` exposes every ``required`` attribute.

    Used in real-artifact activation tests to document the canonical
    public surface. ``instance`` must be a real module/class — never
    a MagicMock — so the check fails if the attribute is missing or
    only present because ``MagicMock`` auto-supplies it.
    """
    missing = [name for name in required if not hasattr(instance, name)]
    assert not missing, (
        f"{context}: contract missing attributes {missing!r}; "
        f"present attributes: "
        f"{[n for n in dir(instance) if not n.startswith('_')][:20]}"
    )


# ---------------------------------------------------------------------------
# Devon module registry (metadata, not a stub factory)
# ---------------------------------------------------------------------------


DEVON_MODULES: dict[str, str] = {
    "IF-WEB-01": "louke.web.app",
    "IF-SETUP-01": "louke.web.login_readiness",
    "IF-SETUP-02": "louke.web.auth",
    "IF-SETUP-03": "louke.web.opencode_probe",
    "IF-PROJECT-01": "louke.web.projects_context",
    "IF-GUIDE-01": "louke.web.guide_session",
    "IF-ENV-01": "louke.web.environment_service",
    "IF-ENV-02": "louke.web.repository_readiness",
    "IF-DRAFT-01": "louke.web.draft_storage",
    "IF-PREVIEW-01": "louke.runtime.release_entry",
    "IF-CREATE-01": "louke.runtime.foundation_scribe",
    "IF-IDENTITY-01": "louke.runtime.project_identity",
    "IF-STATUS-01": "louke.runtime.projection",
    "IF-ATTEMPT-01": "louke.runtime.attempt_detail",
    "IF-RETURN-01": "louke.runtime.return_application",
    "IF-DOC-01": "louke.web.document_surface",
    "IF-COMPAT-01": "louke.web.compatibility_router",
    "IF-AUDIT-01": "louke.runtime.audit_observability",
    "IF-CSRF": "louke.web.csrf_middleware",
}


def devon_module_available(identifier: str) -> bool:
    """Return True iff the canonical module for ``identifier`` is importable.

    Used as a registry helper by the synthetic-host isolation test to
    confirm every interface maps to an importable path. This is *not*
    a stub factory: it never returns a MagicMock, it only returns a
    bool describing whether the real module can be imported.
    """
    import importlib.util

    module_path = DEVON_MODULES.get(identifier)
    if not module_path:
        raise KeyError(
            f"unknown identifier {identifier!r}; expected one of "
            f"{sorted(DEVON_MODULES.keys())}"
        )
    return importlib.util.find_spec(module_path) is not None


def devon_module_skip(identifier: str, *, fr: str) -> None:
    """No-op skip helper retained for backward compatibility.

    v0.14-004 ships all canonical Devon modules, so this helper no
    longer fires ``pytest.skip``. It is kept so the e2e journey
    suite (which uses it as a marker) imports cleanly while every
    artefact is real.

    Args:
        identifier: Interface or FR id (unused).
        fr: FR number (unused).
    """
    # No-op: every interface module is now importable. The helper
    # is preserved so existing ``from _mode_b import devon_module_skip``
    # lines do not break the e2e collection.
    return None
