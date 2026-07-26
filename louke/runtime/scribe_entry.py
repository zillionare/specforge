"""Persistent M-STORY Scribe task, session and message orchestration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from louke.opencode.adapter import OpenCodeAdapter, ProviderResult
from louke.runtime.store import WorkflowRunStore
from louke.runtime.task_manifest import build_manifest
from louke.runtime.workflow_authority import (
    ActionForbidden,
    Phase,
    PhaseAction,
    RunState,
    WorkflowAuthority,
    WorkflowStateConflict,
)
from louke.runtime.scribe_dispatch import dispatch_scribe_investigation


class ScribeTaskError(ValueError):
    """Fail-closed Scribe task or message rejection with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ScribeStore:
    """SQLite persistence for Scribe tasks, attempts and messages."""

    def __init__(self, run_store: WorkflowRunStore) -> None:
        self._conn = run_store._conn
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scribe_tasks (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                phase TEXT NOT NULL,
                role TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                manifest_digest TEXT NOT NULL,
                artifact_revision INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                write_scope_json TEXT NOT NULL,
                output_contract_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                active_attempt_id TEXT NOT NULL,
                session_id TEXT,
                connection TEXT NOT NULL,
                lease_id TEXT NOT NULL,
                last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS scribe_attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL,
                session_id TEXT,
                status TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                manifest_digest TEXT NOT NULL,
                dispatch_count INTEGER NOT NULL DEFAULT 0,
                result_status TEXT,
                error TEXT,
                UNIQUE(task_id, attempt_no)
            );
            CREATE TABLE IF NOT EXISTS scribe_messages (
                message_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                client_message_id TEXT NOT NULL UNIQUE,
                correlation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_message_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scribe_results (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                attempt_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                manifest_digest TEXT NOT NULL,
                artifact_revision INTEGER NOT NULL,
                artifact_digest TEXT NOT NULL,
                write_scope_json TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                reason TEXT NOT NULL,
                result_status TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS story_decisions (
                run_id TEXT PRIMARY KEY,
                story_revision INTEGER NOT NULL,
                story_digest TEXT NOT NULL,
                value TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_kind TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                decided_at TEXT NOT NULL,
                backlog_json TEXT,
                cleanup_json TEXT
            );
            """
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Return one raw persisted task record, if present."""
        row = self._conn.execute(
            "SELECT * FROM scribe_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return _decode_task(row) if row is not None else None

    def get_task_for_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the single Scribe task bound to ``run_id``, if present."""
        row = self._conn.execute(
            "SELECT * FROM scribe_tasks WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _decode_task(row) if row is not None else None

    def create_task(
        self,
        *,
        task_id: str,
        run_id: str,
        manifest: dict[str, Any],
        manifest_digest: str,
        artifact_revision: int,
        artifact_digest: str,
        output_contract_digest: str,
        attempt_id: str,
        lease_id: str,
    ) -> None:
        """Persist a new task, its first attempt identity and write lease."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO scribe_tasks
                (task_id, run_id, phase, role, manifest_json, manifest_digest,
                 artifact_revision, artifact_digest, write_scope_json,
                 output_contract_digest, status, active_attempt_id, session_id,
                 connection, lease_id, last_error)
                VALUES (?, ?, 'M-STORY', 'Scribe', ?, ?, ?, ?, ?, ?,
                        'pending', ?, NULL, 'reconnecting', ?, NULL)
                """,
                (
                    task_id,
                    run_id,
                    json.dumps(manifest, sort_keys=True),
                    manifest_digest,
                    artifact_revision,
                    artifact_digest,
                    json.dumps(["story.md"]),
                    output_contract_digest,
                    attempt_id,
                    lease_id,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO scribe_attempts
                (attempt_id, task_id, attempt_no, status, input_digest, manifest_digest)
                VALUES (?, ?, 1, 'pending', ?, ?)
                """,
                (
                    attempt_id,
                    task_id,
                    manifest["artifact"]["input_digest"],
                    manifest_digest,
                ),
            )

    def create_attempt(
        self,
        *,
        task: dict[str, Any],
        attempt_id: str,
        attempt_no: int,
        manifest: dict[str, Any],
        manifest_digest: str,
    ) -> None:
        """Persist a retry attempt and make it the task's active attempt."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO scribe_attempts
                (attempt_id, task_id, attempt_no, status, input_digest, manifest_digest)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (
                    attempt_id,
                    task["task_id"],
                    attempt_no,
                    task["manifest"]["artifact"]["input_digest"],
                    manifest_digest,
                ),
            )
            self._conn.execute(
                """
                UPDATE scribe_tasks
                SET manifest_json = ?, manifest_digest = ?, active_attempt_id = ?,
                    session_id = NULL, status = 'pending', connection = 'reconnecting',
                    last_error = NULL
                WHERE task_id = ?
                """,
                (
                    json.dumps(manifest, sort_keys=True),
                    manifest_digest,
                    attempt_id,
                    task["task_id"],
                ),
            )

    def update_task(self, task_id: str, **fields: Any) -> None:
        """Update a controlled set of task lifecycle fields."""
        allowed = {
            "status",
            "session_id",
            "connection",
            "last_error",
            "active_attempt_id",
            "manifest_json",
            "manifest_digest",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported Scribe task fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE scribe_tasks SET {assignments} WHERE task_id = ?",
                (*fields.values(), task_id),
            )

    def update_attempt(self, attempt_id: str, **fields: Any) -> None:
        """Update an attempt lifecycle and dispatch evidence."""
        allowed = {"status", "session_id", "dispatch_count", "error", "result_status"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported Scribe attempt fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE scribe_attempts SET {assignments} WHERE attempt_id = ?",
                (*fields.values(), attempt_id),
            )

    def get_attempts(self, task_id: str) -> list[dict[str, Any]]:
        """Return attempts for a task in ascending attempt order."""
        rows = self._conn.execute(
            "SELECT * FROM scribe_attempts WHERE task_id = ? ORDER BY attempt_no",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_message_by_client(self, client_message_id: str) -> dict[str, Any] | None:
        """Return a persisted message by its client idempotency identity."""
        row = self._conn.execute(
            "SELECT * FROM scribe_messages WHERE client_message_id = ?",
            (client_message_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def record_message(
        self,
        *,
        message_id: str,
        task_id: str,
        attempt_id: str,
        client_message_id: str,
        correlation_id: str,
        role: str,
        body: str,
        status: str,
        provider_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a message before any external dispatch is attempted."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO scribe_messages
                (message_id, task_id, attempt_id, client_message_id, correlation_id,
                 role, body, status, provider_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    task_id,
                    attempt_id,
                    client_message_id,
                    correlation_id,
                    role,
                    body,
                    status,
                    provider_message_id,
                    now,
                ),
            )
        return self.get_message_by_client(client_message_id) or {}

    def update_message(self, message_id: str, **fields: Any) -> dict[str, Any]:
        """Update message dispatch status and return the persisted message."""
        allowed = {"status", "provider_message_id"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported Scribe message fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE scribe_messages SET {assignments} WHERE message_id = ?",
                (*fields.values(), message_id),
            )
        row = self._conn.execute(
            "SELECT * FROM scribe_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return dict(row) if row is not None else {}

    def list_messages(self, task_id: str) -> list[dict[str, Any]]:
        """Return persisted task messages in creation order."""
        rows = self._conn.execute(
            "SELECT * FROM scribe_messages WHERE task_id = ? ORDER BY created_at, message_id",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """Return the persisted result for one Scribe task, if present."""
        row = self._conn.execute(
            "SELECT * FROM scribe_results WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["write_scope"] = json.loads(result.pop("write_scope_json"))
        return result

    def save_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Persist one accepted Scribe result and return its read model."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO scribe_results
                (task_id, run_id, attempt_id, session_id, role, manifest_digest,
                 artifact_revision, artifact_digest, write_scope_json,
                 recommendation, reason, result_status, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?)
                """,
                (
                    result["task_id"],
                    result["run_id"],
                    result["attempt_id"],
                    result["session_id"],
                    result["role"],
                    result["manifest_digest"],
                    result["artifact_revision"],
                    result["artifact_digest"],
                    json.dumps(result["write_scope"], sort_keys=True),
                    result["recommendation"],
                    result["reason"],
                    result["received_at"],
                ),
            )
        return self.get_result(str(result["task_id"])) or {}

    def get_decision(self, run_id: str) -> dict[str, Any] | None:
        """Return the persisted Human story decision for a run, if present."""
        row = self._conn.execute(
            "SELECT * FROM story_decisions WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        decision = dict(row)
        for field in ("backlog_json", "cleanup_json"):
            key = field.removesuffix("_json")
            decision[key] = json.loads(decision.pop(field)) if decision[field] else None
        return decision

    def save_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        """Persist one Human story decision and its optional exit evidence."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO story_decisions
                (run_id, story_revision, story_digest, value, reason, actor,
                 actor_kind, idempotency_key, decided_at, backlog_json, cleanup_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["run_id"],
                    decision["story_revision"],
                    decision["story_digest"],
                    decision["value"],
                    decision["reason"],
                    decision["actor"],
                    decision["actor_kind"],
                    decision["idempotency_key"],
                    decision["decided_at"],
                    json.dumps(decision["backlog"], sort_keys=True)
                    if decision.get("backlog") is not None
                    else None,
                    json.dumps(decision["cleanup"], sort_keys=True)
                    if decision.get("cleanup") is not None
                    else None,
                ),
            )
        return self.get_decision(str(decision["run_id"])) or {}


class ScribeEntryService:
    """Coordinate manifest-bound Scribe work through real OpenCode transport."""

    def __init__(
        self,
        run_store: WorkflowRunStore,
        adapter: OpenCodeAdapter | None = None,
        *,
        workspace_root: str | Path | None = None,
        adapter_factory: Callable[[Path], OpenCodeAdapter] | None = None,
    ) -> None:
        self._run_store = run_store
        self._adapter = adapter
        self._workspace_root = (
            Path(workspace_root).resolve() if workspace_root else None
        )
        self._adapter_factory = adapter_factory
        self._store = ScribeStore(run_store)

    def ensure_task(
        self,
        *,
        run_id: str,
        artifact: Any,
        human_request: str,
        foundation_manifest_identity: str,
        workspace: str,
    ) -> dict[str, Any]:
        """Persist and dispatch the first Scribe attempt for an M-STORY run."""
        run = self._run_store.get_run(run_id)
        if run.current_step != "M-STORY":
            raise ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT",
                f"Scribe requires M-STORY, got {run.current_step}",
            )
        existing = self._store.get_task_for_run(run_id)
        if existing is not None:
            return self._read_task(existing)
        task_id = _stable_id("task", run_id)
        attempt_id = _stable_id("attempt", f"{run_id}:1")
        manifest, manifest_digest = _build_manifest(
            run=run,
            artifact=artifact,
            task_id=task_id,
            attempt_id=attempt_id,
            human_request=human_request,
            foundation_manifest_identity=foundation_manifest_identity,
        )
        lease_id = _stable_id("lease", f"{task_id}:{attempt_id}")
        output_contract_digest = _digest("scribe.story.v1")
        self._store.create_task(
            task_id=task_id,
            run_id=run_id,
            manifest=manifest,
            manifest_digest=manifest_digest,
            artifact_revision=artifact.revision,
            artifact_digest=artifact.digest,
            output_contract_digest=output_contract_digest,
            attempt_id=attempt_id,
            lease_id=lease_id,
        )
        return self._dispatch(
            task_id=task_id,
            attempt_id=attempt_id,
            manifest=manifest,
            story_body=artifact.body_md,
            workspace=workspace,
        )

    def task_read(self, run_id: str, task_id: str) -> dict[str, Any]:
        """Return a persistent task read model after validating run binding."""
        task = self._require_task(run_id, task_id)
        return self._read_task(task)

    def task_for_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the persisted task bound to a run without creating one."""
        return self._store.get_task_for_run(run_id)

    def submit_result(
        self,
        *,
        run_id: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and persist one manifest-bound Scribe recommendation.

        Args:
            run_id: Runtime run bound to the task.
            task_id: Persisted Scribe task identity.
            payload: Agent result containing role, attempt/session identity,
                manifest/artifact digests, write scope, recommendation and reason.

        Returns:
            The accepted recommendation read model. An identical retry returns
            the original persisted result.

        Raises:
            ScribeTaskError: If any task, attempt, session, digest, scope or
                recommendation field is stale, malformed or unauthorized.

        Side effects:
            Only an accepted result and its attempt evidence are persisted;
            rejected results update the attempt diagnostic and never advance the
            Runtime phase or create an M-SPEC task.
        """
        task = self._require_task(run_id, task_id)
        existing = self._store.get_result(task_id)
        if existing is not None:
            return _public_result(existing)
        try:
            result = self._validate_result(task, payload)
        except ScribeTaskError as exc:
            self._reject_result(task, exc)
            raise
        self._store.save_result(result)
        self._store.update_attempt(task["active_attempt_id"], result_status="accepted")
        run = self._run_store.get_run(run_id)
        if run.current_step != Phase.M_STORY.value:
            error = ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT",
                f"Scribe result requires M-STORY, got {run.current_step}",
            )
            self._reject_result(task, error)
            raise error
        if run.status != "waiting_for_human":
            self._run_store.update_run(
                run.with_status("waiting_for_human"), run.revision
            )
        return _public_result(self._store.get_result(task_id) or result)

    def decide_story(
        self,
        *,
        run_id: str,
        value: str,
        reason: str,
        expected_run_revision: int,
        expected_artifact_revision: int,
        idempotency_key: str,
        actor: str,
        actor_kind: str,
    ) -> dict[str, Any]:
        """Apply the authenticated Human story decision through Runtime authority.

        Args:
            run_id: Runtime run whose current Story is being decided.
            value: One of ``Go``, ``Park`` or ``No-Go``.
            reason: Human explanation for the selected candidate.
            expected_run_revision: Run revision observed by the Human.
            expected_artifact_revision: Story revision observed by the Human.
            idempotency_key: Stable identity for replay-safe submission.
            actor: Server-derived Human principal identity.
            actor_kind: Server-derived principal kind; only ``human`` is valid.

        Returns:
            Persisted decision, updated Runtime status and optional Backlog/
            cleanup evidence. Replaying the same key returns the same decision.

        Raises:
            ScribeTaskError: If the gate is unavailable, stale, unauthorized,
                outside the candidate set, or the request conflicts.

        Side effects:
            Go advances only the Runtime revision while remaining at M-STORY;
            Park/No-Go persist one Backlog identity and enter a terminal
            Runtime state. No M-SPEC task is created.
        """
        if not idempotency_key.strip():
            raise ScribeTaskError("VALIDATION_FAILED", "idempotency_key is required")
        existing = self._store.get_decision(run_id)
        if existing is not None:
            if existing["idempotency_key"] != idempotency_key:
                raise ScribeTaskError(
                    "REQUEST_CONFLICT", "story decision already has another identity"
                )
            return self._decision_response(existing)
        _validate_decision_input(value, reason, actor_kind)
        run, artifact, state, authority = self._authorize_story_decision(
            run_id=run_id,
            expected_run_revision=expected_run_revision,
            expected_artifact_revision=expected_artifact_revision,
        )
        next_run, backlog, cleanup = self._decision_exit(
            run=run,
            artifact=artifact,
            state=state,
            authority=authority,
            value=value,
            reason=reason,
            actor=actor,
            actor_kind=actor_kind,
            expected_run_revision=expected_run_revision,
        )
        decision = {
            "run_id": run_id,
            "story_revision": artifact["revision"],
            "story_digest": artifact["digest"],
            "value": value,
            "reason": reason.strip(),
            "actor": actor,
            "actor_kind": actor_kind,
            "idempotency_key": idempotency_key,
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "backlog": backlog,
            "cleanup": cleanup,
        }
        saved = self._store.save_decision(decision)
        updated_run = self._run_store.update_run(next_run, expected_run_revision)
        return self._decision_response(saved, run=updated_run)

    def story_gate(self, run_id: str) -> dict[str, Any]:
        """Return the persisted Scribe recommendation and Human gate model."""
        task = self._store.get_task_for_run(run_id)
        result = self._store.get_result(task["task_id"]) if task else None
        decision = self._store.get_decision(run_id)
        accepted = result is not None and result["result_status"] == "accepted"
        return {
            "recommendation": result["recommendation"] if accepted else None,
            "reason": result["reason"] if accepted else None,
            "result": _public_result(result) if accepted else None,
            "decision": _public_decision(decision) if decision else None,
            "human_wait": bool(accepted and decision is None),
            "pending_action": "story_decision"
            if accepted and decision is None
            else None,
            "m_spec_task_count": self.m_spec_task_count(run_id),
        }

    def m_spec_task_count(self, run_id: str) -> int:
        """Return the number of persisted M-SPEC tasks for a Runtime run."""
        row = self._store._conn.execute(
            "SELECT COUNT(*) AS count FROM scribe_tasks WHERE run_id = ? AND phase = 'M-SPEC'",
            (run_id,),
        ).fetchone()
        return int(row["count"])

    def _decision_response(
        self, decision: dict[str, Any], *, run: Any | None = None
    ) -> dict[str, Any]:
        """Return one replay-stable Human decision response envelope."""
        current_run = run or self._run_store.get_run(str(decision["run_id"]))
        result = _public_decision(decision)
        result["run"] = {
            "run_id": current_run.run_id,
            "revision": current_run.revision,
            "phase": current_run.current_step,
            "status": current_run.status,
        }
        result["backlog_entry_count"] = 1 if decision.get("backlog") else 0
        return result

    def _authorize_story_decision(
        self,
        *,
        run_id: str,
        expected_run_revision: int,
        expected_artifact_revision: int,
    ) -> tuple[Any, dict[str, Any], RunState, WorkflowAuthority]:
        """Validate current Story/gate identities through phase authority."""
        run = self._run_store.get_run(run_id)
        if run.current_step != Phase.M_STORY.value:
            raise ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT",
                f"story decision requires M-STORY, got {run.current_step}",
            )
        artifact = self._current_artifact(run_id)
        if artifact is None or artifact["revision"] != expected_artifact_revision:
            raise ScribeTaskError(
                "DOCUMENT_WRITE_CONFLICT", "decision targets a stale Story revision"
            )
        gate = self.story_gate(run_id)
        if gate["recommendation"] is None or gate["decision"] is not None:
            raise ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT", "a current Scribe recommendation is required"
            )
        state = RunState(
            run_id=run.run_id,
            phase=Phase.M_STORY,
            revision=run.revision,
            artifact_revision=artifact["revision"],
            allowed_actions=(PhaseAction.STORY_DECISION,),
        )
        authority = WorkflowAuthority()
        try:
            authority.assert_revision_current(state, expected_run_revision)
            authority.assert_action_allowed(state, PhaseAction.STORY_DECISION)
        except WorkflowStateConflict as exc:
            raise ScribeTaskError(exc.code, str(exc)) from exc
        except ActionForbidden as exc:
            raise ScribeTaskError(exc.code, str(exc)) from exc
        return run, artifact, state, authority

    def _decision_exit(
        self,
        *,
        run: Any,
        artifact: dict[str, Any],
        state: RunState,
        authority: WorkflowAuthority,
        value: str,
        reason: str,
        actor: str,
        actor_kind: str,
        expected_run_revision: int,
    ) -> tuple[Any, dict[str, Any] | None, dict[str, Any] | None]:
        """Build the safe Runtime/Backlog outcome for one Human candidate."""
        if value == "Go":
            return run.with_status("running"), None, None
        backlog = _backlog_for_decision(
            run_id=run.run_id,
            story_revision=artifact["revision"],
            story_digest=artifact["digest"],
            value=value,
            reason=reason.strip(),
            actor=actor,
        )
        cleanup = {
            "status": "needs_attention",
            "blocking_reasons": [
                "release branch cleanup safety preconditions were not proven"
            ],
            "permitted_commands": [],
        }
        target = Phase.PARKED if value == "Park" else Phase.NO_GO
        authority.transition(
            state=state,
            target=target,
            expected_revision=expected_run_revision,
            actor_kind=actor_kind,
        )
        status = "parked" if value == "Park" else "no_go"
        return run.with_step(target.value, status), backlog, cleanup

    @property
    def workspace_root(self) -> Path | None:
        """Return the server-owned workspace root used for retry dispatch."""
        return self._workspace_root

    def list_messages(self, run_id: str, task_id: str) -> list[dict[str, Any]]:
        """Return persisted Chat messages after validating task ownership."""
        task = self._require_task(run_id, task_id)
        return self._store.list_messages(task["task_id"])

    def reply(
        self,
        *,
        run_id: str,
        task_id: str,
        client_message_id: str,
        correlation_id: str,
        body: str,
        expected_attempt_id: str,
        expected_artifact_revision: int,
    ) -> dict[str, Any]:
        """Persist and dispatch one Human reply under the active Scribe attempt."""
        task = self._require_task(run_id, task_id)
        existing = self._store.get_message_by_client(client_message_id)
        if existing is not None:
            return _public_message(existing)
        if task["active_attempt_id"] != expected_attempt_id:
            raise ScribeTaskError(
                "TASK_ATTEMPT_CONFLICT",
                "reply does not target the task's active attempt",
            )
        if task["artifact_revision"] != expected_artifact_revision:
            raise ScribeTaskError(
                "DOCUMENT_WRITE_CONFLICT",
                "reply targets a stale Story revision",
            )
        _require_message_fields(client_message_id, correlation_id, body)
        message = self._store.record_message(
            message_id=_stable_id("msg", client_message_id),
            task_id=task_id,
            attempt_id=expected_attempt_id,
            client_message_id=client_message_id,
            correlation_id=correlation_id,
            role="user",
            body=body,
            status="persisted",
        )
        if not task["session_id"]:
            self._store.update_task(task_id, status="blocked", connection="blocked")
            return _public_message(
                self._store.update_message(message["message_id"], status="uncertain")
            )
        try:
            provider_message, _ = self._resolve_adapter().send_message(
                task["session_id"], body, correlation_id=correlation_id
            )
        except Exception as exc:
            self._store.update_message(message["message_id"], status="uncertain")
            self._store.update_task(
                task_id, status="blocked", connection="blocked", last_error=str(exc)
            )
            return _public_message(
                self._store.update_message(message["message_id"], status="uncertain")
            )
        return _public_message(
            self._store.update_message(
                message["message_id"],
                status="dispatched",
                provider_message_id=provider_message.id,
            )
        )

    def reconcile(self, run_id: str, task_id: str) -> dict[str, Any]:
        """Reconcile persisted task state with the existing OpenCode session."""
        task = self._require_task(run_id, task_id)
        if self._store.get_result(task_id) is not None:
            return self._read_task(task)
        if not task["session_id"]:
            return self._read_task(task)
        try:
            adapter = self._resolve_adapter()
            outcome = adapter.reconcile_session(
                task["session_id"], after_result_id=None
            )
            if outcome.status == "completed":
                self._ingest_provider_results(task, outcome.results)
                return self._read_task(self._store.get_task(task_id) or task)
            if outcome.status in {"not_found", "ambiguous"}:
                self._mark_reconciliation_uncertain(task, outcome.error)
                return self._read_task(self._store.get_task(task_id) or task)
            messages = adapter.list_messages(task["session_id"], after_message_id=None)
            for message in messages:
                client_id = f"provider:{message.id}"
                if self._store.get_message_by_client(client_id) is None:
                    self._store.record_message(
                        message_id=_stable_id("msg", client_id),
                        task_id=task_id,
                        attempt_id=task["active_attempt_id"],
                        client_message_id=client_id,
                        correlation_id=f"reconcile:{message.id}",
                        role=message.role,
                        body=message.content,
                        status="dispatched",
                        provider_message_id=message.id,
                    )
            self._store.update_task(
                task_id, status="running", connection="recovered", last_error=None
            )
        except Exception as exc:
            self._store.update_task(
                task_id, status="blocked", connection="blocked", last_error=str(exc)
            )
        return self._read_task(self._store.get_task(task_id) or task)

    def _ingest_provider_results(
        self, task: dict[str, Any], results: list[ProviderResult]
    ) -> None:
        """Validate the latest controlled provider result, if one exists."""
        if not results:
            return
        provider_result = results[-1]
        payload = provider_result.payload
        if payload is None:
            payload = {}
        try:
            self.submit_result(
                run_id=task["run_id"], task_id=task["task_id"], payload=payload
            )
        except ScribeTaskError:
            return

    def _mark_reconciliation_uncertain(
        self, task: dict[str, Any], error: str | None
    ) -> None:
        """Persist fail-closed evidence for a missing or ambiguous session."""
        detail = error or "OpenCode session result could not be confirmed"
        self._store.update_attempt(
            task["active_attempt_id"], status="uncertain", error=detail
        )
        self._store.update_task(
            task["task_id"], status="blocked", connection="blocked", last_error=detail
        )

    def retry(self, run_id: str, task_id: str, workspace: str) -> dict[str, Any]:
        """Create one new attempt for a blocked task and retry real transport."""
        task = self._require_task(run_id, task_id)
        if task["status"] != "blocked":
            return self._read_task(task)
        attempts = self._store.get_attempts(task_id)
        attempt_no = len(attempts) + 1
        attempt_id = _stable_id("attempt", f"{run_id}:{attempt_no}")
        manifest = dict(task["manifest"])
        manifest["attempt_id"] = attempt_id
        manifest["attempt_no"] = attempt_no
        manifest_digest = _digest(json.dumps(manifest, sort_keys=True))
        self._store.create_attempt(
            task=task,
            attempt_id=attempt_id,
            attempt_no=attempt_no,
            manifest=manifest,
            manifest_digest=manifest_digest,
        )
        story = self._run_store._conn.execute(
            "SELECT body_md FROM story_artifacts WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._dispatch(
            task_id=task_id,
            attempt_id=attempt_id,
            manifest=manifest,
            story_body=story["body_md"] if story else "",
            workspace=workspace,
        )

    def has_active_lease(self, run_id: str) -> bool:
        """Return whether the Story remains readonly under a Scribe lease."""
        task = self._store.get_task_for_run(run_id)
        return task is not None and task["status"] in {"pending", "running", "blocked"}

    def _dispatch(
        self,
        *,
        task_id: str,
        attempt_id: str,
        manifest: dict[str, Any],
        story_body: str,
        workspace: str,
    ) -> dict[str, Any]:
        """Create a real session and dispatch the manifest-bound Scribe prompt."""
        try:
            adapter = self._resolve_adapter()
            correlation_id = f"scribe:{task_id}:{attempt_id}"
            instance = adapter.create(correlation_id=correlation_id)
            self._store.update_attempt(
                attempt_id, status="running", session_id=instance.id
            )
            self._store.update_task(
                task_id,
                status="running",
                session_id=instance.id,
                connection="connected",
                last_error=None,
            )
            prompt = _scribe_prompt(manifest, story_body)
            provider_message, _ = adapter.send_message(
                instance.id, prompt, correlation_id=correlation_id
            )
            self._store.update_attempt(attempt_id, dispatch_count=1)
            self._store.record_message(
                message_id=_stable_id("msg", f"dispatch:{attempt_id}"),
                task_id=task_id,
                attempt_id=attempt_id,
                client_message_id=f"dispatch:{attempt_id}",
                correlation_id=correlation_id,
                role="system",
                body=prompt,
                status="dispatched",
                provider_message_id=provider_message.id,
            )
        except Exception as exc:
            self._store.update_attempt(attempt_id, status="uncertain", error=str(exc))
            self._store.update_task(
                task_id, status="blocked", connection="blocked", last_error=str(exc)
            )
        return self._read_task(self._store.get_task(task_id) or {})

    def _resolve_adapter(self) -> OpenCodeAdapter:
        """Resolve the real adapter lazily so unavailable transport is retryable."""
        if self._adapter is not None:
            return self._adapter
        if self._adapter_factory is not None:
            if self._workspace_root is None:
                raise ScribeTaskError(
                    "OPENCODE_UNAVAILABLE", "workspace root is missing"
                )
            self._adapter = self._adapter_factory(self._workspace_root)
            return self._adapter
        from louke.opencode.dispatch import get_default_adapter

        try:
            self._adapter = get_default_adapter(
                kind="real", workspace_root=self._workspace_root
            )
        except Exception as exc:
            raise ScribeTaskError("OPENCODE_UNAVAILABLE", str(exc)) from exc
        return self._adapter

    def _validate_result(
        self, task: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate every persisted identity in a Scribe result payload."""
        required = (
            "role",
            "task_id",
            "attempt_id",
            "session_id",
            "manifest_digest",
            "artifact_revision",
            "artifact_digest",
            "write_scope",
            "recommendation",
            "reason",
        )
        missing = [field for field in required if field not in payload]
        if missing:
            raise ScribeTaskError(
                "VALIDATION_FAILED", f"Scribe result fields are required: {missing}"
            )
        if payload["role"] != "Scribe":
            raise ScribeTaskError("RESULT_ROLE_CONFLICT", "result role is not Scribe")
        if payload["task_id"] != task["task_id"]:
            raise ScribeTaskError("TASK_SCOPE_DENIED", "result task is not bound")
        if payload["attempt_id"] != task["active_attempt_id"]:
            raise ScribeTaskError(
                "RESULT_ATTEMPT_CONFLICT", "result attempt is not active"
            )
        if not task["session_id"] or payload["session_id"] != task["session_id"]:
            raise ScribeTaskError(
                "RESULT_SESSION_CONFLICT", "result session is not the active session"
            )
        if payload["manifest_digest"] != task["manifest_digest"]:
            raise ScribeTaskError(
                "RESULT_MANIFEST_CONFLICT", "result manifest digest is stale"
            )
        artifact = self._current_artifact(task["run_id"])
        if artifact is None:
            raise ScribeTaskError("NOT_FOUND", "current Story artifact does not exist")
        if (
            payload["artifact_revision"] != task["artifact_revision"]
            or payload["artifact_revision"] != artifact["revision"]
            or payload["artifact_digest"] != task["artifact_digest"]
            or payload["artifact_digest"] != artifact["digest"]
        ):
            raise ScribeTaskError(
                "RESULT_ARTIFACT_CONFLICT", "result targets a stale Story artifact"
            )
        if payload["write_scope"] != ["story.md"]:
            raise ScribeTaskError(
                "RESULT_WRITE_SCOPE_DENIED", "Scribe result scope must be story.md only"
            )
        if payload["recommendation"] not in {"Go", "Park", "No-Go"}:
            raise ScribeTaskError(
                "VALIDATION_FAILED", "recommendation must be Go, Park or No-Go"
            )
        if not isinstance(payload["reason"], str) or not payload["reason"].strip():
            raise ScribeTaskError(
                "VALIDATION_FAILED", "recommendation reason is required"
            )
        run = self._run_store.get_run(task["run_id"])
        if run.current_step != Phase.M_STORY.value:
            raise ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT", "Scribe result requires current M-STORY"
            )
        return {
            "task_id": task["task_id"],
            "run_id": task["run_id"],
            "attempt_id": task["active_attempt_id"],
            "session_id": task["session_id"],
            "role": "Scribe",
            "manifest_digest": task["manifest_digest"],
            "artifact_revision": artifact["revision"],
            "artifact_digest": artifact["digest"],
            "write_scope": ["story.md"],
            "recommendation": payload["recommendation"],
            "reason": payload["reason"].strip(),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def _reject_result(self, task: dict[str, Any], error: ScribeTaskError) -> None:
        """Persist rejected-result evidence without mutating Runtime state."""
        self._store.update_attempt(
            task["active_attempt_id"],
            result_status="rejected",
            error=f"{error.code}: {error.message}",
        )

    def _current_artifact(self, run_id: str) -> dict[str, Any] | None:
        """Read the current Story identity from Runtime persistence."""
        row = self._store._conn.execute(
            "SELECT revision, digest FROM story_artifacts WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _require_task(self, run_id: str, task_id: str) -> dict[str, Any]:
        """Validate that a task belongs to the requested Runtime run."""
        task = self._store.get_task(task_id)
        if task is None or task["run_id"] != run_id:
            raise ScribeTaskError("TASK_SCOPE_DENIED", "task is not bound to this run")
        return task

    def _read_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Build the public IF-API-08 task read model."""
        attempts = self._store.get_attempts(task["task_id"])
        active = next(
            (
                attempt
                for attempt in attempts
                if attempt["attempt_id"] == task["active_attempt_id"]
            ),
            None,
        )
        allowed = (
            ["retry", "reconcile"] if task["status"] == "blocked" else ["reconcile"]
        )
        result = self._store.get_result(task["task_id"])
        if result is None and active and active.get("result_status") == "rejected":
            result = {
                "status": "rejected",
                "reason": active.get("error"),
            }
        return {
            "task_id": task["task_id"],
            "run_id": task["run_id"],
            "phase": task["phase"],
            "role": task["role"],
            "artifact": {
                "kind": "story",
                "revision": task["artifact_revision"],
                "digest": task["artifact_digest"],
            },
            "write_scope": json.loads(task["write_scope_json"]),
            "output_contract_digest": task["output_contract_digest"],
            "status": task["status"],
            "connection": task["connection"],
            "session_id": task["session_id"],
            "lease_id": task["lease_id"],
            "manifest": task["manifest"],
            "manifest_digest": task["manifest_digest"],
            "attempts": attempts,
            "active_attempt": active,
            "last_error": task["last_error"],
            "allowed_actions": allowed,
            "result": _public_result(result) if result else None,
        }


def _build_manifest(
    *,
    run: Any,
    artifact: Any,
    task_id: str,
    attempt_id: str,
    human_request: str,
    foundation_manifest_identity: str,
) -> tuple[dict[str, Any], str]:
    """Build the combined public Scribe and generic task manifests."""
    if not foundation_manifest_identity:
        raise ScribeTaskError(
            "FOUNDATION_MANIFEST_REQUIRED", "Foundation identity is required"
        )
    prompt_bundle = _digest("v0.14-scribe-story-prompt-v1")
    generic = build_manifest(
        run_id=run.run_id,
        task_id=task_id,
        attempt_no=1,
        graph_revision=run.contract_digest,
        baseline_commit=artifact.commit_sha,
        issue_id=-1,
        fr_ids=("FR-0700",),
        nfr_ids=(),
        ac_ids=("AC-FR0700-01", "AC-FR0700-02", "AC-FR0700-03"),
        design_refs=("IF-API-08", "IF-WEB-05"),
        phase="final",
        write_scopes=("story.md",),
        forbidden_scopes=("spec.md", "acceptance.md"),
        test_commands={"final": "Runtime format validation"},
        prompt_bundle=prompt_bundle,
        schema_refs=("IF-API-08",),
        output_contract="scribe.story.v1",
        deadline=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        retry_policy={"max_attempts": 3, "on_session_loss": "reconcile"},
    )
    scribe = dispatch_scribe_investigation(
        run_id=run.run_id,
        story_revision=artifact.revision,
        story_digest=artifact.digest,
        story_template_path="louke/templates/story.md",
        story_template_digest=_digest("louke/templates/story.md:v1"),
        human_request=human_request,
        foundation_manifest_identity=foundation_manifest_identity,
        spec_id=artifact.spec_id,
        attempt_id=attempt_id,
    )
    manifest = {
        "run_id": run.run_id,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "attempt_no": 1,
        "phase": "M-STORY",
        "role": "Scribe",
        "artifact": {
            "kind": "story",
            "revision": artifact.revision,
            "digest": artifact.digest,
            "input_digest": artifact.input_digest,
        },
        "human_request": human_request,
        "foundation_manifest_identity": foundation_manifest_identity,
        "write_scope": list(scribe.write_scope),
        "task_manifest": asdict(generic),
        "output_contract": "scribe.story.v1",
    }
    return manifest, _digest(json.dumps(manifest, sort_keys=True))


def _decode_task(row: sqlite3.Row) -> dict[str, Any]:
    """Decode structured task columns from SQLite."""
    result = dict(row)
    result["manifest"] = json.loads(result.pop("manifest_json"))
    return result


def _require_message_fields(client_id: str, correlation_id: str, body: str) -> None:
    """Validate Human message identity and bounded content."""
    if not client_id.strip() or not correlation_id.strip():
        raise ScribeTaskError("VALIDATION_FAILED", "message identities are required")
    if not isinstance(body, str) or not body.strip() or len(body) > 20000:
        raise ScribeTaskError(
            "VALIDATION_FAILED", "message body must be 1..20000 characters"
        )


def _validate_decision_input(value: str, reason: str, actor_kind: str) -> None:
    """Validate Human gate fields before reading or mutating Runtime state."""
    if actor_kind != "human":
        raise ScribeTaskError(
            "HUMAN_AUTHORITY_REQUIRED",
            "Agent/anonymous actors cannot decide Go/Park/No-Go",
        )
    if value not in {"Go", "Park", "No-Go"}:
        raise ScribeTaskError(
            "VALIDATION_FAILED", "story decision must be Go, Park or No-Go"
        )
    if not reason.strip():
        raise ScribeTaskError("VALIDATION_FAILED", "decision reason is required")


def _public_message(message: dict[str, Any]) -> dict[str, Any]:
    """Return the public IF-API-08 message envelope."""
    return {
        "message_id": message["message_id"],
        "status": message["status"],
        "event_sequences": {"persisted": message["message_id"]},
        "provider_message_id": message.get("provider_message_id"),
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return the non-secret Scribe result envelope."""
    return {
        "status": result.get("result_status", result.get("status")),
        "recommendation": result.get("recommendation"),
        "reason": result.get("reason"),
        "task_id": result.get("task_id"),
        "attempt_id": result.get("attempt_id"),
        "session_id": result.get("session_id"),
        "manifest_digest": result.get("manifest_digest"),
        "artifact_revision": result.get("artifact_revision"),
        "artifact_digest": result.get("artifact_digest"),
        "write_scope": result.get("write_scope"),
        "received_at": result.get("received_at"),
    }


def _public_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted Human decision and exit evidence."""
    return {
        "run_id": decision.get("run_id"),
        "story_revision": decision.get("story_revision"),
        "story_digest": decision.get("story_digest"),
        "value": decision.get("value"),
        "reason": decision.get("reason"),
        "actor": decision.get("actor"),
        "decided_at": decision.get("decided_at"),
        "backlog": decision.get("backlog"),
        "cleanup": decision.get("cleanup"),
        "idempotency_key": decision.get("idempotency_key"),
    }


def _backlog_for_decision(
    *,
    run_id: str,
    story_revision: int,
    story_digest: str,
    value: str,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    """Build one stable canonical Backlog identity for Park/No-Go."""
    identity = f"{run_id}|{value}"
    entry_id = f"bl_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
    return {
        "entry_id": entry_id,
        "run_id": run_id,
        "source_run": run_id,
        "story_revision": story_revision,
        "story_digest": story_digest,
        "decision": value,
        "reason": reason,
        "actor": actor,
    }


def _scribe_prompt(manifest: dict[str, Any], story_body: str) -> str:
    """Build the non-secret initial Scribe prompt from persisted task facts."""
    return (
        "You are the Scribe for the bound M-STORY task. Do not decide for Human, "
        "do not write outside story.md. After your work, return exactly one JSON "
        "object matching the scribe.story.v1 contract; do not wrap it in Markdown. "
        "The object must include role, task_id, attempt_id, session_id, "
        "manifest_digest, artifact_revision, artifact_digest, write_scope, "
        "recommendation and reason. recommendation is only a suggestion to Human.\n\n"
        f"Task manifest:\n{json.dumps(manifest, sort_keys=True, ensure_ascii=False)}\n\n"
        f"Current story.md:\n{story_body}"
    )


def _stable_id(prefix: str, value: str) -> str:
    """Return a deterministic opaque identifier for a persisted identity."""
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _digest(value: str) -> str:
    """Return a sha256 identity digest for non-secret contract data."""
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
