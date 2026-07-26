"""Real Git coverage for Foundation/Story creation and reconciliation.

AC-FR0500-01/02/03 and AC-FR0600-02: the initial Story must be created in the
controlled release worktree even when no Story exists at Foundation time.
"""

from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

from louke.runtime.foundation_adapter import ShellFoundationAdapter
from louke.runtime.story_init import StoryInitConflict

from tests.fixtures.v014_workflow_reflow.harness import build_isolated_workspace


SPEC_ID = "v0.14-001-workflow-reflow-spec"
STORY = "Ship the v0.14 reflow entry slice without a pre-existing Story."


def _git(worktree: Path, *args: str) -> str:
    """Run one Git command in the controlled release worktree."""
    result = subprocess.run(
        ["git", *args], cwd=worktree, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.integration
def test_story_creation_without_preexisting_file_preserves_unrelated_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-FR0500-01: absent Story creation commits only the Story target."""
    workspace = build_isolated_workspace(tmp_path, include_story=False)
    try:
        baseline_file = workspace.root / "unrelated.md"
        baseline_file.write_text("original unrelated state\n", encoding="utf-8")
        assert workspace.git("add", "--", "unrelated.md").returncode == 0
        assert (
            workspace.git("commit", "-m", "test: add unrelated baseline").returncode
            == 0
        )
        assert workspace.git("push", "origin", "main").returncode == 0
        monkeypatch.setenv(
            "PATH", f"{workspace.gh_bin.parent}{os.pathsep}{os.environ['PATH']}"
        )
        monkeypatch.setenv("LOUKE_GH_OWNER", "zillionare")
        adapter = ShellFoundationAdapter(workspace.root, spec_id=SPEC_ID)
        main_check = adapter.preflight(STORY, "0.14.0")
        foundation = adapter.provision(STORY, "0.14.0", "run-no-story", main_check)
        assert foundation.status == "ready"
        worktree = Path(foundation.resources["worktree"]["path"])

        unrelated = worktree / "unrelated.md"
        unrelated.write_text("changed but not part of Story\n", encoding="utf-8")
        _git(worktree, "add", "--", "unrelated.md")
        scratch = worktree / "unrelated-scratch.md"
        scratch.write_text("untracked state\n", encoding="utf-8")
        before = _git(worktree, "rev-parse", "HEAD")

        result = adapter.write_story(
            workspace=str(worktree),
            spec_id=SPEC_ID,
            human_story=STORY,
            actor="human:alice",
            run_id="run-no-story",
        )

        assert result.evidence.file_digest.startswith("sha256:")
        assert result.evidence.commit_sha != "pending"
        assert _git(worktree, "rev-parse", "HEAD") == result.evidence.commit_sha
        assert _git(worktree, "diff", "--cached", "--name-only") == "unrelated.md"
        committed = _git(worktree, "show", "--format=", "--name-only", "HEAD")
        assert committed == f".louke/project/specs/{SPEC_ID}/story.md"
        assert _git(worktree, "show", "HEAD:unrelated.md") == "original unrelated state"
        status = _git(worktree, "status", "--short")
        assert "M  unrelated.md" in status
        assert "?? unrelated-scratch.md" in status
        assert before != result.evidence.commit_sha
        assert _git(worktree, "ls-remote", "origin", "refs/heads/main")
    finally:
        workspace.cleanup()


@pytest.mark.integration
def test_story_creation_retry_reconciles_and_conflict_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-FR0500-02/03: retry is stable and changed bytes never overwrite."""
    workspace = build_isolated_workspace(tmp_path, include_story=False)
    try:
        monkeypatch.setenv(
            "PATH", f"{workspace.gh_bin.parent}{os.pathsep}{os.environ['PATH']}"
        )
        monkeypatch.setenv("LOUKE_GH_OWNER", "zillionare")
        adapter = ShellFoundationAdapter(workspace.root, spec_id=SPEC_ID)
        main_check = adapter.preflight(STORY, "0.14.0")
        foundation = adapter.provision(STORY, "0.14.0", "run-retry", main_check)
        worktree = Path(foundation.resources["worktree"]["path"])
        kwargs = {
            "workspace": str(worktree),
            "spec_id": SPEC_ID,
            "human_story": STORY,
            "actor": "human:alice",
            "run_id": "run-retry",
        }
        first = adapter.write_story(**kwargs)
        second = adapter.write_story(**kwargs)
        assert second.evidence.commit_sha == first.evidence.commit_sha
        assert _git(worktree, "rev-list", "--count", "HEAD") == "2"

        story_path = worktree / ".louke" / "project" / "specs" / SPEC_ID / "story.md"
        original = story_path.read_bytes()
        story_path.write_bytes(b"unattributed conflict\n")
        with pytest.raises(StoryInitConflict):
            adapter.write_story(**{**kwargs, "human_story": "different story"})
        assert story_path.read_bytes() == b"unattributed conflict\n"
        assert first.evidence.commit_sha == _git(worktree, "rev-parse", "HEAD")
        story_path.write_bytes(original)
    finally:
        workspace.cleanup()
