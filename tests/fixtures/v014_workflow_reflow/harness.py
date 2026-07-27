"""L2 protocol stand-ins and isolated-workspace builder for v0.14-001 entry slice.

AC-FR0100-01/02/03, AC-FR0300-01/02, AC-FR0400-01/02/03/04/05,
AC-FR0500-01/03, AC-FR0600-02, AC-FR0700-01/02/03, AC-FR0800-01.

The stand-ins implement the *public process/protocol boundaries* of OpenCode
and GitHub and record every operation in a ledger so tests can independently
prove dispatch happened and identities match -- no fake app-internal success.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
LOUKE_REPO_IDENTITY = "github.com/zillionare/louke"
SPEC_ID = "v0.14-001-workflow-reflow-spec"
RELEASE_VERSION = "0.14.0"
RELEASE_BRANCH = f"releases/{RELEASE_VERSION}"

CANONICAL_HUMAN_STORY = "Ship the v0.14 reflow entry slice for authenticated Go."

_CONTRACT_FILES: tuple[str, ...] = (
    ".louke/project/specs/v0.14-001-workflow-reflow-spec/spec.md",
    ".louke/project/specs/v0.14-001-workflow-reflow-spec/acceptance.md",
    ".louke/project/specs/v0.14-002-workflow-reflow-design/spec.md",
    ".louke/project/specs/v0.14-002-workflow-reflow-design/acceptance.md",
    ".louke/project/specs/v0.14-003-workflow-reflow-impl/spec.md",
    ".louke/project/specs/v0.14-003-workflow-reflow-impl/acceptance.md",
)

_LOUKE_MARKER = "louke/__init__.py"
_PROJECT_TOML = ".louke/project/project.toml"
_CONTRACT_BUNDLE = ".louke/project/release-contract-bundle.json"


# ---------------------------------------------------------------------------
# Upstream blocker: Scribe recommendation ingestion
# ---------------------------------------------------------------------------

#: Production (commit 77cbb17) now ingests controlled OpenCode Scribe results
#: during ``reconcile`` via ``adapter.reconcile_session`` -> ``submit_result``.
#: The stand-in emits the exact ``scribe.story.v1`` result schema as an
#: assistant JSON message; ``RealOpenCodeAdapter.reconcile_session`` parses it
#: and ``ScribeEntryService._ingest_provider_results`` feeds it to
#: ``submit_result`` through the public task transport path.


# ---------------------------------------------------------------------------
# OpenCode HTTP stand-in subprocess
# ---------------------------------------------------------------------------

_OPENCODE_STANDIN_SCRIPT = r'''#!/usr/bin/env python3
"""Deterministic OpenCode HTTP stand-in for v0.14-001 entry-slice tests.

Implements the public OpenCode protocol endpoints that
``RealOpenCodeAdapter`` calls:
  POST   /api/session                 - create session
  GET    /api/session                 - list sessions
  DELETE /api/session/{id}            - stop session
  POST   /api/session/{id}/prompt     - send message
  GET    /api/session/{id}/message    - list messages

When the Scribe prompt is received, the stand-in parses the embedded task
manifest, computes the manifest digest, and emits an assistant message
containing a JSON object matching the ``scribe.story.v1`` contract.  The
production ``reconcile_session`` -> ``_ingest_provider_results`` ->
``submit_result`` path validates and persists the recommendation through
the public task transport boundary.

The ``--mode`` flag controls result emission:
  default  - valid Go recommendation
  malformed - assistant content is not valid JSON
  wrong_role - result with role "Sage" instead of "Scribe"
  stale_artifact - result with a wrong artifact_revision
  no_result - assistant content is "ack" (no JSON)

Records every operation in ``--ledger`` as JSON lines.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


_ledger_path = ""
_mode = "default"
_sessions: dict[str, dict] = {}
_messages: dict[str, list[dict]] = {}
_next_id = 0


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id(prefix: str) -> str:
    global _next_id
    _next_id += 1
    return f"{prefix}_{_next_id:08d}"


def _record(entry: dict) -> None:
    entry["at"] = _now()
    with open(_ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _parse_manifest(prompt_text: str) -> dict | None:
    """Extract the task manifest JSON from a Scribe prompt."""
    marker = "Task manifest:\n"
    idx = prompt_text.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    end_marker = "\n\nCurrent story.md:"
    end_idx = prompt_text.find(end_marker, start)
    if end_idx < 0:
        end_idx = len(prompt_text)
    raw = prompt_text[start:end_idx].strip()
    try:
        manifest = json.loads(raw)
        if isinstance(manifest, dict):
            return manifest
    except (json.JSONDecodeError, ValueError):
        return None
    return None


def _compute_manifest_digest(manifest: dict) -> str:
    """Compute the manifest digest using the same algorithm as production."""
    serialized = json.dumps(manifest, sort_keys=True)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_scribe_result(manifest: dict, session_id: str, mode: str) -> str:
    """Build the scribe.story.v1 result JSON or a controlled malformation."""
    artifact = manifest.get("artifact", {})
    task_id = manifest.get("task_id", "")
    attempt_id = manifest.get("attempt_id", "")
    manifest_digest = _compute_manifest_digest(manifest)
    artifact_revision = artifact.get("revision", 0)
    artifact_digest = artifact.get("digest", "")

    if mode == "malformed":
        return "not valid json {{{"
    if mode == "no_result":
        return "ack"
    if mode == "wrong_role":
        return json.dumps({
            "role": "Sage",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "manifest_digest": manifest_digest,
            "artifact_revision": artifact_revision,
            "artifact_digest": artifact_digest,
            "write_scope": ["story.md"],
            "recommendation": "Go",
            "reason": "wrong role test",
        })
    if mode == "stale_artifact":
        return json.dumps({
            "role": "Scribe",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "manifest_digest": manifest_digest,
            "artifact_revision": artifact_revision + 999,
            "artifact_digest": artifact_digest,
            "write_scope": ["story.md"],
            "recommendation": "Go",
            "reason": "stale artifact test",
        })
    # default: valid Go recommendation
    return json.dumps({
        "role": "Scribe",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "session_id": session_id,
        "manifest_digest": manifest_digest,
        "artifact_revision": artifact_revision,
        "artifact_digest": artifact_digest,
        "write_scope": ["story.md"],
        "recommendation": "Go",
        "reason": "The bounded Story is ready for Human review.",
    })


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_POST(self):
        path = urlparse(self.path).path
        correlation = self.headers.get("x-correlation-id", "")
        if path == "/api/session":
            sid = _new_id("sess")
            _sessions[sid] = {"id": sid, "status": "running", "created": _now()}
            _messages.setdefault(sid, [])
            _record({"kind": "session_create", "session_id": sid,
                      "correlation_id": correlation})
            self._json(200, {"data": {"id": sid, "time": {"created": time.time()}}})
            return
        parts = path.strip("/").split("/")
        if len(parts) >= 4 and parts[0] == "api" and parts[1] == "session" and parts[3] == "prompt":
            sid = parts[2]
            if sid not in _sessions:
                self._json(404, {"error": "session not found"})
                return
            body = self._body()
            text = (body.get("prompt") or {}).get("text", "")
            msg_id = _new_id("msg")
            user_msg = {"id": msg_id, "sessionID": sid, "role": "user",
                        "type": "message", "content": [{"type": "text", "text": text}]}
            _messages[sid].append(user_msg)
            # Parse the Scribe prompt and emit a controlled assistant result.
            manifest = _parse_manifest(text)
            assistant_content = "ack"
            result_emitted = False
            if manifest is not None:
                assistant_content = _build_scribe_result(manifest, sid, _mode)
                result_emitted = True
            assistant_id = _new_id("msg")
            assistant_msg = {"id": assistant_id, "sessionID": sid, "role": "assistant",
                             "type": "message",
                             "content": [{"type": "text", "text": assistant_content}]}
            _messages[sid].append(assistant_msg)
            _record({"kind": "send_message", "session_id": sid,
                      "correlation_id": correlation,
                      "prompt_digest": hashlib.sha256(text.encode()).hexdigest(),
                      "result_emitted": result_emitted, "mode": _mode})
            self._json(200, {"data": {"id": msg_id}})
            return
        self._json(404, {"error": f"unknown POST {path}"})

    def do_GET(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if path == "/api/session":
            items = [{"id": s["id"], "time": {"created": s["created"]}}
                     for s in _sessions.values()]
            self._json(200, {"data": items, "cursor": {}})
            return
        if len(parts) >= 4 and parts[3] == "message":
            sid = parts[2]
            msgs = _messages.get(sid, [])
            self._json(200, {"data": msgs, "cursor": {}})
            return
        if path == "/global/health":
            self._json(200, {"healthy": True})
            return
        self._json(404, {"error": f"unknown GET {path}"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "session":
            sid = parts[2]
            if sid in _sessions:
                _sessions[sid]["status"] = "stopped"
            self._json(200, {"data": True})
            return
        self._json(404, {"error": f"unknown DELETE {path}"})


if __name__ == "__main__":
    port = int(sys.argv[1])
    _ledger_path = sys.argv[2]
    _mode = sys.argv[3] if len(sys.argv) > 3 else "default"
    open(_ledger_path, "w").close()
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''


@dataclass
class OpenCodeStandIn:
    """A running OpenCode HTTP stand-in subprocess."""

    process: subprocess.Popen
    base_url: str
    ledger_path: Path

    def read_ledger(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        entries = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_opencode_standin(tmp_path: Path, *, mode: str = "default") -> OpenCodeStandIn:
    """Start the OpenCode HTTP stand-in as a subprocess.

    Args:
        tmp_path: Temp directory for the script and ledger.
        mode: Result emission mode (default, malformed, wrong_role,
            stale_artifact, no_result).

    Returns the stand-in handle with ``base_url`` for
    ``LOUKE_OPENCODE_BASE_URL`` and ``ledger_path`` for independent
    dispatch verification.
    """
    script_path = tmp_path / "opencode-standin.py"
    script_path.write_text(_OPENCODE_STANDIN_SCRIPT, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
    ledger_path = tmp_path / "opencode-ledger.jsonl"
    port = _free_port()
    proc = subprocess.Popen(
        [
            __import__("sys").executable,
            str(script_path),
            str(port),
            str(ledger_path),
            mode,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    # Wait for the stand-in to be ready.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            import urllib.request

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"{base_url}/global/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError(f"OpenCode stand-in did not start at {base_url}")
    return OpenCodeStandIn(process=proc, base_url=base_url, ledger_path=ledger_path)


# ---------------------------------------------------------------------------
# GitHub Project stand-in (``gh`` replacement)
# ---------------------------------------------------------------------------

_GH_STANDIN_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Bounded read-only ``gh`` stand-in for isolated workspace checks.

It supports the bounded CLI argv used by Environment readiness and Foundation
Project reconciliation; it never persists command history.
\"\"\"
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if argv == ["--version"]:
        print("gh version 2.65.0 (stand-in)")
        return 0
    if argv == ["auth", "status"]:
        print("github.com")
        print(
            "  ✓ Logged in to github.com account fixture-login "
            "(/Users/openclaw/.config/gh/hosts.yml)"
        )
        print("  - Active account: true")
        print("  - Git operations protocol: https")
        print("  - Token: gho_************************************")
        print("  - Token scopes: 'gist', 'project', 'repo', 'workflow'")
        return 0
    if len(argv) >= 2 and argv[0] == "project" and argv[1] == "list":
        owner = ""
        for i, tok in enumerate(argv):
            if tok == "--owner" and i + 1 < len(argv):
                owner = argv[i + 1]
        payload = {"projects": []}
        print(json.dumps(payload))
        return 0
    if len(argv) >= 2 and argv[0] == "project" and argv[1] == "create":
        owner = ""
        title = ""
        for index, token in enumerate(argv):
            if token == "--owner" and index + 1 < len(argv):
                owner = argv[index + 1]
            if token == "--title" and index + 1 < len(argv):
                title = argv[index + 1]
        print(
            json.dumps(
                {
                    "id": "P_gt_created",
                    "title": title,
                    "url": f"https://github.com/users/{owner}/projects/99",
                }
            )
        )
        return 0
    print(f"gh stand-in: unsupported command: {argv}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
"""


# ---------------------------------------------------------------------------
# OpenCode CLI stand-in executable (``opencode`` replacement)
# ---------------------------------------------------------------------------

_OPENCODE_CLI_STANDIN_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Deterministic ``opencode`` CLI stand-in for the v0.14-004 Setup probe.

Responds to the two ``opencode`` CLI invocations the Setup model probe issues:

  * ``opencode models``                    -> list one configured model id
  * ``opencode run --model <id> <prompt>`` -> exit 0 (a successful minimal request)

Records every invocation in ``LOUKE_OPENCODE_CLI_LEDGER_PATH`` (JSON lines) so
tests can independently prove a real ``opencode run --model`` happened. The
advertised model id is controlled by ``LOUKE_OPENCODE_STANDIN_MODEL``
(default ``minimax/m2``).
\"\"\"
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(ledger: str, entry: dict) -> None:
    if not ledger:
        return
    entry["at"] = _now()
    try:
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\\n")
    except OSError as exc:
        raise RuntimeError("OpenCode stand-in ledger could not be written") from exc


def main(argv: list[str]) -> int:
    ledger = os.environ.get("LOUKE_OPENCODE_CLI_LEDGER_PATH", "")
    model = os.environ.get("LOUKE_OPENCODE_STANDIN_MODEL", "minimax/m2")
    if argv and argv[0] == "models":
        _record(ledger, {"argv": argv, "kind": "models", "model": model})
        print(model)
        return 0
    if argv and argv[0] == "run":
        run_model = ""
        for i, tok in enumerate(argv):
            if tok == "--model" and i + 1 < len(argv):
                run_model = argv[i + 1]
        _record(ledger, {"argv": argv, "kind": "run", "model": run_model})
        print("hi")
        return 0
    _record(ledger, {"argv": argv, "kind": "unsupported"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
"""


# ---------------------------------------------------------------------------
# Isolated workspace builder
# ---------------------------------------------------------------------------


@dataclass
class IsolatedWorkspace:
    """A fully isolated Louke-like workspace for entry-slice tests."""

    root: Path
    bare_remote: Path
    gh_bin: Path
    opencode_bin: Path | None = None
    opencode_ledger: Path | None = None

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )

    def git_output(self, *args: str) -> str:
        result = self.git(*args)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def cleanup(self) -> None:
        worktrees = self.root / ".louke" / "worktrees"
        if worktrees.exists():
            shutil.rmtree(worktrees, ignore_errors=True)
        self.git("branch", "-D", RELEASE_BRANCH)


def build_isolated_workspace(
    tmp_path: Path,
    *,
    include_story: bool = False,
) -> IsolatedWorkspace:
    """Create a Louke-like workspace with a bare Git remote.

    The workspace contains the Louke package marker, project.toml, the
    release-contract bundle, byte-verified contract files, a Git repo with
    ``main`` pushed to a bare ``origin``, and a stand-in ``gh`` script.
    ``story.md`` is intentionally left absent so Foundation creates it
    through the public controlled-worktree commit path.

    Args:
        tmp_path: Temp directory for the workspace.
        include_story: Whether to seed a canonical ``story.md``.
    """
    root = tmp_path / "workspace"
    root.mkdir(parents=True)

    louke_pkg = root / "louke"
    louke_pkg.mkdir()
    shutil.copy2(REPO_ROOT / "louke" / "__init__.py", louke_pkg / "__init__.py")
    templates_dst = louke_pkg / "templates"
    templates_dst.mkdir()
    shutil.copy2(
        REPO_ROOT / "louke" / "templates" / "story.md", templates_dst / "story.md"
    )

    project_dir = root / ".louke" / "project"
    project_dir.mkdir(parents=True)
    project_dir / "specs" / SPEC_ID
    specs_dir = project_dir / "specs"
    specs_dir.mkdir(parents=True)

    project_toml = project_dir / "project.toml"
    project_toml.write_text(
        textwrap.dedent(
            f"""\
            [project]
            version = "{RELEASE_VERSION}"
            repo = "{LOUKE_REPO_IDENTITY}"
            project = "louke-{RELEASE_VERSION}"
            project_id = ""
            spec_id = "{SPEC_ID}"
            release_branch = "{RELEASE_BRANCH}"

            [meta]
            created = "2026-07-23"
            current_stage = "M-LOCK"
            test_framework = "pytest"
            """
        ),
        encoding="utf-8",
    )
    # Login readiness selects only explicitly configured concrete models.
    # Keep the fixture's model identity independent from the host project and
    # let the real ``opencode run --model`` boundary prove availability.
    (root / ".louke" / "models.json").write_text(
        json.dumps(
            {
                "$schema": "louke://models-config",
                "version": 1,
                "aliases": {"minimax-m2": "minimax/m2"},
                "assignments": {"roles": {"A": "minimax-m2"}, "agents": {}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    shutil.copy2(
        REPO_ROOT / _CONTRACT_BUNDLE, project_dir / "release-contract-bundle.json"
    )

    for rel in _CONTRACT_FILES:
        src = REPO_ROOT / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    if include_story:
        story_template_path = REPO_ROOT / "louke" / "templates" / "story.md"
        story_template_body = story_template_path.read_text(encoding="utf-8")
        story_placeholder = "{用户原始输入，逐字记录，不修改或转述}"
        story_md_body = story_template_body.replace(
            story_placeholder, CANONICAL_HUMAN_STORY
        )
        story_md_path = root / ".louke" / "project" / "specs" / SPEC_ID / "story.md"
        story_md_path.write_text(story_md_body, encoding="utf-8")

    gh_dir = tmp_path / "gh-bin"
    gh_dir.mkdir()
    gh_bin = gh_dir / "gh"
    gh_bin.write_text(_GH_STANDIN_SCRIPT, encoding="utf-8")
    gh_bin.chmod(gh_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # ``url.<bare>.insteadOf`` keeps Foundation's actual Git traffic local,
    # but ``git remote get-url`` expands that rewrite.  Environment readiness
    # must observe the configured GitHub binding, while all other Git commands
    # must retain their real local-bare behavior.  This bounded wrapper exposes
    # only that read-only identity fact and delegates every operation to Git.
    git_bin = gh_dir / "git"
    git_bin.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then\n'
        '  printf "%s\\n" "https://github.com/zillionare/louke.git"\n'
        "  exit 0\n"
        "fi\n"
        'exec /usr/bin/git "$@"\n',
        encoding="utf-8",
    )
    git_bin.chmod(git_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # v0.14-004: an ``opencode`` CLI stand-in for the Setup model probe. It
    # lives in the same bin dir as the ``gh`` stand-in so the conftest PATH
    # addition (``workspace.gh_bin.parent``) puts both on PATH. It answers
    # ``opencode models`` and ``opencode run --model <id>`` deterministically
    # and records each call to ``LOUKE_OPENCODE_CLI_LEDGER_PATH``.
    opencode_bin = gh_dir / "opencode"
    opencode_ledger = tmp_path / "opencode-cli-standin-ledger.jsonl"
    opencode_bin.write_text(_OPENCODE_CLI_STANDIN_SCRIPT, encoding="utf-8")
    opencode_bin.chmod(
        opencode_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    )

    bare_remote = tmp_path / "bare-remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare_remote)],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "init", str(root)],
        capture_output=True,
        text=True,
        check=True,
    )
    # Configure a deterministic repository-local Git identity so that commits
    # inside worktrees (created by the Foundation adapter in the ``lk serve``
    # subprocess) succeed even when HOME/global/system Git config is absent
    # (CI isolated environment).  This does NOT weaken production fail-closed
    # behavior: the Foundation adapter's ``git commit`` still requires a valid
    # identity; the fixture simply provides one at the repository level.
    subprocess.run(
        ["git", "config", "user.name", "Test Human"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "human@test.local"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test Human",
        "GIT_AUTHOR_EMAIL": "human@test.local",
        "GIT_COMMITTER_NAME": "Test Human",
        "GIT_COMMITTER_EMAIL": "human@test.local",
    }
    subprocess.run(["git", "add", "-A"], cwd=str(root), env=env, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialise isolated workspace"],
        cwd=str(root),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=str(root), env=env, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare_remote)],
        cwd=str(root),
        env=env,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=str(root),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    canonical_origin = "https://github.com/zillionare/louke.git"
    subprocess.run(
        ["git", "config", f"url.{bare_remote.as_uri()}.insteadOf", canonical_origin],
        cwd=str(root),
        env=env,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", canonical_origin],
        cwd=str(root),
        env=env,
        check=True,
    )

    return IsolatedWorkspace(
        root=root,
        bare_remote=bare_remote,
        gh_bin=gh_bin,
        opencode_bin=opencode_bin,
        opencode_ledger=opencode_ledger,
    )


# ---------------------------------------------------------------------------
# Live server lifecycle helpers
# ---------------------------------------------------------------------------


def wait_for_health(
    base_url: str,
    timeout: float = 30,
    *,
    process: subprocess.Popen[bytes] | None = None,
    log_tail: Callable[[], str] | None = None,
) -> None:
    """Wait for health, failing immediately on an exited server with log evidence.

    Args:
        base_url: Loopback server root.
        timeout: Maximum readiness polling duration.
        process: Optional spawned ``lk serve`` process to monitor.
        log_tail: Optional redacted, bounded stdout/stderr tail supplier.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                f"lk serve exited early with code {process.returncode}; "
                f"server log tail:\n{log_tail() if log_tail else '<unavailable>'}"
            )
        try:
            with urlopen(f"{base_url}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except (URLError, OSError):
            time.sleep(0.2)
    raise TimeoutError(
        f"lk serve did not become healthy at {base_url} within {timeout}s; "
        f"server log tail:\n{log_tail() if log_tail else '<unavailable>'}"
    )


def server_command(
    python: str, workspace: str, *, port: int = 0, opencode_backend: str = "real"
) -> list[str]:
    """Return the public ``lk serve`` command for the installed product."""
    cmd = [
        python,
        "-m",
        "louke",
        "serve",
        "--project-root",
        workspace,
        "--host",
        "127.0.0.1",
        "--opencode-backend",
        opencode_backend,
    ]
    if port:
        cmd.extend(["--port", str(port)])
    return cmd
