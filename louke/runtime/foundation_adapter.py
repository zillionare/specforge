"""Real Git/GitHub Foundation adapter for the v0.14 public entry."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from louke.runtime.release_entry import FoundationOutcome, MainCheck
from louke.runtime.story_init import (
    StoryInitResult,
    StoryTemplate,
    initialize_story_revision,
)


class ShellFoundationAdapter:
    """Reconcile Foundation through safe, explicit ``git`` and ``gh`` commands."""

    def __init__(
        self, workspace_root: str | Path, *, spec_id: str | None = None
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._configured_spec_id = spec_id

    def preflight(self, story: str, release_version: str) -> MainCheck:
        """Refresh origin/main and return full Git identity and relation evidence.

        When ``origin/main`` does not exist (e.g. the workspace was
        cloned from an empty repository or the upstream branch has not
        been pushed yet), the adapter auto-initialises ``refs/heads/main``
        from the current HEAD so a first Story/Preview can run.  Network
        or permission failures still surface as ``blocked``.
        """
        fetched, fetch_error = self._run("git", "fetch", "origin", "main")
        remote_ref = "refs/remotes/origin/main"
        remote_sha = ""
        remote_error = ""
        if not fetched:
            # Distinguish "remote ref missing" from a real fetch failure.
            missing = self._output("git", "ls-remote", "--heads", "origin", "main")
            if missing[1] == 0 and not missing[0].strip():
                # Remote is empty or has no main yet -- treat as a
                # bootstrap repository and fall through.
                fetch_error = ""
            else:
                return MainCheck(
                    status="blocked",
                    remote_main={},
                    previous_branch={},
                    remediation=f"origin/main refresh failed: {fetch_error}",
                    checked_at=_now(),
                )
        else:
            remote_sha, remote_error = self._output("git", "rev-parse", remote_ref)
        local_sha, local_error = self._output("git", "rev-parse", "refs/heads/main")
        if not local_sha:
            # No local main yet -- bootstrap it from the current HEAD so
            # the Story Preview has a working branch to anchor.
            head_sha, head_err = self._output("git", "rev-parse", "HEAD")
            if not head_sha:
                return MainCheck(
                    status="blocked",
                    remote_main={"full_ref": remote_ref, "sha": remote_sha},
                    previous_branch={"full_ref": "", "sha": "", "relation": "unknown"},
                    local_main={"full_ref": "refs/heads/main", "sha": ""},
                    remediation=(
                        "cannot resolve authoritative main or HEAD: "
                        f"{local_error or head_err or remote_error}"
                    ),
                    checked_at=_now(),
                )
            created, create_err = self._run("git", "branch", "main", head_sha)
            if not created:
                return MainCheck(
                    status="blocked",
                    remote_main={"full_ref": remote_ref, "sha": remote_sha},
                    previous_branch={"full_ref": "", "sha": "", "relation": "unknown"},
                    local_main={"full_ref": "refs/heads/main", "sha": head_sha},
                    remediation=("cannot create local main from HEAD: " + create_err),
                    checked_at=_now(),
                )
            local_sha = head_sha
        branch, branch_error = self._output("git", "branch", "--show-current")
        if not remote_sha or not local_sha or not branch:
            return MainCheck(
                status="blocked",
                remote_main={"full_ref": remote_ref, "sha": remote_sha},
                previous_branch={"full_ref": branch, "sha": "", "relation": "unknown"},
                local_main={"full_ref": "refs/heads/main", "sha": local_sha},
                remediation=(
                    "cannot resolve authoritative main or current branch: "
                    f"{remote_error or local_error or branch_error}"
                ),
                checked_at=_now(),
            )
        previous_ref = f"refs/heads/{branch}"
        previous_sha, _ = self._output("git", "rev-parse", previous_ref)
        relation = self._relation(previous_ref, remote_ref)
        # When the remote has no main yet, treat the local main as the
        # authoritative reference; the bootstrap push is the next step.
        if not remote_sha:
            relation = "ahead"
        remediation = (
            ""
            if (relation == "merged" and local_sha == remote_sha)
            or (not remote_sha and local_sha)
            else (
                f"current branch {previous_ref} is {relation} relative to {remote_ref}; "
                "local main must equal authoritative remote main"
            )
        )
        return MainCheck(
            status="pass" if not remediation else "blocked",
            remote_main={"full_ref": remote_ref, "sha": remote_sha},
            previous_branch={
                "full_ref": previous_ref,
                "sha": previous_sha,
                "relation": relation,
            },
            local_main={"full_ref": "refs/heads/main", "sha": local_sha},
            remediation=remediation,
            checked_at=_now(),
        )

    def provision(
        self,
        story: str,
        release_version: str,
        run_id: str,
        main_check: MainCheck,
        spec_id: str | None = None,
    ) -> FoundationOutcome:
        """Create or reconcile branch, worktree, spec directory and GitHub Project."""
        if main_check.status != "pass":
            return FoundationOutcome("blocked", {}, main_check.remediation)
        resources: dict[str, Any] = {
            "local_project": {
                "id": f"prj_{hashlib.sha256(run_id.encode()).hexdigest()[:12]}"
            },
            "workflow_run": {"id": run_id},
        }
        branch = f"releases/{release_version.removeprefix('v')}"
        branch_result = self._ensure_branch(branch, main_check.remote_main["sha"])
        resources["release_branch"] = branch_result[0]
        if branch_result[1]:
            return self._uncertain(resources, branch_result[1])
        project, project_error = self._ensure_github_project(release_version)
        if project is not None:
            resources["github_project"] = project
        if project_error:
            return self._uncertain(resources, project_error)
        worktree, worktree_error = self._ensure_worktree(branch, release_version)
        resources["worktree"] = worktree
        if worktree_error:
            return self._uncertain(resources, worktree_error)
        resources["release_branch"].update(
            {
                "checked_out": True,
                "head_symbolic_ref": worktree["head_symbolic_ref"],
                "head_sha": worktree["head_sha"],
            }
        )
        target_spec_id = spec_id or self._configured_spec_id
        if not target_spec_id:
            return FoundationOutcome(
                "blocked", resources, "confirmed request has no target spec identity"
            )
        spec, spec_error = self._ensure_spec_directory(
            Path(worktree["path"]), target_spec_id
        )
        resources["spec_directory"] = spec
        if spec_error:
            return self._uncertain(resources, spec_error)
        resources["operations"] = [
            {"kind": key, "status": "confirmed", "actual_identity": value}
            for key, value in resources.items()
            if isinstance(value, dict) and "id" in value
        ]
        return FoundationOutcome("ready", resources, "")

    def write_story(
        self,
        *,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        run_id: str,
    ) -> StoryInitResult:
        """Write, commit, or reconcile the initial Story in a controlled worktree.

        Args:
            workspace: Absolute controlled release worktree path.
            spec_id: Relative spec directory identity.
            human_story: Original Human release idea.
            actor: Non-secret actor identity recorded in revision evidence.
            run_id: Runtime run identity recorded in revision evidence.

        Returns:
            A :class:`StoryInitResult` containing document and commit evidence.

        Raises:
            StoryInitConflict: If an existing Story has different bytes.
            ValueError: If ``spec_id`` escapes the controlled worktree.
            RuntimeError: If Git cannot commit or confirm the Story revision.

        Side effects:
            Writes only the controlled ``story.md`` and commits that path.
        """
        worktree = Path(workspace).resolve()
        relative_spec = _safe_relative_spec(spec_id)
        target = (
            worktree / ".louke" / "project" / "specs" / relative_spec / "story.md"
        ).resolve()
        if worktree not in target.parents:
            raise ValueError("spec_id escapes the controlled worktree")
        template_path = self._root / "louke" / "templates" / "story.md"
        if not template_path.is_file():
            template_path = (
                Path(__file__).resolve().parents[1] / "templates" / "story.md"
            )
        template = StoryTemplate(
            body=template_path.read_text(encoding="utf-8"),
            original_input_placeholder="{用户原始输入，逐字记录，不修改或转述}",
        )
        existing = target.read_bytes() if target.exists() else None
        result = initialize_story_revision(
            template=template,
            human_story=human_story,
            actor=actor,
            run_id=run_id,
            commit_sha="pending",
            spec_id=spec_id,
            existing_bytes=existing,
        )
        relative_target = target.relative_to(worktree).as_posix()
        if existing is not None:
            return self._reconcile_story(worktree, relative_target, result)
        if not target.parent.is_dir():
            raise RuntimeError(f"controlled spec directory is absent: {target.parent}")
        target.write_bytes(result.story_md_bytes)
        return self._commit_story(worktree, relative_target, result, run_id)

    def _reconcile_story(
        self, worktree: Path, relative_target: str, result: StoryInitResult
    ) -> StoryInitResult:
        """Reconcile a matching Story and verify its committed blob exactly."""
        commit_sha, error = self._output_at(
            worktree,
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            relative_target,
        )
        if not commit_sha:
            raise RuntimeError(f"cannot reconcile existing Story commit: {error}")
        self._assert_story_blob(
            worktree, relative_target, commit_sha, result.story_md_bytes
        )
        return _with_commit_sha(result, commit_sha)

    def _commit_story(
        self,
        worktree: Path,
        relative_target: str,
        result: StoryInitResult,
        run_id: str,
    ) -> StoryInitResult:
        """Commit only the Story path while retaining unrelated index state."""
        ok, error = self._run_at(worktree, "git", "add", "--", relative_target)
        if not ok:
            raise RuntimeError(f"Story git add failed: {error}")
        ok, error = self._run_at(
            worktree,
            "git",
            "commit",
            "--only",
            "-m",
            f"chore: initialize Story {run_id}",
            "--",
            relative_target,
        )
        if not ok:
            raise RuntimeError(f"Story git commit failed: {error}")
        commit_sha, error = self._output_at(worktree, "git", "rev-parse", "HEAD")
        if not commit_sha:
            raise RuntimeError(f"Story commit identity could not be confirmed: {error}")
        self._assert_story_blob(
            worktree, relative_target, commit_sha, result.story_md_bytes
        )
        return _with_commit_sha(result, commit_sha)

    def _assert_story_blob(
        self, worktree: Path, relative_target: str, commit_sha: str, expected: bytes
    ) -> None:
        """Fail closed unless a confirmed commit contains the exact Story bytes."""
        committed, error = self._output_bytes_at(
            worktree, "git", "show", f"{commit_sha}:{relative_target}"
        )
        if committed != expected:
            raise RuntimeError(
                f"Story commit does not contain expected bytes: {error or relative_target}"
            )

    def _ensure_branch(self, branch: str, main_sha: str) -> tuple[dict[str, str], str]:
        """Query or create a release branch without overwriting an existing ref."""
        ref = f"refs/heads/{branch}"
        existing, _ = self._output("git", "rev-parse", ref)
        if existing:
            if existing != main_sha:
                return (
                    {"full_ref": ref, "start_sha": existing},
                    f"existing release branch starts at {existing}, expected {main_sha}",
                )
            return {"full_ref": ref, "start_sha": existing}, ""
        ok, error = self._run("git", "branch", branch, main_sha)
        return {"full_ref": ref, "start_sha": main_sha}, "" if ok else error

    def _ensure_worktree(self, branch: str, version: str) -> tuple[dict[str, str], str]:
        """Create an isolated controlled worktree and verify symbolic HEAD."""
        path = self._root / ".louke" / "worktrees" / version.removeprefix("v")
        if not path.exists():
            ok, error = self._run("git", "worktree", "add", str(path), branch)
            if not ok:
                return {"path": str(path)}, error
        symbolic, error = self._output_at(
            path, "git", "symbolic-ref", "--short", "HEAD"
        )
        head, head_error = self._output_at(path, "git", "rev-parse", "HEAD")
        expected = branch
        if symbolic != expected:
            return {"path": str(path), "head_symbolic_ref": symbolic}, (
                f"worktree symbolic HEAD {symbolic!r} is not {expected!r}"
            )
        return {"path": str(path), "head_symbolic_ref": symbolic, "head_sha": head}, (
            "" if head else head_error
        )

    def _ensure_spec_directory(
        self, worktree: Path, spec_id: str
    ) -> tuple[dict[str, str], str]:
        """Create the reserved target spec directory in the controlled worktree."""
        try:
            relative = Path(".louke/project/specs") / _safe_relative_spec(spec_id)
        except ValueError as exc:
            return {"path": spec_id}, str(exc)
        target = worktree / relative
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "path": relative.as_posix()
            }, f"target spec directory unavailable: {exc}"
        digest = _directory_digest(target)
        return {"path": relative.as_posix(), "digest": digest}, ""

    def _ensure_github_project(self, version: str) -> tuple[dict[str, str] | None, str]:
        """Query an exact release Project or create it through ``gh project``."""
        repo = self._project_repo()
        owner, name = repo.rsplit("/", 1)
        title = f"{name} {version.removeprefix('v')}"
        output, error = self._output(
            "gh", "project", "list", "--owner", owner, "--format", "json"
        )
        if error:
            return None, f"GitHub Project query failed: {error}"
        try:
            projects = json.loads(output).get("projects", [])
        except json.JSONDecodeError as exc:
            return None, f"GitHub Project query was not valid JSON: {exc}"
        for project in projects:
            if project.get("title") == title:
                return {
                    "node_id": str(project.get("id") or ""),
                    "url": str(project.get("url") or ""),
                }, ""
        created, create_error = self._output(
            "gh",
            "project",
            "create",
            "--owner",
            owner,
            "--title",
            title,
            "--format",
            "json",
        )
        if create_error:
            return None, f"GitHub Project create failed: {create_error}"
        try:
            payload = json.loads(created)
        except json.JSONDecodeError as exc:
            return None, f"GitHub Project create was not valid JSON: {exc}"
        return {
            "node_id": str(payload.get("id") or ""),
            "url": str(payload.get("url") or ""),
        }, ""

    def _project_repo(self) -> str:
        """Return the configured owner/repository identity without credentials."""
        project = _read_project_toml(self._root)
        repo = str(project.get("project", {}).get("repo") or "")
        return repo.removeprefix("github.com/")

    def _relation(self, previous_ref: str, remote_ref: str) -> str:
        """Classify two refs using explicit merge-base checks."""
        if self._run("git", "merge-base", "--is-ancestor", previous_ref, remote_ref)[0]:
            return "merged"
        if self._run("git", "merge-base", "--is-ancestor", remote_ref, previous_ref)[0]:
            return "ahead"
        return (
            "diverged"
            if self._run("git", "merge-base", previous_ref, remote_ref)[0]
            else "unknown"
        )

    def _run(self, *command: str) -> tuple[bool, str]:
        """Run one argument-vector command and return success plus redacted error."""
        result = self._execute(self._root, command)
        return result.returncode == 0, (result.stderr or result.stdout).strip()

    def _output(self, *command: str) -> tuple[str, str]:
        """Run one command and discard stdout whenever its exit code is non-zero."""
        result = self._execute(self._root, command)
        if result.returncode != 0:
            return "", (result.stderr or result.stdout).strip()
        return result.stdout.strip(), ""

    def _output_at(self, path: Path, *command: str) -> tuple[str, str]:
        """Run a command in a controlled worktree, failing closed on errors."""
        result = self._execute(path, command)
        if result.returncode != 0:
            return "", (result.stderr or result.stdout).strip()
        return result.stdout.strip(), ""

    def _run_at(self, path: Path, *command: str) -> tuple[bool, str]:
        """Run a mutating command in the controlled release worktree."""
        result = self._execute(path, command)
        return result.returncode == 0, (result.stderr or result.stdout).strip()

    def _output_bytes_at(self, path: Path, *command: str) -> tuple[bytes, str]:
        """Read exact command bytes from the controlled release worktree."""
        result = subprocess.run(command, cwd=path, capture_output=True, text=False)
        if result.returncode != 0:
            error = (result.stderr or result.stdout).decode(errors="replace").strip()
            return b"", error
        return result.stdout, ""

    @staticmethod
    def _execute(
        cwd: Path, command: tuple[str, ...]
    ) -> subprocess.CompletedProcess[str]:
        """Execute one controlled command with captured text output."""
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True)

    def _uncertain(
        self, resources: dict[str, Any], remediation: str
    ) -> FoundationOutcome:
        """Preserve observed resource identities when a later operation fails."""
        return FoundationOutcome("uncertain", resources, remediation)


def _directory_digest(path: Path) -> str:
    """Hash every regular file under a Foundation spec directory."""
    digest = hashlib.sha256()
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file():
            digest.update(file_path.relative_to(path).as_posix().encode())
            digest.update(file_path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _safe_relative_spec(spec_id: str) -> Path:
    """Validate a spec identity before joining it to a controlled worktree."""
    relative = Path(spec_id)
    if not spec_id or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("spec_id must be a non-empty relative path")
    return relative


def _with_commit_sha(result: StoryInitResult, commit_sha: str) -> StoryInitResult:
    """Return Story evidence with the confirmed commit identity."""
    return replace(
        result,
        evidence=replace(result.evidence, commit_sha=commit_sha),
        navigation=replace(result.navigation, commit_sha=commit_sha),
    )


def _read_project_toml(root: Path) -> dict[str, Any]:
    """Read project metadata using the repository's existing TOML helper."""
    from louke._common import _toml_load

    return _toml_load(root / ".louke/project/project.toml")


def _now() -> str:
    """Return an ISO-8601 UTC observation timestamp."""
    return datetime.now(timezone.utc).isoformat()
