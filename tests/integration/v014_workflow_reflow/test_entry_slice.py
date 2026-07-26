"""Integration coverage for the v0.14-001 public-entry slice.

AC-FR0100-01/02/03, AC-FR0300-01/02, AC-FR0400-01/02/03/04/05,
AC-FR0500-01/03, AC-FR0600-02, AC-FR0700-01/02/03, AC-FR0800-01.

Every test drives the real ``lk serve`` process through public HTTP JSON
endpoints against real SQLite, real Git CLI and a bare remote.  The only
stand-ins are the external OpenCode HTTP server and GitHub ``gh`` script
per test-plan §6.2.  No internal Python calls, direct SQLite writes, or
service construction are used.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.fixtures.v014_workflow_reflow.harness import CANONICAL_HUMAN_STORY


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, trust_env=False, follow_redirects=True)


def _register(client: httpx.Client) -> httpx.Response:
    return client.post(
        "/api/auth/register", json={"username": "human", "password": "secret"}
    )


def _session(response: httpx.Response) -> str:
    return response.cookies.get("louke_session", "").strip('"')


def _cookies(session: str) -> dict[str, str]:
    return {"louke_session": session}


def _csrf(client: httpx.Client, session: str) -> str:
    resp = client.get("/projects/new", cookies=_cookies(session))
    m = re.search(r'const\s+csrf\s*=\s*"([a-f0-9]+)"', resp.text)
    if m:
        return m.group(1)
    raise RuntimeError("Could not derive CSRF token from /projects/new")


def _mut_headers(base_url: str, csrf: str) -> dict[str, str]:
    return {"Origin": base_url, "X-Louke-CSRF": csrf}


def _preview(client: httpx.Client, session: str, headers: dict[str, str]) -> dict:
    resp = client.post(
        "/api/v14/releases/preview",
        json={"story": CANONICAL_HUMAN_STORY, "release_version": "0.14.0"},
        cookies=_cookies(session),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _confirm(
    client: httpx.Client, session: str, headers: dict[str, str], preview: dict
) -> dict:
    resp = client.post(
        "/api/v14/releases/confirm",
        json={
            "preview_id": preview["preview_id"],
            "expected_preview_revision": preview["preview_revision"],
            "request_digest": preview["request_digest"],
            "idempotency_key": "confirm-1",
        },
        cookies=_cookies(session),
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


def _poll_status(
    client: httpx.Client, session: str, request_id: str, timeout: float = 30
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(
            f"/api/v14/releases/requests/{request_id}",
            cookies=_cookies(session),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("ready", "conflict", "blocked"):
            return body
        time.sleep(0.5)
    raise TimeoutError(f"release request {request_id} did not settle")


def _current(client: httpx.Client, session: str, project_id: str) -> dict:
    resp = client.get(
        f"/api/v14/projects/{project_id}/current",
        cookies=_cookies(session),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _reconcile_task(
    client: httpx.Client,
    session: str,
    headers: dict[str, str],
    run_id: str,
    task_id: str,
) -> dict:
    resp = client.post(
        f"/api/v14/runs/{run_id}/tasks/{task_id}/reconcile",
        cookies=_cookies(session),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _decide(
    client: httpx.Client,
    session: str,
    headers: dict[str, str],
    run_id: str,
    project_id: str,
    run_revision: int,
    artifact_revision: int,
    candidate: str,
    key: str = "go-1",
) -> dict:
    resp = client.post(
        f"/api/v14/runs/{run_id}/actions",
        json={
            "action": "story_decision",
            "expected_run_revision": run_revision,
            "expected_artifact_revision": artifact_revision,
            "idempotency_key": key,
            "payload": {
                "candidate": candidate,
                "reason": "Human decision through public HTTP",
                "project_id": project_id,
            },
        },
        cookies=_cookies(session),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Golden path: Foundation -> Story -> Scribe recommendation -> Human Go
# ---------------------------------------------------------------------------


class TestEntrySliceGoldenPath:
    """AC-FR0100..0800: authenticated form-first release -> M-STORY -> Go."""

    def test_release_foundation_scribe_recommendation_human_go(self, live_server):
        """AC-FR0100-01/02, AC-FR0300-01/02, AC-FR0400-01/02/03,
        AC-FR0500-01/03, AC-FR0600-02, AC-FR0700-01/02/03, AC-FR0800-01.

        Drives the complete entry slice through public HTTP:
        preview -> confirm -> Foundation -> Story -> Scribe task ->
        reconcile -> recommendation -> waiting_for_human -> Human Go.
        """
        base_url, workspace, opencode = live_server
        client = _client(base_url)

        # AC-FR0100-01: register + authenticate
        reg = _register(client)
        assert reg.status_code == 200, reg.text
        session = _session(reg)
        csrf = _csrf(client, session)
        headers = _mut_headers(base_url, csrf)

        # AC-FR0300-01: preview produces no side effects
        preview = _preview(client, session, headers)
        assert preview["side_effects"] == []
        assert preview["release"]["external"] == "0.14.0"

        # AC-FR0300-02/AC-FR0400-02: confirm + Foundation
        confirm_body = _confirm(client, session, headers, preview)
        status = _poll_status(client, session, confirm_body["request_id"])
        assert status["status"] == "ready"
        project_id = status["project_id"]
        run_id = status["run_id"]

        # AC-FR0400-02/03: Foundation evidence
        foundation = client.get(
            f"/api/v14/releases/requests/{confirm_body['request_id']}/foundation",
            cookies=_cookies(session),
        ).json()
        assert foundation["status"] == "ready"
        release_branch = foundation["foundation"]["resources"]["release_branch"]
        assert release_branch["full_ref"] == "refs/heads/releases/0.14.0"
        assert release_branch["checked_out"] is True
        assert release_branch["head_symbolic_ref"] == "releases/0.14.0"
        worktree_path = foundation["foundation"]["resources"]["worktree"]["path"]
        # Independent Git ground truth.
        sym = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert sym == "releases/0.14.0"

        # AC-FR0500-01/03: Story revision + independent digest
        current = _current(client, session, project_id)
        assert current["run"]["phase"] == "M-STORY"
        artifact = current["artifact"]
        assert artifact, "Story artifact must exist (AC-FR0500-01)"
        assert artifact["kind"] == "story"
        assert artifact["revision"] == 1
        story_path = (
            Path(worktree_path)
            / ".louke"
            / "project"
            / "specs"
            / "v0.14-001-workflow-reflow-spec"
            / "story.md"
        )
        expected = f"sha256:{hashlib.sha256(story_path.read_bytes()).hexdigest()}"
        assert artifact["digest"] == expected

        # AC-FR0700-01: Scribe task manifest
        task = current["task"]
        assert task, "Scribe task must exist (AC-FR0700-01)"
        assert task["task_id"].startswith("task_")
        task_detail = client.get(
            f"/api/v14/runs/{run_id}/tasks/{task['task_id']}",
            cookies=_cookies(session),
        ).json()
        assert task_detail["phase"] == "M-STORY"
        assert task_detail["role"] == "Scribe"
        assert task_detail["write_scope"] == ["story.md"]

        # AC-FR0700-02: before reconcile -- no recommendation, zero M-SPEC
        gate = current["story_gate"]
        assert gate["recommendation"] is None
        assert gate["m_spec_task_count"] == 0
        assert gate["human_wait"] is False

        # AC-FR0700-02: reconcile through public HTTP triggers provider result
        # ingestion -> submit_result -> recommendation persisted.
        _reconcile_task(client, session, headers, run_id, task["task_id"])

        # Verify the OpenCode stand-in recorded the dispatch.
        ledger = opencode.read_ledger()
        assert any(e.get("kind") == "session_create" for e in ledger)
        assert any(e.get("kind") == "send_message" for e in ledger)

        # AC-FR0700-02: after reconcile -- recommendation present, waiting_for_human
        current = _current(client, session, project_id)
        gate = current["story_gate"]
        assert gate["recommendation"] == "Go"
        assert gate["human_wait"] is True
        assert gate["pending_action"] == "story_decision"
        assert gate["m_spec_task_count"] == 0

        # AC-FR0800-01: authenticated Human Go decision
        run_revision = current["run"]["revision"]
        artifact_revision = artifact["revision"]
        decision = _decide(
            client,
            session,
            headers,
            run_id,
            project_id,
            run_revision,
            artifact_revision,
            "Go",
        )
        assert decision["value"] == "Go"
        assert decision["actor"] == "human:human"
        assert decision["backlog_entry_count"] == 0
        # Go advances revision but stays at M-STORY.
        assert decision["run"]["revision"] > run_revision
        assert decision["run"]["phase"] == "M-STORY"
        assert decision["run"]["status"] == "running"

        # AC-FR0700-03: idempotent replay returns same decision.
        replay = _decide(
            client,
            session,
            headers,
            run_id,
            project_id,
            run_revision,
            artifact_revision,
            "Go",
        )
        assert replay["run"]["revision"] == decision["run"]["revision"]


# ---------------------------------------------------------------------------
# Fail-closed: malformed / wrong-role / stale-artifact provider results
# ---------------------------------------------------------------------------


class TestProviderResultFailClosed:
    """AC-FR0700-03, AC-FR1900-03: invalid provider output is rejected."""

    @pytest.mark.parametrize("mode", ["malformed", "wrong_role", "stale_artifact"])
    def test_invalid_provider_result_leaves_gate_empty(self, live_server_factory, mode):
        """AC-FR0700-03: malformed/wrong-role/stale provider results are
        rejected by ``submit_result`` without advancing the gate.

        AC-FR1900-03: wrong role/manifest/digest/schema are rejected and
        state/bytes are unchanged.
        """
        base_url, workspace, opencode = live_server_factory(mode)
        client = _client(base_url)

        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)
        headers = _mut_headers(base_url, csrf)

        preview = _preview(client, session, headers)
        confirm_body = _confirm(client, session, headers, preview)
        status = _poll_status(client, session, confirm_body["request_id"])
        assert status["status"] == "ready"
        project_id = status["project_id"]
        run_id = status["run_id"]

        current = _current(client, session, project_id)
        task = current["task"]
        assert task

        # Reconcile -- the stand-in emits an invalid result; submit_result
        # rejects it silently and the gate stays empty.
        _reconcile_task(client, session, headers, run_id, task["task_id"])

        current = _current(client, session, project_id)
        gate = current["story_gate"]
        assert gate["recommendation"] is None
        assert gate["human_wait"] is False
        assert gate["m_spec_task_count"] == 0
        # Run phase unchanged.
        assert current["run"]["phase"] == "M-STORY"


# ---------------------------------------------------------------------------
# Fail-closed: stale decision, foreign Origin, anonymous, invalid candidate
# ---------------------------------------------------------------------------


class TestEntrySliceFailClosed:
    """AC-FR0300-01, AC-FR0600-03, AC-FR0700-03: invalid inputs leave state unchanged."""

    def test_foreign_origin_rejected_before_preview(self, live_server):
        """AC-FR0600-03: foreign Origin cannot create a release request."""
        base_url, _, _ = live_server
        client = _client(base_url)
        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)

        resp = client.post(
            "/api/v14/releases/preview",
            json={"story": CANONICAL_HUMAN_STORY, "release_version": "0.14.0"},
            cookies=_cookies(session),
            headers={"Origin": "https://foreign.example", "X-Louke-CSRF": csrf},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "ORIGIN_FORBIDDEN"

    def test_unauthenticated_preview_rejected(self, live_server):
        """AC-FR0600-01: anonymous requests are rejected before Driver."""
        base_url, _, _ = live_server
        client = _client(base_url)
        resp = client.post(
            "/api/v14/releases/preview",
            json={"story": CANONICAL_HUMAN_STORY, "release_version": "0.14.0"},
        )
        assert resp.status_code == 401

    def test_preview_invalid_release_version_fails_closed(self, live_server):
        """AC-FR0300-01: invalid release version returns 400."""
        base_url, _, _ = live_server
        client = _client(base_url)
        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)

        resp = client.post(
            "/api/v14/releases/preview",
            json={"story": CANONICAL_HUMAN_STORY, "release_version": "../escape"},
            cookies=_cookies(session),
            headers=_mut_headers(base_url, csrf),
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "RELEASE_VERSION_INVALID"

    def test_stale_decision_rejected_without_advancement(self, live_server):
        """AC-FR0700-03: stale run revision is rejected; state unchanged."""
        base_url, _, _ = live_server
        client = _client(base_url)
        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)
        headers = _mut_headers(base_url, csrf)

        preview = _preview(client, session, headers)
        confirm_body = _confirm(client, session, headers, preview)
        status = _poll_status(client, session, confirm_body["request_id"])
        project_id = status["project_id"]
        run_id = status["run_id"]
        current = _current(client, session, project_id)

        # Reconcile to get a recommendation (this advances the run revision).
        task = current["task"]
        _reconcile_task(client, session, headers, run_id, task["task_id"])

        # Capture the post-reconcile revision.
        current = _current(client, session, project_id)
        run_revision = current["run"]["revision"]
        artifact_revision = current["artifact"]["revision"]

        # Stale revision.
        stale = client.post(
            f"/api/v14/runs/{run_id}/actions",
            json={
                "action": "story_decision",
                "expected_run_revision": run_revision + 999,
                "expected_artifact_revision": artifact_revision,
                "idempotency_key": "stale-1",
                "payload": {
                    "candidate": "Go",
                    "reason": "stale",
                    "project_id": project_id,
                },
            },
            cookies=_cookies(session),
            headers=headers,
        )
        assert stale.status_code == 409
        assert stale.json()["error_code"] == "WORKFLOW_STATE_CONFLICT"
        # State unchanged.
        after = _current(client, session, project_id)
        assert after["run"]["revision"] == run_revision

    def test_invalid_candidate_rejected_without_advancement(self, live_server):
        """AC-FR0700-03: candidate outside {Go,Park,No-Go} is rejected."""
        base_url, _, _ = live_server
        client = _client(base_url)
        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)
        headers = _mut_headers(base_url, csrf)

        preview = _preview(client, session, headers)
        confirm_body = _confirm(client, session, headers, preview)
        status = _poll_status(client, session, confirm_body["request_id"])
        project_id = status["project_id"]
        run_id = status["run_id"]
        current = _current(client, session, project_id)
        task = current["task"]
        _reconcile_task(client, session, headers, run_id, task["task_id"])

        # Re-fetch after reconcile (revision may have advanced).
        current = _current(client, session, project_id)

        invalid = client.post(
            f"/api/v14/runs/{run_id}/actions",
            json={
                "action": "story_decision",
                "expected_run_revision": current["run"]["revision"],
                "expected_artifact_revision": current["artifact"]["revision"],
                "idempotency_key": "invalid-1",
                "payload": {
                    "candidate": "Maybe",
                    "reason": "invalid",
                    "project_id": project_id,
                },
            },
            cookies=_cookies(session),
            headers=headers,
        )
        assert invalid.status_code == 400
        assert invalid.json()["error_code"] == "VALIDATION_FAILED"

    def test_park_decision_creates_backlog(self, live_server):
        """AC-FR0800-01: Park persists one Backlog identity and terminal state."""
        base_url, _, _ = live_server
        client = _client(base_url)
        reg = _register(client)
        session = _session(reg)
        csrf = _csrf(client, session)
        headers = _mut_headers(base_url, csrf)

        preview = _preview(client, session, headers)
        confirm_body = _confirm(client, session, headers, preview)
        status = _poll_status(client, session, confirm_body["request_id"])
        project_id = status["project_id"]
        run_id = status["run_id"]
        current = _current(client, session, project_id)
        task = current["task"]
        _reconcile_task(client, session, headers, run_id, task["task_id"])

        # Re-fetch after reconcile (revision may have advanced).
        current = _current(client, session, project_id)

        park = _decide(
            client,
            session,
            headers,
            run_id,
            project_id,
            current["run"]["revision"],
            current["artifact"]["revision"],
            "Park",
            key="park-1",
        )
        assert park["value"] == "Park"
        assert park["backlog_entry_count"] == 1
        assert park["run"]["status"] == "parked"


# ---------------------------------------------------------------------------
# Fixture portability: repository-local Git identity without global config
# ---------------------------------------------------------------------------


class TestFixtureGitIdentity:
    """AC-FR0500-01: Foundation Story commit succeeds without global Git config.

    Proves the isolated workspace's repository-local ``user.name``/``user.email``
    config is sufficient for the Foundation adapter's controlled-worktree commit
    even when HOME/global/system Git identity is absent (CI portability).
    """

    def test_workspace_has_local_git_identity(self, tmp_path):
        """The fixture configures repository-local Git identity."""

        from tests.fixtures.v014_workflow_reflow.harness import (
            build_isolated_workspace,
        )

        ws = build_isolated_workspace(tmp_path)
        name = ws.git("config", "user.name").stdout.strip()
        email = ws.git("config", "user.email").stdout.strip()
        assert name == "Test Human"
        assert email == "human@test.local"
        ws.cleanup()

    def test_foundation_story_commit_under_cleared_identity(self, tmp_path):
        """Full public flow succeeds with HOME/global Git identity cleared.

        Simulates CI's isolated environment by clearing HOME and all
        GIT_AUTHOR/GIT_COMMITTER env vars, then proving the repository-local
        config is sufficient.
        """
        import os
        import socket
        import subprocess
        import sys

        from tests.fixtures.v014_workflow_reflow.harness import (
            build_isolated_workspace,
            server_command,
            start_opencode_standin,
            wait_for_health,
        )

        ws = build_isolated_workspace(tmp_path)
        oc = start_opencode_standin(tmp_path)

        # Clear all Git identity env vars and set HOME to a temp dir with no
        # global Git config -- simulates the CI runner's isolated environment.
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        clean_env["HOME"] = str(tmp_path / "empty-home")
        Path(clean_env["HOME"]).mkdir(exist_ok=True)
        clean_env["PATH"] = str(ws.gh_bin.parent) + ":/usr/bin:/bin"
        clean_env["LOUKE_GH_OWNER"] = "zillionare"
        clean_env["LOUKE_OPENCODE_BASE_URL"] = oc.base_url
        clean_env["LOUKE_OPENCODE_BACKEND"] = "real"
        clean_env["LOUKE_OPENCODE_USE_SERVER_DEFAULT"] = "1"
        clean_env["NO_PROXY"] = "127.0.0.1,localhost"
        clean_env["no_proxy"] = "127.0.0.1,localhost"

        port = 0
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        base_url = f"http://127.0.0.1:{port}"
        cmd = server_command(
            os.environ.get("LOUKE_E2E_SERVER_PYTHON", sys.executable),
            str(ws.root),
            port=port,
        )
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=clean_env,
        )
        try:
            wait_for_health(base_url, timeout=30)
            client = _client(base_url)
            reg = _register(client)
            session = _session(reg)
            csrf = _csrf(client, session)
            headers = _mut_headers(base_url, csrf)

            preview = _preview(client, session, headers)
            confirm_body = _confirm(client, session, headers, preview)
            status = _poll_status(client, session, confirm_body["request_id"])
            # Foundation + Story commit must succeed despite no global Git identity.
            assert status["status"] == "ready", status

            current = _current(client, session, status["project_id"])
            assert current["run"]["phase"] == "M-STORY"
            assert current["artifact"], "Story artifact must exist"
            assert current["artifact"]["revision"] == 1
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
            oc.stop()
            ws.cleanup()
