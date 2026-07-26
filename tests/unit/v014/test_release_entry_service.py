"""Contract tests for the authenticated v0.14 release entry service."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

import pytest

from louke.runtime.catalog import DefinitionRegistry, Edge, Step, WorkflowDefinition
from louke.runtime.store import WorkflowRunStore
from louke.runtime.story_init import (
    StoryInitConflict,
    StoryInitResult,
    StoryNavigation,
    StoryRevisionEvidence,
)
from louke.runtime.release_entry import (
    FoundationOutcome,
    MainCheck,
    ReleaseEntryService,
    StalePreviewError,
)
from louke.runtime.story_entry import StoryEntryService


def _run_store(db_path: str | None = None) -> WorkflowRunStore:
    catalog = DefinitionRegistry()
    catalog.register(
        WorkflowDefinition(
            definition_id="new_feature",
            version="0.14.0",
            start_step="M-START",
            steps=(
                Step(
                    step_id="M-START",
                    kind="program",
                    handler="v014.m_start",
                    implemented=False,
                    transitions=(Edge("start-story", "M-START", "M-STORY", "done"),),
                ),
                Step(
                    step_id="M-STORY",
                    kind="program",
                    handler="v014.m_story",
                    implemented=False,
                ),
            ),
        )
    )
    return WorkflowRunStore(db_path=db_path, catalog=catalog)


@dataclass
class FakeFoundation:
    check: MainCheck
    outcome: FoundationOutcome
    check_calls: int = 0
    provision_calls: int = 0
    spec_ids: list[str] = field(default_factory=list)

    def preflight(self, story: str, release_version: str) -> MainCheck:
        self.check_calls += 1
        return self.check

    def provision(
        self,
        story: str,
        release_version: str,
        run_id: str,
        main_check: MainCheck,
        spec_id: str,
    ) -> FoundationOutcome:
        self.provision_calls += 1
        self.spec_ids.append(spec_id)
        resources = dict(self.outcome.resources)
        resources["spec_directory"] = {"path": f".louke/project/specs/{spec_id}"}
        return FoundationOutcome(
            self.outcome.status, resources, self.outcome.remediation
        )


def _main_check(status: str = "pass") -> MainCheck:
    return MainCheck(
        status=status,
        remote_main={"full_ref": "refs/remotes/origin/main", "sha": "sha-main"},
        previous_branch={
            "full_ref": "refs/heads/releases/0.13.0",
            "sha": "sha-previous",
            "relation": "merged",
        },
        remediation="" if status == "pass" else "fetch and merge main",
    )


def _ready_outcome() -> FoundationOutcome:
    return FoundationOutcome(
        status="ready",
        resources={
            "github_project": {"node_id": "PVT_1", "url": "https://github.test/p/1"},
            "release_branch": {
                "full_ref": "refs/heads/releases/0.14.0",
                "start_sha": "sha-main",
            },
            "spec_directory": {"path": ".louke/project/specs/v0.14-001"},
        },
        remediation="",
    )


@dataclass
class FakeStoryWriter:
    calls: int = 0
    conflict: StoryInitConflict | None = None

    def write_story(
        self,
        *,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        run_id: str,
    ) -> StoryInitResult:
        self.calls += 1
        if self.conflict is not None:
            raise self.conflict
        body = f"# Story\n\n> {human_story}\n"
        return StoryInitResult(
            story_md_bytes=body.encode(),
            evidence=StoryRevisionEvidence(
                input_digest="sha256:input",
                file_digest="sha256:file",
                actor=actor,
                run_id=run_id,
                commit_sha="sha-story",
            ),
            navigation=StoryNavigation(
                run_id=run_id,
                spec_id=spec_id,
                phase="M-STORY",
                document="story",
                revision_digest="sha256:file",
                commit_sha="sha-story",
            ),
        )


def test_preview_persists_revision_without_foundation_side_effects() -> None:
    """AC-FR0300-01: preview persists a revision but creates no release resources."""
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")

    preview = service.preview("Ship the reflow", "v0.14.0")

    assert preview["preview_revision"] == 0
    assert preview["side_effects"] == []
    assert foundation.check_calls == 0
    assert service.status(preview["request_id"])["status"] == "preview"


def test_confirm_rejects_stale_revision_and_digest() -> None:
    """AC-FR0600-03: stale preview confirmation changes no persisted state."""
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    preview = service.preview("Ship the reflow", "v0.14.0")

    with pytest.raises(StalePreviewError):
        service.confirm(
            preview["preview_id"],
            expected_preview_revision=1,
            request_digest=preview["request_digest"],
            idempotency_key="idem-1",
            actor="human",
        )

    assert service.status(preview["request_id"])["status"] == "preview"
    assert foundation.check_calls == 0


def test_confirm_ready_persists_run_and_replays_idempotently() -> None:
    """AC-FR0400-02: successful confirmation persists Foundation and WorkflowRun once."""
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    preview = service.preview("Ship the reflow", "v0.14.0")
    request = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )
    replay = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )

    assert request["status"] == "ready"
    assert request["run_id"]
    assert replay == request
    assert foundation.check_calls == 1
    assert foundation.provision_calls == 1


def test_confirm_reserves_a_canonical_spec_identity_and_reuses_it(
    tmp_path: Path,
) -> None:
    """AC-FR1101-01: Confirm reserves one new target without touching an old Story."""
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    (tmp_path / ".louke/project/specs/v0.15-007-existing").mkdir(parents=True)
    old_story = tmp_path / ".louke/project/specs/v0.14-001-existing/story.md"
    old_story.parent.mkdir(parents=True)
    old_story.write_text(
        "# Existing v0.14 Story\n\nDo not replace.\n", encoding="utf-8"
    )
    service = ReleaseEntryService(
        _run_store(), foundation, workspace_id="ws-1", workspace_root=tmp_path
    )
    preview = service.preview("Ship the Reflow!", "v0.15.0")

    confirmed = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-spec-id",
        actor="human",
    )
    replay = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-spec-id",
        actor="human",
    )

    assert confirmed["spec_id"] == "v0.15-008-ship-the-reflow"
    assert replay["spec_id"] == confirmed["spec_id"]
    assert replay["project_id"] == confirmed["project_id"]
    assert replay["run_id"] == confirmed["run_id"]
    assert foundation.spec_ids == [confirmed["spec_id"]]
    assert (
        old_story.read_text(encoding="utf-8")
        == "# Existing v0.14 Story\n\nDo not replace.\n"
    )


def test_confirm_ready_initializes_story_and_enters_m_story() -> None:
    """AC-FR0500-01/03: ready Foundation confirmation creates Story revision."""
    store = _run_store()
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    writer = FakeStoryWriter()
    service = ReleaseEntryService(
        store,
        foundation,
        workspace_id="ws-1",
        story_entry=StoryEntryService(store, writer),
    )
    preview = service.preview("Ship the reflow", "v0.14.0")

    request = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human:alice",
    )

    assert request["status"] == "ready"
    assert request["story"]["revision"] == 1
    assert request["story"]["phase"] == "M-STORY"
    assert store.get_run(request["run_id"]).current_step == "M-STORY"
    assert writer.calls == 1


def test_ready_creation_persists_the_authoritative_active_project_context(
    tmp_path: Path,
) -> None:
    """IF-CREATE-01: ready Story evidence publishes the active Project chain."""
    store = _run_store()
    service = ReleaseEntryService(
        store,
        FakeFoundation(_main_check(), _ready_outcome()),
        workspace_id="ws-1",
        story_entry=StoryEntryService(store, FakeStoryWriter()),
        workspace_root=tmp_path,
    )
    preview = service.preview("Ship the reflow", "v0.14.0")

    creation = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-project-context",
        actor="human:alice",
    )

    state = json.loads((tmp_path / ".louke" / "project-state.json").read_text())
    assert state["state"] == "active"
    assert state["project_id"] == creation["project_id"]
    assert state["project"] == {
        "project_id": creation["project_id"],
        "request_id": creation["request_id"],
        "run_id": creation["run_id"],
        "release_version": "0.14.0",
        "spec_id": creation["spec_id"],
        "github_project_node_id": "PVT_1",
        "story_revision": 1,
    }


def test_story_initialization_conflict_is_recoverable_and_not_ready() -> None:
    """AC-FR0500-02: Story conflict preserves M-START and exposes remediation."""
    store = _run_store()
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    writer = FakeStoryWriter(
        conflict=StoryInitConflict(
            existing_bytes=b"human edit",
            expected_file_digest="sha256:expected",
        )
    )
    service = ReleaseEntryService(
        store,
        foundation,
        workspace_id="ws-1",
        story_entry=StoryEntryService(store, writer),
    )
    preview = service.preview("Ship the reflow", "v0.14.0")

    request = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human:alice",
    )

    assert request["status"] == "conflict"
    assert "STORY_INITIALIZATION_CONFLICT" in request["foundation"]["remediation"]
    assert store.get_run(request["run_id"]).current_step == "M-START"


def test_blocked_preflight_can_recheck_without_creating_a_run() -> None:
    """AC-FR0400-04: blocked main preflight is persisted and recoverable."""
    foundation = FakeFoundation(_main_check("blocked"), _ready_outcome())
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    preview = service.preview("Ship the reflow", "v0.14.0")
    blocked = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )

    foundation.check = _main_check("pass")
    recovered = service.recheck(preview["request_id"], actor="human")

    assert blocked["status"] == "blocked"
    assert blocked["run_id"] is None
    assert recovered["status"] == "ready"
    assert recovered["run_id"]
    assert foundation.check_calls == 2


def test_partial_foundation_effect_is_not_reported_as_ready() -> None:
    """AC-FR0400-05: uncertain Foundation effects remain recoverable and blocked."""
    outcome = FoundationOutcome(
        status="uncertain",
        resources={"github_project": {"node_id": "PVT_1"}},
        remediation="query the release project before retrying",
    )
    foundation = FakeFoundation(_main_check(), outcome)
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    preview = service.preview("Ship the reflow", "v0.14.0")

    result = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )

    assert result["status"] == "blocked"
    assert result["foundation"]["status"] == "uncertain"
    assert result["run_id"]


def test_failed_foundation_run_is_persisted_as_non_active_operation_evidence() -> None:
    """AC-FR0400-01: blocked Foundation never looks like an active started run."""
    outcome = FoundationOutcome(
        status="blocked",
        resources={},
        remediation="release branch cannot be reconciled",
    )
    store = _run_store()
    service = ReleaseEntryService(
        store, FakeFoundation(_main_check(), outcome), workspace_id="ws-1"
    )
    preview = service.preview("Ship the reflow", "v0.14.0")

    result = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )

    run = store.get_run(result["run_id"])
    assert result["status"] == "blocked"
    assert run.current_step == "M-START"
    assert run.status == "foundation_pending"


def test_project_lookup_returns_only_its_persisted_request_identity() -> None:
    """AC-FR0600-01: project lookup cannot borrow another request's run."""
    service = ReleaseEntryService(
        _run_store(),
        FakeFoundation(_main_check(), _ready_outcome()),
        workspace_id="ws-1",
    )
    preview = service.preview("Ship the reflow", "v0.14.0")
    request_id = preview["request_id"]
    service._requests.update(request_id, project_id="project-a", run_id="run-a")

    assert service.current_project("project-a")["run_id"] == "run-a"
    assert service.current_project("project-b") is None


def test_uncertain_foundation_recheck_reuses_the_original_run() -> None:
    """AC-FR0400-03: recovery queries one Foundation identity and never duplicates the run."""
    outcome = FoundationOutcome(
        status="uncertain",
        resources={"github_project": {"node_id": "PVT_1"}},
        remediation="query the release project before retrying",
    )
    foundation = FakeFoundation(_main_check(), outcome)
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    preview = service.preview("Ship the reflow", "v0.14.0")
    first = service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )
    foundation.outcome = _ready_outcome()
    second = service.recheck(preview["request_id"], actor="human")

    assert second["status"] == "ready"
    assert second["run_id"] == first["run_id"]
    assert foundation.provision_calls == 2


def test_blocked_foundation_recheck_after_restart_reactivates_same_run(
    tmp_path,
) -> None:
    """AC-FR0400-03: restart/recheck reuses evidence without orphan activation."""
    db_path = str(tmp_path / "runtime.sqlite3")
    first_foundation = FakeFoundation(
        _main_check(),
        FoundationOutcome(
            status="blocked", resources={}, remediation="release branch missing"
        ),
    )
    first_store = _run_store(db_path)
    first_service = ReleaseEntryService(
        first_store, first_foundation, workspace_id="ws-1"
    )
    preview = first_service.preview("Ship the reflow", "v0.14.0")
    blocked = first_service.confirm(
        preview["preview_id"],
        expected_preview_revision=0,
        request_digest=preview["request_digest"],
        idempotency_key="idem-1",
        actor="human",
    )
    run_id = blocked["run_id"]
    assert first_store.get_run(run_id).status == "foundation_pending"
    first_store.close()

    second_foundation = FakeFoundation(_main_check(), _ready_outcome())
    second_store = _run_store(db_path)
    second_service = ReleaseEntryService(
        second_store, second_foundation, workspace_id="ws-1"
    )
    recovered = second_service.recheck(preview["request_id"], actor="human")

    assert recovered["run_id"] == run_id
    assert second_store.get_run(run_id).status == "waiting_human"


def test_uncertain_foundation_blocks_a_second_release_request() -> None:
    """AC-FR0400-05: unresolved external effects keep the workspace single-active."""
    foundation = FakeFoundation(
        _main_check(),
        FoundationOutcome(
            status="uncertain",
            resources={"github_project": {"node_id": "PVT_1"}},
            remediation="query the release project before retrying",
        ),
    )
    service = ReleaseEntryService(_run_store(), foundation, workspace_id="ws-1")
    first = service.preview("First release", "v0.14.0")
    service.confirm(
        first["preview_id"],
        expected_preview_revision=0,
        request_digest=first["request_digest"],
        idempotency_key="idem-first",
        actor="human",
    )
    second = service.preview("Second release", "v0.15.0")

    result = service.confirm(
        second["preview_id"],
        expected_preview_revision=0,
        request_digest=second["request_digest"],
        idempotency_key="idem-second",
        actor="human",
    )

    assert result["status"] == "backlogged"
    assert foundation.provision_calls == 1


def test_active_release_is_persistently_backlogged_without_second_run(
    tmp_path,
) -> None:
    """AC-FR0300-02: active conflict survives restart and creates no second run."""
    db_path = str(tmp_path / "runtime.sqlite3")
    foundation = FakeFoundation(_main_check(), _ready_outcome())
    first_service = ReleaseEntryService(
        _run_store(db_path), foundation, workspace_id="ws-1"
    )
    first = first_service.preview("First release", "v0.14.0")
    first_service.confirm(
        first["preview_id"],
        expected_preview_revision=0,
        request_digest=first["request_digest"],
        idempotency_key="idem-first",
        actor="human",
    )
    second = first_service.preview("Second release", "v0.15.0")
    blocked = first_service.confirm(
        second["preview_id"],
        expected_preview_revision=0,
        request_digest=second["request_digest"],
        idempotency_key="idem-second",
        actor="human",
    )

    restarted = ReleaseEntryService(
        _run_store(db_path), foundation, workspace_id="ws-1"
    )

    assert blocked["status"] == "backlogged"
    assert restarted.status(second["request_id"])["backlog"]["entry_id"]
    assert foundation.provision_calls == 1
