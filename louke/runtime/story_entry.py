"""Runtime-owned initial Story persistence and M-START transition."""

from __future__ import annotations

import threading
import sqlite3
from dataclasses import dataclass
from typing import Protocol

from louke.runtime.program_steps import (
    HandlerRegistry,
    HandlerResult,
    ProgramStepExecutor,
    StepContext,
)
from louke.runtime.store import WorkflowRun, WorkflowRunStore
from louke.runtime.story_init import StoryInitResult


@dataclass(frozen=True)
class StoryArtifact:
    """Persisted identity and content of the initial Story revision.

    Attributes:
        run_id: Runtime run owning the artifact.
        spec_id: Canonical spec directory identity.
        body_md: UTF-8 Story document body.
        revision: Monotonic artifact revision, starting at one.
        digest: SHA-256 digest of ``body_md`` bytes.
        input_digest: SHA-256 digest of the original Human input.
        actor: Non-secret actor identity that created the revision.
        commit_sha: Git commit identity for the revision.
        path: Workspace-relative Story path.
        idempotency_key: Stable initialization attempt identity.
    """

    run_id: str
    spec_id: str
    body_md: str
    revision: int
    digest: str
    input_digest: str
    actor: str
    commit_sha: str
    path: str
    idempotency_key: str


@dataclass(frozen=True)
class StoryEntryOutcome:
    """Result of a successful initial Story transition."""

    run: WorkflowRun
    artifact: StoryArtifact
    task: dict[str, object] | None = None


class StoryWriter(Protocol):
    """Port for the controlled document and Git adapter."""

    def write_story(
        self,
        *,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        run_id: str,
    ) -> StoryInitResult:
        """Write or reconcile the initial Story and return commit evidence."""


class ScribeDispatcher(Protocol):
    """Port for Runtime-owned Scribe task/session dispatch."""

    def ensure_task(
        self,
        *,
        run_id: str,
        artifact: StoryArtifact,
        human_request: str,
        foundation_manifest_identity: str,
        workspace: str,
    ) -> dict[str, object]:
        """Persist and dispatch the task bound to the initial Story."""


class StoryArtifactStore:
    """SQLite persistence for the initial Story artifact identity."""

    def __init__(self, run_store: WorkflowRunStore) -> None:
        self._conn = run_store._conn
        self._lock = threading.RLock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS story_artifacts (
                run_id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                body_md TEXT NOT NULL,
                revision INTEGER NOT NULL,
                digest TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                actor TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                path TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE
            )
            """
        )
        self._conn.commit()

    def get(self, run_id: str) -> StoryArtifact | None:
        """Return the persisted initial Story for ``run_id``, if present."""
        row = self._conn.execute(
            "SELECT * FROM story_artifacts WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_artifact(row) if row is not None else None

    def save(
        self,
        run_id: str,
        spec_id: str,
        result: StoryInitResult,
        idempotency_key: str,
    ) -> StoryArtifact:
        """Persist one initial Story revision and return its stable identity.

        Raises:
            ValueError: If the run already has a different initial Story or the
                idempotency key belongs to another run.
        """
        existing = self.get(run_id)
        if existing is not None:
            if existing.digest != result.evidence.file_digest:
                raise ValueError("run already has a different initial Story digest")
            return existing
        artifact = StoryArtifact(
            run_id=run_id,
            spec_id=spec_id,
            body_md=result.story_md_bytes.decode("utf-8"),
            revision=1,
            digest=result.evidence.file_digest,
            input_digest=result.evidence.input_digest,
            actor=result.evidence.actor,
            commit_sha=result.evidence.commit_sha,
            path=f".louke/project/specs/{spec_id}/story.md",
            idempotency_key=idempotency_key,
        )
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """
                    INSERT INTO story_artifacts
                    (run_id, spec_id, body_md, revision, digest, input_digest,
                     actor, commit_sha, path, idempotency_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.run_id,
                        artifact.spec_id,
                        artifact.body_md,
                        artifact.revision,
                        artifact.digest,
                        artifact.input_digest,
                        artifact.actor,
                        artifact.commit_sha,
                        artifact.path,
                        artifact.idempotency_key,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "initial Story idempotency identity conflicts"
                ) from exc
        return artifact


class StoryEntryService:
    """Execute M-START through the Runtime program-step executor."""

    def __init__(
        self,
        run_store: WorkflowRunStore,
        writer: StoryWriter,
        scribe_entry: ScribeDispatcher | None = None,
    ) -> None:
        self._run_store = run_store
        self._writer = writer
        self._scribe_entry = scribe_entry
        self._artifacts = StoryArtifactStore(run_store)

    def artifact(self, run_id: str) -> StoryArtifact | None:
        """Return the persisted initial Story artifact for ``run_id``."""
        return self._artifacts.get(run_id)

    def initialize(
        self,
        *,
        run_id: str,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        idempotency_key: str,
        foundation_manifest_identity: str = "",
    ) -> StoryEntryOutcome:
        """Create the initial Story and advance the bound run to M-STORY.

        Args:
            run_id: Runtime run currently positioned at ``M-START``.
            workspace: Controlled workspace passed to the document adapter.
            spec_id: Canonical spec directory identity.
            human_story: Original Human release idea.
            actor: Authenticated Human actor identity.
            idempotency_key: Stable identity for this initialization attempt.

        Returns:
            The updated Runtime run and its persisted Story artifact.

        Raises:
            ValueError: If the run is not at ``M-START`` or the artifact cannot
                be persisted consistently.
            Exception: Adapter errors are propagated without advancing the run.
        """
        run = self._run_store.get_run(run_id)
        existing = self._artifacts.get(run_id)
        if existing is not None and existing.idempotency_key == idempotency_key:
            return StoryEntryOutcome(
                run=run,
                artifact=existing,
                task=self._ensure_scribe(
                    existing,
                    human_story,
                    foundation_manifest_identity,
                    workspace,
                ),
            )
        entry_step = self._entry_step(run)
        if run.current_step != entry_step.step_id:
            raise ValueError(
                "Story initialization requires the declared entry stage "
                f"{entry_step.step_id}, got {run.current_step}"
            )
        registry = HandlerRegistry()
        failure: list[Exception] = []
        registry.register(
            entry_step.handler or f"runtime:{entry_step.step_id}",
            self._handler(
                workspace=workspace,
                spec_id=spec_id,
                human_story=human_story,
                actor=actor,
                idempotency_key=idempotency_key,
                failure=failure,
            ),
        )
        outcome = ProgramStepExecutor(registry).execute(
            self._run_store, run_id, workspace, idempotency_key
        )
        if failure:
            raise failure[0]
        if outcome.error_code is not None:
            raise ValueError(
                f"M-START Story initialization failed: {outcome.error_code}"
            )
        artifact = self._artifacts.get(run_id)
        if artifact is None:
            raise ValueError("M-START completed without a persisted Story artifact")
        return StoryEntryOutcome(
            run=outcome.run,
            artifact=artifact,
            task=self._ensure_scribe(
                artifact,
                human_story,
                foundation_manifest_identity,
                workspace,
            ),
        )

    def _ensure_scribe(
        self,
        artifact: StoryArtifact,
        human_story: str,
        foundation_manifest_identity: str,
        workspace: str,
    ) -> dict[str, object] | None:
        """Ensure the M-STORY Scribe task exists after Story persistence."""
        if self._scribe_entry is None:
            return None
        return self._scribe_entry.ensure_task(
            run_id=artifact.run_id,
            artifact=artifact,
            human_request=human_story,
            foundation_manifest_identity=foundation_manifest_identity,
            workspace=workspace,
        )

    def _entry_step(self, run: WorkflowRun):
        """Return the declared initial program step for ``run``'s definition."""
        catalog = self._run_store._catalog
        if catalog is None:
            raise ValueError("Runtime catalog is not configured")
        definition = catalog.get(run.definition_id, run.definition_version)
        for step in definition.steps:
            if step.step_id == definition.start_step:
                return step
        raise ValueError("Workflow definition has no declared entry step")

    def _handler(
        self,
        *,
        workspace: str,
        spec_id: str,
        human_story: str,
        actor: str,
        idempotency_key: str,
        failure: list[BaseException],
    ):
        """Build the request-bound Runtime handler for initial Story creation."""

        def handle(context: StepContext) -> HandlerResult:
            existing = self._artifacts.get(context.run_id)
            if existing is not None:
                return HandlerResult("done", {"digest": existing.digest})
            try:
                result = self._writer.write_story(
                    workspace=workspace,
                    spec_id=spec_id,
                    human_story=human_story,
                    actor=actor,
                    run_id=context.run_id,
                )
                artifact = self._artifacts.save(
                    context.run_id, spec_id, result, idempotency_key
                )
            except Exception as exc:
                failure.append(exc)
                return HandlerResult("failed")
            return HandlerResult("done", {"digest": artifact.digest})

        return handle


def _row_to_artifact(row) -> StoryArtifact:
    """Convert a SQLite row into a Story artifact read model."""
    return StoryArtifact(
        run_id=row["run_id"],
        spec_id=row["spec_id"],
        body_md=row["body_md"],
        revision=row["revision"],
        digest=row["digest"],
        input_digest=row["input_digest"],
        actor=row["actor"],
        commit_sha=row["commit_sha"],
        path=row["path"],
        idempotency_key=row["idempotency_key"],
    )
