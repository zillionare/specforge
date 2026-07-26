"""Runtime-owned Project preview, confirmation, and status service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from pathlib import Path

from louke.runtime.catalog import DefinitionNotFoundError, WorkflowDefinition
from louke.runtime.release_request import _canonical_release_version
from louke.runtime.store import RunNotFoundError, WorkflowRunStore
from louke.runtime.release_request import preview_release_request
from louke.runtime.story_entry import StoryEntryService


class StalePreviewError(ValueError):
    """Raised when confirmation does not match the persisted preview revision."""


class ReleaseRequestConflictError(ValueError):
    """Raised when a request is replayed with a different idempotency key."""


@dataclass(frozen=True)
class MainCheck:
    """Public main-preflight evidence returned by a Foundation adapter."""

    status: str
    remote_main: dict[str, str]
    previous_branch: dict[str, str]
    remediation: str
    local_main: dict[str, str] | None = None
    checked_at: str = ""


@dataclass(frozen=True)
class FoundationOutcome:
    """Public Foundation reconciliation result and stable resource identities."""

    status: str
    resources: dict[str, Any]
    remediation: str


class FoundationAdapter(Protocol):
    """Port for real Git/GitHub Foundation orchestration."""

    def preflight(self, story: str, release_version: str) -> MainCheck:
        """Refresh and inspect Git/GitHub main state without creating release resources."""

    def provision(
        self,
        story: str,
        release_version: str,
        run_id: str,
        main_check: MainCheck,
        spec_id: str,
    ) -> FoundationOutcome:
        """Query/reconcile Foundation resources and report uncertain effects explicitly."""


class ReleaseRequestStore:
    """SQLite persistence for v0.14 preview and confirmation identities."""

    _ACTIVE_STATUSES = (
        "preflight",
        "foundation",
        "ready",
        "blocked",
        "conflict",
    )

    def __init__(self, run_store: WorkflowRunStore) -> None:
        self._run_store = run_store
        self._conn = run_store._conn
        self._lock = threading.RLock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS release_requests (
                request_id TEXT PRIMARY KEY,
                preview_id TEXT NOT NULL UNIQUE,
                workspace_id TEXT NOT NULL,
                request_digest TEXT NOT NULL UNIQUE,
                 preview_revision INTEGER NOT NULL,
                 revision INTEGER NOT NULL DEFAULT 0,
                story TEXT NOT NULL,
                release_version TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT,
                actor TEXT,
                main_check TEXT,
                foundation TEXT,
                backlog TEXT,
                project_id TEXT,
                run_id TEXT,
                spec_id TEXT UNIQUE,
                readiness_identity TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(release_requests)")
        }
        if "spec_id" not in columns:
            self._conn.execute("ALTER TABLE release_requests ADD COLUMN spec_id TEXT")
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS release_requests_spec_id_unique "
                "ON release_requests(spec_id)"
            )
        if "readiness_identity" not in columns:
            self._conn.execute(
                "ALTER TABLE release_requests ADD COLUMN readiness_identity TEXT"
            )
        self._conn.commit()

    def create_preview(
        self,
        workspace_id: str,
        story: str,
        release_version: str,
        digest: str,
        readiness_identity: dict[str, str],
    ) -> dict[str, Any]:
        """Persist or reuse a preview keyed by workspace and request digest."""
        now = _now()
        request_id = f"req_{digest[7:31]}"
        preview_id = f"prev_{digest[7:31]}"
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO release_requests
                (request_id, preview_id, workspace_id, request_digest,
                 preview_revision, story, release_version, readiness_identity, status, created_at,
                 updated_at)
                 VALUES (?, ?, ?, ?, 0, ?, ?, ?, 'preview', ?, ?)
                """,
                (
                    request_id,
                    preview_id,
                    workspace_id,
                    digest,
                    story,
                    release_version,
                    _identity_json(readiness_identity),
                    now,
                    now,
                ),
            )
            record = self.get(request_id)
        return record

    def claim(
        self,
        request_id: str,
        expected_revision: int,
        request_digest: str,
        idempotency_key: str,
        actor: str,
        spec_id: str,
    ) -> dict[str, Any]:
        """Atomically validate a preview and claim confirmation or backlog it."""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            record = self.get(request_id)
            _assert_preview(record, expected_revision, request_digest)
            if record["status"] != "preview":
                if (
                    record.get("idempotency_key") != idempotency_key
                    or record.get("actor") != actor
                ):
                    raise ReleaseRequestConflictError(
                        "request already confirmed with another idempotency key"
                    )
                return record
            if self._has_active_release(record["request_id"]):
                backlog = {
                    "entry_id": f"bl_{request_digest[7:31]}",
                    "story": record["story"],
                    "release_version": record["release_version"],
                    "reason": "an active main release already exists",
                    "created_at": _now(),
                    "source_identity": {
                        "workspace_id": record["workspace_id"],
                        "request_digest": request_digest,
                    },
                }
                self._update(
                    request_id,
                    status="backlogged",
                    idempotency_key=idempotency_key,
                    actor=actor,
                    backlog=backlog,
                )
                return self.get(request_id)
            self._update(
                request_id,
                status="preflight",
                idempotency_key=idempotency_key,
                actor=actor,
                spec_id=spec_id,
            )
            return self.get(request_id)

    def update(self, request_id: str, **fields: Any) -> dict[str, Any]:
        """Persist a status read-model update and return the current record."""
        with self._lock, self._conn:
            self._update(request_id, **fields)
            return self.get(request_id)

    def get(self, request_id: str) -> dict[str, Any]:
        """Return one persisted request or raise ``KeyError``."""
        row = self._conn.execute(
            "SELECT * FROM release_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"release request {request_id!r} not found")
        record = dict(row)
        for field in ("main_check", "foundation", "backlog"):
            record[field] = json.loads(record[field]) if record[field] else None
        record["readiness_identity"] = (
            json.loads(record["readiness_identity"])
            if record.get("readiness_identity")
            else {}
        )
        return record

    def get_by_project(self, project_id: str) -> dict[str, Any] | None:
        """Return the exact persisted release request for one project identity."""
        row = self._conn.execute(
            "SELECT request_id FROM release_requests WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return self.get(str(row["request_id"])) if row is not None else None

    def get_by_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the exact persisted release request for one Runtime run."""
        row = self._conn.execute(
            "SELECT request_id FROM release_requests WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return self.get(str(row["request_id"])) if row is not None else None

    def reserved_spec_ids(self) -> set[str]:
        """Return every durable target-spec identity reserved by a request."""
        rows = self._conn.execute(
            "SELECT spec_id FROM release_requests WHERE spec_id IS NOT NULL"
        ).fetchall()
        return {str(row["spec_id"]) for row in rows}

    def _has_active_release(self, request_id: str) -> bool:
        placeholders = ",".join("?" for _ in self._ACTIVE_STATUSES)
        row = self._conn.execute(
            f"SELECT 1 FROM release_requests WHERE request_id != ? "
            f"AND status IN ({placeholders}) LIMIT 1",
            (request_id, *self._ACTIVE_STATUSES),
        ).fetchone()
        return row is not None

    def _update(self, request_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "idempotency_key",
            "actor",
            "main_check",
            "foundation",
            "backlog",
            "project_id",
            "run_id",
            "spec_id",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported release request fields: {sorted(unknown)}")
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(_serialize_field(key, value))
        assignments.append("updated_at = ?")
        values.append(_now())
        assignments.append("revision = revision + 1")
        values.append(request_id)
        self._conn.execute(
            f"UPDATE release_requests SET {', '.join(assignments)} WHERE request_id = ?",
            values,
        )


class ReleaseEntryService:
    """Coordinate v0.14 public release APIs through Runtime persistence."""

    def __init__(
        self,
        run_store: WorkflowRunStore,
        foundation: FoundationAdapter,
        *,
        workspace_id: str,
        definition_id: str = "new_feature",
        definition_version: str = "0.14.0",
        story_entry: StoryEntryService | None = None,
        workspace_root: str | Path | None = None,
    ) -> None:
        self._run_store = run_store
        self._foundation = foundation
        self._workspace_id = workspace_id
        self._definition_id = definition_id
        self._definition_version = definition_version
        self._story_entry = story_entry
        self._workspace_root = (
            Path(workspace_root).resolve() if workspace_root else None
        )
        self._requests = ReleaseRequestStore(run_store)

    def preview(
        self,
        story: str,
        release_version: str,
        readiness_identity: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate and persist a side-effect-free release preview read model."""
        preview = preview_release_request(
            workspace_id=self._workspace_id,
            story=story,
            release_version=release_version,
            active_main_release_present=False,
        )
        identity = dict(readiness_identity or {})
        digest = _preview_digest(preview.request_digest, identity)
        record = self._requests.create_preview(
            self._workspace_id,
            preview.story,
            preview.release_version,
            digest,
            identity,
        )
        return {
            "preview_id": record["preview_id"],
            "preview_revision": record["preview_revision"],
            "request_id": record["request_id"],
            "request_digest": record["request_digest"],
            "workspace_id": self._workspace_id,
            "workspace": {"workspace_id": self._workspace_id},
            "story": record["story"],
            "release": self._release_identity(record["release_version"]),
            "side_effects": [],
            "actions": {"create": True, "cancel": True},
        }

    def confirm(
        self,
        preview_id: str,
        *,
        expected_preview_revision: int,
        request_digest: str,
        idempotency_key: str,
        actor: str,
        readiness_identity: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Confirm a preview, run real Foundation checks, and persist recovery state."""
        request_id = self._request_id_for_preview(preview_id)
        record = self._requests.get(request_id)
        if dict(readiness_identity or {}) != record["readiness_identity"]:
            raise StalePreviewError(
                "repository identity or authoritative main changed; refresh the preview"
            )
        spec_id = str(record.get("spec_id") or "")
        if not spec_id:
            spec_id = self._allocate_spec_identity(
                record["release_version"], record["story"]
            )
        record = self._requests.claim(
            request_id,
            expected_preview_revision,
            request_digest,
            idempotency_key,
            actor,
            spec_id,
        )
        if record["status"] != "preflight":
            return self._read_model(record)
        return self._run_preflight(record)

    def replay_ready(
        self,
        preview_id: str,
        *,
        expected_preview_revision: int,
        request_digest: str,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, Any] | None:
        """Return an exact terminal-ready Confirm replay without new readiness work."""
        record = self._requests.get(self._request_id_for_preview(preview_id))
        _assert_preview(record, expected_preview_revision, request_digest)
        if record["status"] != "ready":
            return None
        if (
            record.get("idempotency_key") != idempotency_key
            or record.get("actor") != actor
        ):
            raise ReleaseRequestConflictError(
                "request already confirmed with another idempotency key or actor"
            )
        return self._read_model(record)

    def recheck(
        self, request_id: str, *, actor: str, expected_revision: int | None = None
    ) -> dict[str, Any]:
        """Re-run a blocked or uncertain Foundation request without bypassing checks."""
        record = self._requests.get(request_id)
        if (
            expected_revision is not None
            and record.get("revision") != expected_revision
        ):
            raise StalePreviewError("ProjectCreation revision is stale")
        if record["status"] not in {"blocked", "conflict"}:
            return self._read_model(record)
        self._requests.update(request_id, status="preflight", actor=actor)
        return self._run_preflight(self._requests.get(request_id))

    def status(self, request_id: str) -> dict[str, Any]:
        """Return the persisted public status read model for a release request."""
        return self._read_model(self._requests.get(request_id))

    def current_project(self, project_id: str) -> dict[str, Any] | None:
        """Return the exact release/run binding for a project path identity."""
        record = self._requests.get_by_project(project_id)
        return self._read_model(record) if record is not None else None

    def project_for_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the exact project binding for one Runtime run identity."""
        record = self._requests.get_by_run(run_id)
        return (
            {"project_id": record["project_id"], "run_id": record["run_id"]}
            if record is not None and record.get("project_id")
            else None
        )

    def _run_preflight(self, record: dict[str, Any]) -> dict[str, Any]:
        check = self._foundation.preflight(record["story"], record["release_version"])
        self._requests.update(record["request_id"], main_check=check)
        if check.status != "pass":
            return self._read_model(
                self._requests.update(record["request_id"], status="blocked")
            )
        run_id = record["run_id"] or self._create_run().run_id
        project_id = (
            f"prj_{hashlib.sha256(record['request_id'].encode()).hexdigest()[:12]}"
        )
        record = self._requests.update(
            record["request_id"],
            status="foundation",
            project_id=project_id,
            run_id=run_id,
        )
        outcome = self._foundation.provision(
            record["story"], record["release_version"], run_id, check, record["spec_id"]
        )
        resources = dict(outcome.resources)
        resources.setdefault("local_project", {"id": project_id})
        resources.setdefault("workflow_run", {"id": run_id})
        outcome = FoundationOutcome(outcome.status, resources, outcome.remediation)
        if outcome.status != "ready":
            self._mark_run_foundation_pending(run_id)
        else:
            self._activate_run_after_foundation(run_id)
        if outcome.status == "ready" and self._story_entry is not None:
            try:
                story = self._initialize_story(record, resources)
            except Exception as exc:
                outcome = FoundationOutcome(
                    "conflict",
                    resources,
                    f"initial Story reconciliation failed: {exc}",
                )
            else:
                resources["story"] = story
                outcome = FoundationOutcome(
                    outcome.status, resources, outcome.remediation
                )
        status = (
            "ready"
            if outcome.status == "ready"
            else "conflict"
            if outcome.status == "conflict"
            else "blocked"
        )
        completed = self._requests.update(
            record["request_id"],
            status=status,
            foundation=outcome,
            project_id=project_id,
        )
        if status == "ready":
            self._persist_active_project_context(completed)
        return self._read_model(completed)

    def _create_run(self):
        definition = self._definition()
        return self._run_store.create_run(definition)

    def _persist_active_project_context(self, record: dict[str, Any]) -> None:
        """Atomically publish a ready Project identity chain for Web read models.

        Args:
            record: Persisted ready release-request record with Foundation and
                Story evidence.

        Side Effects:
            Replaces ``.louke/project-state.json`` when this service is bound
            to a workspace root.
        """
        if self._workspace_root is None:
            return
        foundation = record.get("foundation") or {}
        resources = foundation.get("resources") or {}
        github_project = resources.get("github_project") or {}
        story = _story_from_foundation(foundation) or {}
        state_path = self._workspace_root / ".louke" / "project-state.json"
        previous = _read_project_context_state(state_path)
        project = {
            "project_id": record["project_id"],
            "request_id": record["request_id"],
            "run_id": record["run_id"],
            "release_version": record["release_version"],
            "spec_id": record["spec_id"],
            "github_project_node_id": github_project.get("node_id"),
            "story_revision": story.get("revision"),
        }
        payload = {
            "state": "active",
            "revision": int(previous.get("revision", 0)) + 1,
            "project_id": record["project_id"],
            "spec_id": record["spec_id"],
            "project": project,
            "conflicts": [],
        }
        _atomic_json_write(state_path, payload)

    def _mark_run_foundation_pending(self, run_id: str) -> None:
        """Keep a failed Foundation run non-active until reconciliation succeeds."""
        run = self._run_store.get_run(run_id)
        if run.status == "foundation_pending":
            return
        self._run_store.update_run(
            run.with_step(self._definition().start_step, "foundation_pending"),
            run.revision,
        )

    def _activate_run_after_foundation(self, run_id: str) -> None:
        """Restore the normal Runtime status after Foundation succeeds."""
        run = self._run_store.get_run(run_id)
        if run.status == "foundation_pending":
            self._run_store.update_run(
                run.with_step(self._definition().start_step, "waiting_human"),
                run.revision,
            )

    def _definition(self) -> WorkflowDefinition:
        """Resolve the immutable entry definition from the Runtime catalog."""
        catalog = self._run_store._catalog
        if catalog is None:
            raise DefinitionNotFoundError("Runtime catalog is not configured")
        try:
            return catalog.get(self._definition_id, self._definition_version)
        except DefinitionNotFoundError:
            if self._definition_id != "new_feature":
                raise
            return catalog.get("project_entry", "1")

    def _request_id_for_preview(self, preview_id: str) -> str:
        """Resolve the persisted request id for an opaque preview id."""
        digest = preview_id.removeprefix("prev_")
        return f"req_{digest}"

    def _release_identity(self, version: str) -> dict[str, str]:
        """Return the non-secret release identity displayed by preview.

        Per interfaces §IF-PREVIEW-01, the ``canonical`` form is the
        3-segment PEP440 version padded from the input (``0.14`` ->
        ``0.14.0``); the ``tag`` carries a single leading ``v``; the
        ``branch`` is ``releases/<canonical>``.
        """
        canonical = _canonical_release_version(version) or version.removeprefix("v")
        return {
            "external": version,
            "canonical": canonical,
            "tag": f"v{canonical}",
            "branch": f"releases/{canonical}",
        }

    def _read_model(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert a persisted request record into IF-API-03 response fields."""
        foundation = record["foundation"]
        resources = (foundation or {}).get("resources") or {}
        try:
            run = (
                self._run_store.get_run(record["run_id"]) if record["run_id"] else None
            )
        except RunNotFoundError:
            run = None
        project = (
            {
                "project_id": record["project_id"],
                "release_version": record["release_version"],
                "spec_id": record["spec_id"],
                "github_project_node_id": (resources.get("github_project") or {}).get(
                    "node_id"
                ),
            }
            if record["project_id"]
            else None
        )
        return {
            "request_id": record["request_id"],
            "revision": int(record.get("revision", 0)),
            "state": record["status"],
            "project_id": record["project_id"],
            "spec_id": record["spec_id"],
            "project": project,
            "status": record["status"],
            "backlog": record["backlog"],
            "main_check": record["main_check"],
            "foundation": foundation,
            "story": _story_from_foundation(foundation),
            "run_id": record["run_id"],
            "run": (
                {
                    "run_id": run.run_id,
                    "current_step": run.current_step,
                    "runtime_revision": run.revision,
                }
                if run is not None
                else None
            ),
            "primary_action": _primary_action(record["status"]),
            "continue_url": (
                f"/projects/{record['project_id']}/requirements/story"
                if record["project_id"]
                else None
            ),
        }

    def _allocate_spec_identity(self, release_version: str, story: str) -> str:
        """Reserve the next stable release-series spec identity for a Story."""
        canonical = _canonical_release_version(release_version) or release_version
        parts = canonical.removeprefix("v").split(".")
        if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
            raise ValueError("release version cannot form a target spec identity")
        prefix = f"v{parts[0]}.{parts[1]}-"
        reserved = self._requests.reserved_spec_ids()
        names = set(reserved)
        if self._workspace_root is not None:
            specs = self._workspace_root / ".louke" / "project" / "specs"
            if specs.is_dir():
                names.update(path.name for path in specs.iterdir() if path.is_dir())
        sequence = (
            max(
                (
                    int(match.group(1))
                    for name in names
                    if (
                        match := re.fullmatch(
                            rf"{re.escape(prefix)}(\d{{3,}})-.+", name
                        )
                    )
                ),
                default=0,
            )
            + 1
        )
        slug = re.sub(r"[^a-z0-9]+", "-", story.lower()).strip("-")[:72]
        return f"{prefix}{sequence:03d}-{slug or 'project'}"

    def _initialize_story(
        self, record: dict[str, Any], resources: dict[str, Any]
    ) -> dict[str, Any]:
        """Create the initial Story through the Runtime program-step service."""
        spec_path = str(resources.get("spec_directory", {}).get("path") or "")
        spec_id = spec_path.rsplit("/", 1)[-1]
        if not spec_id:
            raise ValueError("Foundation ready evidence has no spec directory identity")
        result = self._story_entry.initialize(
            run_id=str(record["run_id"]),
            workspace=str(resources.get("worktree", {}).get("path") or ""),
            spec_id=spec_id,
            human_story=str(record["story"]),
            actor=str(record.get("actor") or "human"),
            idempotency_key=f"story-init:{record['request_id']}",
            foundation_manifest_identity=_foundation_identity(resources),
        )
        return {
            "path": result.artifact.path,
            "revision": result.artifact.revision,
            "digest": result.artifact.digest,
            "input_digest": result.artifact.input_digest,
            "actor": result.artifact.actor,
            "commit_sha": result.artifact.commit_sha,
            "phase": result.run.current_step,
            "run_id": result.run.run_id,
            "task": result.task,
        }


def _assert_preview(record: dict[str, Any], revision: int, digest: str) -> None:
    """Reject stale preview revisions or mismatched request digests."""
    if record["preview_revision"] != revision or record["request_digest"] != digest:
        raise StalePreviewError(
            "preview revision or request digest is stale; refresh the release preview"
        )


def _identity_json(identity: dict[str, str]) -> str:
    """Serialize a terminal readiness identity in deterministic key order."""
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def _preview_digest(request_digest: str, readiness_identity: dict[str, str]) -> str:
    """Bind the request digest to the exact terminal facts shown in Preview."""
    payload = json.dumps(
        {"request_digest": request_digest, "readiness_identity": readiness_identity},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _story_from_foundation(foundation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read Story evidence from the persisted Foundation resource bundle."""
    if not foundation:
        return None
    resources = foundation.get("resources") or {}
    story = resources.get("story")
    return dict(story) if isinstance(story, dict) else None


def _foundation_identity(resources: dict[str, Any]) -> str:
    """Return a stable non-secret identity for the confirmed Foundation set."""
    payload = json.dumps(resources, sort_keys=True, separators=(",", ":"))
    return f"foundation:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _primary_action(status: str) -> str | None:
    """Return the single recovery action appropriate to a creation state."""
    if status in {"blocked", "conflict", "uncertain"}:
        return "retry"
    if status in {"foundation", "scribe", "preflight"}:
        return "refresh"
    return None


def _serialize_field(field: str, value: Any) -> Any:
    """Serialize structured request fields while preserving scalar columns."""
    if value is None or field not in {"main_check", "foundation", "backlog"}:
        return value
    if field in {"main_check", "foundation"}:
        value = asdict(value)
    return json.dumps(value, sort_keys=True)


def _read_project_context_state(path: Path) -> dict[str, Any]:
    """Read a Project context payload or return an empty safe baseline."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace one JSON projection without leaving a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


def _now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()
