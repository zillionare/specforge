"""Chromium closes the complete v0.13 workbench product journey."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from tests.fixtures.v014_workflow_reflow.harness import (
    build_isolated_workspace,
    start_opencode_standin,
)


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).exists()
    except Exception:
        return False


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, OSError):
            time.sleep(0.2)
    raise TimeoutError(f"lk serve did not become healthy at {base_url}")


def _prepare_workspace(root: Path) -> None:
    spec_id = "v0.13-999-browser-fixture"
    project = root / ".louke" / "project"
    specs = project / "specs" / spec_id
    end_user = root / ".louke" / "end-user-docs"
    wiki = root / ".louke" / "wiki" / "pages"
    specs.mkdir(parents=True, exist_ok=True)
    end_user.mkdir(parents=True, exist_ok=True)
    wiki.mkdir(parents=True, exist_ok=True)
    (project / "project.toml").write_text(
        "\n".join(
            (
                "[project]",
                'version = "0.13.1"',
                f'spec_id = "{spec_id}"',
                'project = "browser fixture"',
                "",
                "[meta]",
                'current_stage = "M-E2E"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (specs / "story.md").write_text("# Story\n\nSee US-1301.\n", encoding="utf-8")
    (specs / "spec.md").write_text(
        '# Fixture Spec\n\n<a id="fr-1301"></a>\n## FR-1301 Chrome\n\nSee US-1301.\n',
        encoding="utf-8",
    )
    (specs / "acceptance.md").write_text(
        '<a id="fr-1301"></a>\n## FR-1301\n\nBrowser acceptance.\n',
        encoding="utf-8",
    )
    (specs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (end_user / "guide.md").write_text("# User Guide\n\nHello.\n", encoding="utf-8")
    (wiki / "README.md").write_text("# README\n", encoding="utf-8")
    _seed_runtime_run(root)


def _seed_runtime_run(root: Path) -> None:
    """Create a Runtime store run with a review-stage event for the Runs tab.

    The v0.13 workbench reads runs from the Runtime SQLite store (not the
    legacy ``runs.json``).  This seeds one run at the ``design`` step with
    an event whose details carry the values the browser test asserts on:
    ``abc123`` (digest), ``PASS`` (verdict), ``Prism`` (reviewer),
    ``Looks good`` (conclusion).
    """
    from louke.web.api._runtime_store import build_run_store
    from louke.runtime.store import WorkflowEvent

    db_path = str(root / ".louke" / "project" / "runtime.sqlite3")
    store = build_run_store(db_path, workspace_root=root)
    definition = store._catalog.get("new_feature", "1")
    run = store.create_run(definition)
    # Advance to the design step so the graph shows meaningful nodes.
    run = store.update_run(run.with_step("design", "waiting_for_human"), run.revision)
    # Attach a review-like event at the design step with the expected
    # artifact detail values.
    event = WorkflowEvent(
        event_id="evt-review-1",
        run_id=run.run_id,
        sequence=1,
        type="step.completed",
        at="2026-07-16T00:00:00Z",
        actor={"role": "Prism"},
        from_step="requirements_approval",
        to_step="design",
        revision=run.revision,
        details={
            "result": "PASS",
            "reviewer": "Prism",
            "conclusion": "Looks good",
        },
        step_id="design",
        attempt_id="att-1",
        correlation_id="",
        input_digest="sha256:input",
        output_digest="abc123",
    )
    store.append_event(event)


def _complete_setup(page, base_url: str) -> None:
    """Drive the public first-user and model-probe journey to Workbench."""
    page.goto(f"{base_url}/setup", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    name_input = page.locator('input[name="name"]')
    name_input.wait_for(state="visible")
    name_input.fill("owner")
    assert name_input.input_value() == "owner"
    credential_input = page.locator('input[name="credential"]')
    credential_input.wait_for(state="visible")
    credential_input.fill("secret")
    assert credential_input.input_value() == "secret"
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    body = page.inner_text("body").lower()
    assert "model" in body or "opencode" in body
    trigger = page.query_selector('button[name="retry"]') or page.query_selector(
        'button[name="start"]'
    )
    if trigger is not None:
        trigger.click()
        page.wait_for_load_state("networkidle")
    page.wait_for_url("**/workbench?activity=projects")


@pytest.mark.chromium_e2e
@pytest.mark.skipif(
    not _chromium_available(),
    reason="Chromium or Playwright is not installed; run: python -m playwright install chromium; issue #180",
)
@pytest.mark.skipif(
    not os.environ.get("LOUKE_E2E_SERVER_PYTHON")
    or not os.environ.get("LOUKE_E2E_CASE_CWD"),
    reason="v0.13 Chromium journey must run through the project-venv E2E runner",
)
def test_v013_chromium_main_journey(tmp_path: Path) -> None:
    """AC-FR1317-01/02/03/04@v0.13: complete real-browser journey."""
    from playwright.sync_api import sync_playwright

    product_python_raw = os.environ.get("LOUKE_E2E_SERVER_PYTHON", "")
    workspace_raw = os.environ.get("LOUKE_E2E_CASE_CWD", "")
    assert product_python_raw, "LOUKE_E2E_SERVER_PYTHON must select a product venv"
    assert workspace_raw, "LOUKE_E2E_CASE_CWD must select the isolated workspace"
    product_python = Path(product_python_raw)
    workspace = Path(workspace_raw).resolve()
    runner_python = Path(os.environ["LOUKE_PROJECT_RUNNER_PYTHON"])
    repo_venv = Path(__file__).parents[2] / ".venv"
    # Compare venv *prefixes* (not resolved executables): on Linux both venv
    # shims may resolve to the same base interpreter, so ``.resolve()``
    # produces identical paths.  The installed-wheel guarantee is that the
    # product venv directory differs from the runner venv and that ``louke``
    # resolves under the product environment -- not that the Python binaries
    # are distinct files.
    product_venv_root = product_python.parent.parent
    runner_venv_root = runner_python.parent.parent
    assert product_venv_root != runner_venv_root, (
        f"product venv {product_venv_root} must differ from runner venv {runner_venv_root}"
    )
    assert product_venv_root.resolve() != repo_venv.resolve(), (
        f"product venv must not be the repo .venv: {product_venv_root}"
    )
    _prepare_workspace(workspace)

    # Reuse the project-local OpenCode CLI/HTTP stand-ins rather than bypassing
    # the Setup probe. The product process still executes its real subprocess
    # boundary and records the bounded ``opencode run --model`` invocation.
    boundary = build_isolated_workspace(tmp_path / "opencode-boundary")
    opencode = start_opencode_standin(tmp_path)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        [str(boundary.gh_bin.parent), environment.get("PATH", "")]
    )
    environment["LOUKE_GH_OWNER"] = "zillionare"
    environment["LOUKE_OPENCODE_BACKEND"] = "real"
    environment["LOUKE_OPENCODE_BASE_URL"] = opencode.base_url
    environment["LOUKE_OPENCODE_USE_SERVER_DEFAULT"] = "1"
    environment["LOUKE_OPENCODE_CLI_LEDGER_PATH"] = str(boundary.opencode_ledger)
    environment["NO_PROXY"] = "127.0.0.1,localhost"
    environment["no_proxy"] = "127.0.0.1,localhost"
    server = subprocess.Popen(
        [
            str(product_python),
            "-m",
            "louke",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--project-root",
            str(workspace),
            "--opencode-backend",
            "real",
        ],
        cwd=workspace,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    browser = None
    try:
        _wait_for_health(base_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                errors: list[str] = []
                failed_requests: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: (
                        failed_requests.append(f"{response.status} {response.url}")
                        if response.status >= 500
                        else None
                    ),
                )
                _complete_setup(page, base_url)
                ledger = [
                    json.loads(line)
                    for line in boundary.opencode_ledger.read_text(
                        encoding="utf-8"
                    ).splitlines()
                ]
                assert any(
                    entry["kind"] == "run" and "--model" in entry["argv"]
                    for entry in ledger
                ), "Setup must execute the real model-probe command boundary"
                page.goto(f"{base_url}/workbench", wait_until="domcontentloaded")
                expect = page.get_by_test_id
                assert expect("workbench-toolbar").is_visible()
                assert expect("workbench-sidebar").is_visible()
                assert expect("workbench-main").is_visible()

                expect("toolbar-dev-docs").click()
                assert expect("devdocs-tree").is_visible()
                page.locator('[data-testid^="devdocs-spec-"]').first.click()
                expect("devdocs-file-spec").first.click()
                page.wait_for_url("**/workbench?spec=*&doc=spec")
                page.wait_for_load_state("domcontentloaded")
                expect("devdocs-pane-container").locator(".doc-pane").first.wait_for()
                assert expect("devdocs-cross-ref-US-1301").is_visible()
                expect("devdocs-cross-ref-US-1301").click()
                assert "#us-1301" in page.url

                expect("toolbar-end-user-docs").click()
                assert expect("enduserdocs-tree").is_visible()
                expect("enduserdocs-file-guide").click()
                assert expect("enduserdocs-editor").is_visible()
                # loadDoc is async (fetches /api/files); wait for content.
                page.wait_for_function(
                    """() => {
                        const el = document.querySelector('[data-testid="enduserdocs-editor"]');
                        return el && el.value && el.value.includes('User Guide');
                    }""",
                    timeout=5000,
                )
                assert "User Guide" in expect("enduserdocs-editor").input_value()

                expect("toolbar-wiki").click()
                assert expect("wiki-tree").is_visible()
                expect("wiki-page-README").click()
                assert page.get_by_text("README", exact=True).last.is_visible()

                expect("toolbar-runs").click()
                assert expect("runs-sidebar").is_visible()
                # The Runs sidebar is populated from the Runtime store via
                # /api/ui/runs.  Fetch the actual run_id rather than hardcoding.
                runs_response = page.request.get(f"{base_url}/api/ui/runs")
                assert runs_response.ok
                runs_json = runs_response.json()
                assert runs_json["current"], "at least one current run must exist"
                run_id = runs_json["current"][0]["run_id"]
                run_button = page.locator(f'[data-testid="runs-project-{run_id}"]')
                run_button.wait_for()
                run_button.click()
                # Click the design stage node (from the host compatibility
                # definition graph) to load the artifact detail.
                design_node = page.locator('[data-testid="runs-node-design"]')
                design_node.wait_for()
                design_node.click()
                detail = expect("stage-artifact-detail")
                detail.wait_for()
                assert detail.is_visible()
                for value in ("abc123", "PASS", "Prism", "Looks good"):
                    assert value in detail.inner_text()

                open_tabs = page.locator('[data-testid="workbench-tab"]:not([hidden])')
                keys = open_tabs.evaluate_all(
                    "nodes => nodes.map(node => node.dataset.tabKey)"
                )
                assert {"dev-docs", "end-user-docs", "wiki", "runs"}.issubset(set(keys))
                assert not errors
                assert not failed_requests
            finally:
                # Close browser inside the sync_playwright context so the
                # event loop is still active; closing after the context
                # exits raises "Event loop is closed".
                browser.close()
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        opencode.stop()
        boundary.cleanup()
        if boundary.bare_remote.exists():
            shutil.rmtree(boundary.bare_remote, ignore_errors=True)
