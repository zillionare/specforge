"""Production route probe + Mount precedence smoke for /api/runtime/bindings.

S3 (#176): ``louke.web.app.create_app`` mounts ``/api/runtime`` before
``/api/runtime/bindings``, so Starlette's first-match routing hands the
``/api/runtime/bindings/...`` request to the ``runtime_app`` sub-app, which
has no internal route matching ``bindings/...`` and returns 404. The fix is
purely a Mount ordering change in :mod:`louke.web.app`; this file proves the
fix from the outside (via the public ``create_app`` entry point) and guards
against future regressions with a static-analysis smoke on the Mount order.

The route probe goes through the **top-level** ``louke.web.app.create_app``
(not a sub-app import), so it exercises the real production routing tree.
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient


#: The module-level v0.12 sub-apps that cache a shared ``WorkflowRunStore``.
#: Mirrors ``tests/e2e/test_v12_integration_e2e.py`` so this test stays
#: hermetic without importing the e2e fixture module.
_V12_SUBAPPS_ATTR: str = "v12_run_store"

#: Repo root, used to read ``louke/web/app.py`` source for the precedence smoke.
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_APP_MODULE_PATH: Path = _REPO_ROOT / "louke" / "web" / "app.py"

#: A bindings probe tuple: (method, path, json_body, query_params).
#: ``json_body`` is a raw JSON string (or None) so ``TestClient.request`` can
#: pass it straight through as ``content`` without an extra dumps round-trip.
_Probe = tuple[str, str, str | None, dict[str, str] | None]


def _write_project_toml(root: Any) -> None:
    """Write a minimal project.toml so ``create_app`` does not fail on meta reads.

    Copied verbatim from ``tests/e2e/test_v12_integration_e2e.py`` so this
    integration test does not depend on the e2e conftest.
    """
    project_dir = root / ".louke" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.toml").write_text(
        '[project]\nversion = "0.12"\n'
        'spec_id = "v0.12-001-programmatic-workflow-runtime"\n'
        'release_branch = "main"\n\n'
        '[meta]\ncreated = "2026-07-14"\ntag = "unreleased"\n'
        'current_stage = "M-DEV"\nsecurity_audit = "disabled"\n'
        'smoke_test_issue = ""\nsmoke_test_pr = ""\n'
        'pre_commit = "installed"\ntest_framework = "pytest"\n'
        "acknowledged_orphan_releases = []\n",
        encoding="utf-8",
    )


def _v12_subapps() -> tuple[Any, ...]:
    """Return the mounted runtime sub-apps that share the run store."""
    import louke.web.app as appmod

    return (
        appmod.runtime_app,
        appmod.gates_app,
        appmod.bindings_app,
    )


def _reset_subapp_state() -> None:
    """Clear cached state on the module-level v0.12 sub-apps.

    The sub-apps cache their ``WorkflowRunStore`` on ``app.state``; without
    clearing, state leaks across ``create_app`` calls (and thus across
    tests). Clears each sub-app's internal ``_state`` dict so the next
    request lazily rebuilds from scratch.
    """
    for sub_app in _v12_subapps():
        sub_app.state._state.clear()


def _inject_shared_store(client: TestClient) -> Any:
    """Inject a single shared ``WorkflowRunStore`` into all v0.12 sub-apps.

    Must be called inside the ``TestClient`` context manager (portal thread)
    because the ``sqlite3`` connection is thread-bound. Returns the shared
    store so the test can create a real run via HTTP before probing bindings.
    """
    from louke.web.api._runtime_store import build_run_store

    def _setup() -> Any:
        store = build_run_store()
        for sub_app in _v12_subapps():
            setattr(sub_app.state, _V12_SUBAPPS_ATTR, store)
        return store

    return client.portal.call(_setup)


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Build a fresh Starlette app + TestClient per test, with a tmp workspace.

    Uses the **top-level** :func:`louke.web.app.create_app` so the probe
    exercises the real production routing tree (not a sub-app import).
    """
    from louke.web.app import create_app

    _write_project_toml(tmp_path)
    monkeypatch.setenv("LOUKE_E2E_STATE", str(tmp_path / ".louke" / "server"))
    _reset_subapp_state()
    app = create_app(tmp_path)
    with TestClient(app) as c:
        registered = c.post(
            "/api/auth/register",
            json={"username": "fixture-human", "password": "secret"},
        )
        assert registered.status_code == 200
        _inject_shared_store(c)
        yield c


def _extract_mount_prefixes_from_ast(tree: ast.AST) -> list[str]:
    """Return the literal ``Mount("/api/...", ...)`` prefixes in declaration order.

    Uses an AST walk so the extraction cannot be fooled by string quoting or
    formatting. Only literal-string ``Mount`` calls under ``create_app`` are
    considered; this matches the production routing block.

    Args:
        tree: A parsed :class:`ast.Module` of ``louke/web/app.py``.

    Returns:
        The list of Mount prefix strings in the exact order they appear in
        the ``routes=[...]`` list of :func:`create_app`.
    """
    prefixes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Mount" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                prefixes.append(first.value)
    return prefixes


class TestBindingsRoutesReachableViaCreateApp:
    """S3 (#176): all four /api/runtime/bindings/* endpoints are reachable.

    The probe goes through the top-level ``create_app`` so a Mount ordering
    bug (specific path shadowed by a wider prefix) surfaces as a 404 here.
    Each endpoint must NOT return 404: business errors (400/422) are fine;
    a 404 means the route never reached the bindings sub-app (shadowed).
    """

    def test_bindings_routes_reachable_via_create_app(self, client: TestClient) -> None:
        """All four bindings endpoints answer with a non-routing status code.

        Steps:
            1. POST /api/runtime/bindings/runs to create a real run (so the
               subsequent GET/PUT/audit endpoints have a valid run_id).
            2. Probe the four bindings endpoints against that real run_id.
            3. Assert each response status is not 404.

        A 404 here means Mount ordering shadows the bindings sub-app behind
        the wider ``/api/runtime`` Mount.
        """
        create_resp = client.post(
            "/api/runtime/bindings/runs",
            json={"definition_id": "new_feature", "definition_version": "1"},
        )
        assert create_resp.status_code != 404, (
            "POST /api/runtime/bindings/runs returned 404 - the bindings "
            "sub-app is shadowed by the wider /api/runtime Mount"
        )
        assert create_resp.status_code == 201, (
            f"expected 201 from POST /api/runtime/bindings/runs, got "
            f"{create_resp.status_code}: {create_resp.text}"
        )
        run_id = create_resp.json()["run_id"]

        probes: list[_Probe] = [
            ("GET", "/api/runtime/bindings/devon", None, {"run_id": run_id}),
            (
                "PUT",
                "/api/runtime/bindings/devon",
                '{"model": "gpt-4o"}',
                {"run_id": run_id},
            ),
            ("GET", "/api/runtime/bindings/devon/audit", None, {"run_id": run_id}),
        ]
        failures: list[str] = []
        for method, path, body, params in probes:
            resp = client.request(method, path, content=body, params=params)
            if resp.status_code == 404:
                failures.append(f"{method} {path} -> 404 (route shadowed): {resp.text}")
            elif resp.status_code >= 500:
                failures.append(
                    f"{method} {path} -> {resp.status_code} (server error): {resp.text}"
                )
        assert not failures, "bindings route probe failures:\n  " + "\n  ".join(
            failures
        )


class TestMountOrderLongerPrefixFirst:
    """S3 (#176): longer Mount prefixes must be declared before shorter ones.

    Starlette matches Mounts in declaration order and consumes the whole
    remaining path. If ``/api/runtime`` precedes ``/api/runtime/bindings``,
    every ``/api/runtime/bindings/...`` request is handed to the runtime
    sub-app (which has no ``bindings`` internal route) and returns 404. This
    smoke statically asserts the invariant so a future revert cannot
    silently re-introduce the shadow.
    """

    def test_mount_order_longer_prefix_first(self) -> None:
        """For every pair of /api/... Mount prefixes, the longer one comes first.

        Reads ``louke/web/app.py`` source (not the live app) so this is a
        pure static-analysis guard: it fails on the literal source order
        even if a runtime test elsewhere happens to mask the regression.
        """
        source = _APP_MODULE_PATH.read_text(encoding="utf-8")
        # ``louke/web/app.py`` embeds inline JS in triple-quoted strings whose
        # regex escapes (e.g. ``\[``) are invalid Python escape sequences.
        # Parse as ``ast.PyCF_ONLY_AST`` under a filtered warning scope so the
        # DeprecationWarning emitted by the CPython tokenizer for those
        # unrelated string literals does not abort this test under
        # ``-W error::DeprecationWarning``.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            tree = ast.parse(source)
        prefixes = _extract_mount_prefixes_from_ast(tree)
        api_prefixes = [p for p in prefixes if p.startswith("/api/")]
        assert api_prefixes, "no /api/ Mount prefixes found in louke/web/app.py"

        violations: list[str] = []
        for i, p1 in enumerate(api_prefixes):
            for j, p2 in enumerate(api_prefixes):
                if i >= j:
                    continue
                # For each pair (i before j): p1 must not be a strict prefix
                # of p2. If p1 is a prefix of p2, p1 is the wider one and it
                # is shadowing p2 -> violation.
                if p2.startswith(p1 + "/") or (p1 != p2 and p2 == p1):
                    violations.append(
                        f"longer prefix {p2!r} (index {j}) is declared AFTER "
                        f"wider prefix {p1!r} (index {i}); the wider Mount "
                        f"will shadow the longer one"
                    )
        assert not violations, (
            "Mount precedence violations in louke/web/app.py "
            "(longer prefix must come BEFORE its wider parent):\n  "
            + "\n  ".join(violations)
        )
