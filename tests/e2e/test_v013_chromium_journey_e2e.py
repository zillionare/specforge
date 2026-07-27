"""Chromium closes the complete v0.13 workbench product journey."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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
                'repo = "github.com/zillionare/louke"',
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

    # The canonical Project journey now requires a real repository binding and
    # a remote main SHA.  Seed the runner-provided workspace with the same
    # local-bare-remote contract used by the v0.14 E2E fixtures; the product
    # still executes its real Git subprocess boundary through the PATH wrapper.
    bare_remote = root.parent / "browser-fixture-remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare_remote)],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "init", str(root)], capture_output=True, text=True, check=True
    )
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test Human",
        "GIT_AUTHOR_EMAIL": "human@test.local",
        "GIT_COMMITTER_NAME": "Test Human",
        "GIT_COMMITTER_EMAIL": "human@test.local",
    }
    for key, value in (
        ("user.name", "Test Human"),
        ("user.email", "human@test.local"),
    ):
        subprocess.run(
            ["git", "config", key, value],
            cwd=str(root),
            env=git_env,
            capture_output=True,
            text=True,
            check=True,
        )
    subprocess.run(["git", "add", "-A"], cwd=str(root), env=git_env, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialise browser fixture"],
        cwd=str(root),
        env=git_env,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"], cwd=str(root), env=git_env, check=True
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_remote)],
        cwd=str(root),
        env=git_env,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=str(root),
        env=git_env,
        capture_output=True,
        text=True,
        check=True,
    )
    canonical_origin = "https://github.com/zillionare/louke.git"
    subprocess.run(
        ["git", "config", f"url.{bare_remote.as_uri()}.insteadOf", canonical_origin],
        cwd=str(root),
        env=git_env,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", canonical_origin],
        cwd=str(root),
        env=git_env,
        check=True,
    )


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


def _create_project_from_empty_projects(page, base_url: str) -> tuple[str, dict]:
    """Complete the current user-visible empty-Projects journey.

    The historical v0.13 journey used the legacy Dev Docs sidebar as its first
    activity after Setup.  Current Louke keeps that sidebar project-owned, so
    the supported route is: empty Projects -> readiness -> Story/Preview/Create
    -> the canonical Project Story document -> Project Status.
    """
    register = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": "human", "password": "secret"},
    )
    assert register.ok, register.text()

    page.goto(f"{base_url}/workbench?activity=projects", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    new_project = page.get_by_role("button", name="New Project")
    assert new_project.is_visible(), (
        "AC-FR1317-01: empty Projects must expose the New Project action"
    )
    new_project.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('form[name="new_project_story"]')

    # The form is intentionally disabled until the real bounded GitHub/Git
    # readiness check reaches its terminal passed state.  Do not enable it from
    # browser-owned state or skip the gate.
    page.wait_for_function(
        """() => {
            const card = document.querySelector('[data-projects-state="new_project"]');
            const step = document.querySelector('[data-testid="env-step-canonical_main"]');
            return card?.dataset.envPassed === 'true' && step?.dataset.state === 'passed';
        }""",
        timeout=15_000,
    )
    for step_id in (
        "gh_executable",
        "gh_auth_scopes",
        "repository_binding",
        "canonical_main",
    ):
        step = page.locator(f'[data-testid="env-step-{step_id}"]')
        assert step.get_attribute("data-state") == "passed", (
            f"AC-FR1317-01: readiness step {step_id} must be terminal passed"
        )

    story = "Initial Story for v0.15"
    page.locator('textarea[name="story"]').fill(story)
    page.locator('input[name="release_version"]').fill("0.15.0")
    page.get_by_test_id("preview").click()
    page.wait_for_selector('[data-testid="project-preview"]:not([hidden])')
    preview_body = page.inner_text("body")
    assert story in preview_body
    assert "0.15.0" in preview_body
    assert page.get_by_test_id("create-project").is_visible()

    page.get_by_test_id("create-project").click()
    page.wait_for_url(f"{base_url}/workbench?activity=dev-docs*")
    story_view = page.get_by_test_id("dev-docs-story")
    story_view.wait_for()
    story_body = story_view.inner_text()
    assert story in story_body
    assert "Revision: 1" in story_body

    query = parse_qs(urlparse(page.url).query)
    project_id = query["project"][0]
    current_response = page.request.get(f"{base_url}/api/projects/{project_id}/current")
    assert current_response.ok, current_response.text()
    current = current_response.json()
    assert current["project"]["project_id"] == project_id
    assert current["project"]["spec_id"].startswith("v0.15-")
    assert current["run"]["run_id"]
    assert current["run"]["phase"] == "M-STORY"
    assert current["artifact"]["kind"] == "story"
    assert current["artifact"]["revision"] == 1
    assert current["artifact"]["digest"].startswith("sha256:")

    page.get_by_role("link", name="Back to Project Status").click()
    page.wait_for_url(f"{base_url}/workbench?activity=projects&project={project_id}")
    status = page.get_by_test_id("status-cockpit")
    status.wait_for()
    assert status.get_attribute("data-project-id") == project_id
    assert current["run"]["run_id"] in status.inner_text()
    assert "Active: M-STORY" in status.inner_text()
    return project_id, current


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
                _create_project_from_empty_projects(page, base_url)
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
