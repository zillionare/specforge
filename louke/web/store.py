from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .._common import _toml_load
from ..models import SCHEMA as MODELS_SCHEMA


_RE_SPEC_VERSION = re.compile(r"^v(\d+)\.(\d+)(?:-(\d+))?")


def _password_hash(password: str) -> str:
    """Return a salted scrypt verifier without retaining the credential."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    """Return whether a credential matches a stored scrypt verifier."""
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1
        )
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def _spec_version_key(spec_id: str) -> tuple[int, int, int, str]:
    """Parse a spec id like 'v0.10-001-foo' into a sortable key.

    Returns (major, minor, patch, suffix) so 'v0.10' > 'v0.9' > 'v0.8'.
    Specs without a parseable version get a -1 sentinel so they sort last.
    """
    m = _RE_SPEC_VERSION.match(spec_id)
    if not m:
        return (-1, -1, -1, spec_id)
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    return (major, minor, patch, spec_id)


def _pick_highest_version_spec(spec_ids: list[str]) -> str:
    if not spec_ids:
        return ""
    return max(spec_ids, key=_spec_version_key)


from ..models import config_path, load_config  # noqa: E402


DOC_NAME_TO_FILE = {
    "story": "story.md",
    "spec": "spec.md",
    "acceptance": "acceptance.md",
    "test-plan": "test-plan.md",
    "architecture": "architecture.md",
    "interfaces": "interfaces.md",
    "gap-analysis": "gap-analysis.md",
    "m-lock": "m-lock.md",
}
WRITABLE_DOC_NAMES = frozenset({"story", "spec", "acceptance"})
MAX_DOC_BYTES = 1024 * 1024


class ConflictError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


@dataclass
class ResourceMetadata:
    updated_at: str
    last_modified_by: str


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.louke_dir = self.root / ".louke"
        self.project_dir = self.root / ".louke" / "project"
        self.specs_dir = self.project_dir / "specs"
        self.wiki_dir = self.root / ".louke" / "wiki"
        self.wiki_pages_dir = self.wiki_dir / "pages"
        self.activity_path = self.project_dir / ".serve-activity.jsonl"
        self.project_info_path = self.project_dir / "project.toml"
        self.users_path = self.louke_dir / "web-users.json"
        if not self.project_info_path.exists():
            raise FileNotFoundError(f"missing {self.project_info_path}")

    @property
    def spec_id(self) -> str:
        return str((self.project_info().get("project") or {}).get("spec_id") or "")

    def project_info(self) -> dict[str, Any]:
        return _toml_load(self.project_info_path)

    def health_payload(self) -> dict[str, str]:
        return {"status": "ok", "spec_id": self.spec_id}

    def list_users(self) -> list[dict[str, str]]:
        payload = self._read_users_payload()
        users = payload.get("users")
        if not isinstance(users, list):
            return []
        result: list[dict[str, str]] = []
        for item in users:
            if not isinstance(item, dict):
                continue
            username = str(item.get("username") or "").strip()
            password_hash = str(item.get("password_hash") or "")
            legacy_password = str(item.get("password") or "")
            if not username:
                continue
            result.append(
                {
                    "username": username,
                    "password_hash": password_hash,
                    "legacy_password": legacy_password,
                }
            )
        return result

    def user_exists(self, username: str) -> bool:
        return any(user["username"] == username for user in self.list_users())

    def create_user(self, username: str, password: str) -> None:
        if self.user_exists(username):
            raise ValidationError("username already exists")
        users = self.list_users()
        users.append({"username": username, "password_hash": _password_hash(password)})
        payload = {"version": 1, "users": users}
        self._atomic_write_text(self.users_path, self._stable_json(payload) + "\n")

    def verify_user(self, username: str, password: str) -> bool:
        for user in self.list_users():
            if user["username"] != username:
                continue
            password_hash = user.get("password_hash", "")
            if password_hash and _password_matches(password, password_hash):
                return True
            if not password_hash and hmac.compare_digest(
                user.get("legacy_password", ""), password
            ):
                return True
        return False

    def list_spec_documents(self, spec_id: str | None = None) -> list[dict[str, str]]:
        target_spec_id = spec_id or self.spec_id
        items: list[dict[str, str]] = []
        for doc_name, file_name in DOC_NAME_TO_FILE.items():
            path = self.specs_dir / target_spec_id / file_name
            if not path.exists():
                continue
            metadata = self._metadata_for(path)
            items.append(
                {
                    "spec_id": target_spec_id,
                    "doc_name": doc_name,
                    "path": self.relative_path(path),
                    "updated_at": metadata.updated_at,
                    "last_modified_by": metadata.last_modified_by,
                }
            )
        return items

    def list_spec_ids(self) -> list[str]:
        """List all spec directory names under .louke/project/specs/."""
        if not self.specs_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.specs_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def resolve_spec_id(self) -> str:
        """Return the spec ID to use, with auto-select fallback.

        Priority:
        1. The configured spec_id from project.toml, if it exists on disk.
        2. The spec with the highest version number, if any specs exist.
        3. Empty string if no specs.
        """
        available = self.list_spec_ids()
        if not available:
            return ""
        configured = self.spec_id
        if configured and configured in available:
            return configured
        return _pick_highest_version_spec(available)

    def doc_path(self, spec_id: str, doc_name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec_id):
            raise ValidationError(f"unsupported spec id: {spec_id}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", doc_name):
            raise ValidationError(f"unsupported document name: {doc_name}")
        path = (
            self.specs_dir / spec_id / DOC_NAME_TO_FILE.get(doc_name, f"{doc_name}.md")
        )
        try:
            path.resolve().relative_to(self.specs_dir.resolve())
        except ValueError as exc:
            raise ValidationError("document path is outside the specs root") from exc
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def wiki_page_path(self, page: str) -> Path:
        page_name = self._normalize_page_name(page)
        return self.wiki_pages_dir / f"{page_name}.md"

    def read_doc(
        self, spec_id: str, doc_name: str
    ) -> tuple[str, str, ResourceMetadata]:
        path = self.doc_path(spec_id, doc_name)
        body_md = path.read_text(encoding="utf-8")
        return body_md, self._token_for_text(path, body_md), self._metadata_for(path)

    def write_doc(
        self,
        spec_id: str,
        doc_name: str,
        body_md: str,
        version_token: str,
        actor_name: str,
        force: bool = False,
    ) -> tuple[str, ResourceMetadata]:
        if doc_name not in WRITABLE_DOC_NAMES:
            raise ValidationError(
                "PATH_NOT_ALLOWED: only story.md, spec.md, and acceptance.md are writable"
            )
        encoded = body_md.encode("utf-8")
        if not encoded:
            raise ValidationError("VALIDATION_FAILED: body_md must not be empty")
        if len(encoded) > MAX_DOC_BYTES:
            raise ValidationError("TOO_LARGE: body_md exceeds 1 MiB")
        path = self.doc_path(spec_id, doc_name)
        self._check_actor(actor_name)
        current = path.read_text(encoding="utf-8")
        if not force:
            self._assert_token(path, current, version_token)
        self._atomic_write_text(path, body_md)
        metadata = self.record_activity("document.updated", path, actor_name)
        return self._token_for_text(path, body_md), metadata

    def list_wiki_pages(self) -> list[dict[str, str]]:
        if not self.wiki_pages_dir.exists():
            return []
        pages = []
        for path in sorted(self.wiki_pages_dir.rglob("*.md")):
            metadata = self._metadata_for(path)
            relative = path.relative_to(self.wiki_pages_dir).as_posix()
            pages.append(
                {
                    "page": relative[:-3],
                    "path": self.relative_path(path),
                    "updated_at": metadata.updated_at,
                    "last_modified_by": metadata.last_modified_by,
                }
            )
        return pages

    def wiki_index_path(self) -> Path:
        """Path to the wiki index file (.louke/wiki/index.md)."""
        return self.wiki_dir / "index.md"

    def read_wiki_index(self) -> tuple[str, ResourceMetadata] | None:
        """Read the wiki index file if it exists, else return None.

        The wiki index is a regular Markdown file at .louke/wiki/index.md
        that the librarian agent keeps up to date. The /wiki page renders
        this file's content (instead of enumerating pages/ directly).
        """
        path = self.wiki_index_path()
        if not path.exists():
            return None
        body_md = path.read_text(encoding="utf-8")
        return body_md, self._metadata_for(path)

    def read_wiki_page(self, page: str) -> tuple[Path, str, str, ResourceMetadata]:
        path = self.wiki_page_path(page)
        if not path.exists():
            raise FileNotFoundError(path)
        body_md = path.read_text(encoding="utf-8")
        return (
            path,
            body_md,
            self._token_for_text(path, body_md),
            self._metadata_for(path),
        )

    def write_wiki_page(
        self,
        page: str,
        body_md: str,
        version_token: str,
        actor_name: str,
    ) -> tuple[Path, str, ResourceMetadata]:
        path = self.wiki_page_path(page)
        self._check_actor(actor_name)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if path.exists():
            self._assert_token(path, current, version_token)
        elif version_token not in {"", "new"}:
            raise ConflictError(
                "wiki page does not exist yet; use empty token to create it"
            )
        self._atomic_write_text(path, self._ensure_trailing_newline(body_md))
        metadata = self.record_activity("wiki.updated", path, actor_name)
        return path, self._token_for_text(path, body_md), metadata

    def read_bindings(self) -> tuple[dict[str, Any], str, ResourceMetadata]:
        path = config_path(project=True, root=self.root)
        config = load_config(path)
        assignments = config.get("assignments")
        if not isinstance(assignments, dict):
            assignments = {}
        assignments.setdefault("roles", {})
        assignments.setdefault("agents", {})
        config["assignments"] = assignments
        config.setdefault("$schema", MODELS_SCHEMA)
        config.setdefault("version", 1)
        config.setdefault("aliases", {})
        token = self._token_for_json(path, config)
        metadata = (
            self._metadata_for(path) if path.exists() else ResourceMetadata("", "")
        )
        return config, token, metadata

    def write_bindings(
        self,
        config: dict[str, Any],
        version_token: str,
        actor_name: str,
    ) -> tuple[str, ResourceMetadata]:
        path = config_path(project=True, root=self.root)
        self._check_actor(actor_name)
        current, current_token, _ = self.read_bindings()
        if current_token != version_token:
            raise ConflictError("bindings version token is stale")
        payload = {
            "$schema": MODELS_SCHEMA,
            "version": int(config.get("version") or 1),
            "aliases": dict(config.get("aliases") or {}),
            "assignments": {
                "roles": dict((config.get("assignments") or {}).get("roles") or {}),
                "agents": dict((config.get("assignments") or {}).get("agents") or {}),
            },
        }
        self._atomic_write_text(path, self._stable_json(payload) + "\n")
        metadata = self.record_activity("bindings.updated", path, actor_name)
        return self._token_for_json(path, payload), metadata

    def read_text_target(
        self, target_path: str
    ) -> tuple[Path, str, str, ResourceMetadata]:
        path = self.resolve_target_path(target_path)
        body_md = path.read_text(encoding="utf-8")
        return (
            path,
            body_md,
            self._token_for_text(path, body_md),
            self._metadata_for(path),
        )

    def resolve_target_path(self, target_path: str) -> Path:
        candidate = (self.root / target_path).resolve()
        if not str(candidate).startswith(str(self.root)):
            raise ValidationError("target path escapes project root")
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def record_activity(
        self,
        event_type: str,
        path: Path,
        actor_name: str,
        extra: dict[str, Any] | None = None,
    ) -> ResourceMetadata:
        updated_at = self._now()
        payload: dict[str, Any] = {
            "type": event_type,
            "target": self.relative_path(path),
            "actor_name": actor_name,
            "updated_at": updated_at,
        }
        if extra:
            payload.update(extra)
        self.activity_path.parent.mkdir(parents=True, exist_ok=True)
        with self.activity_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return ResourceMetadata(updated_at=updated_at, last_modified_by=actor_name)

    def latest_activity(self, path: Path) -> ResourceMetadata:
        target = self.relative_path(path)
        latest: dict[str, Any] | None = None
        if self.activity_path.exists():
            for line in self.activity_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("target") == target:
                    latest = record
        if latest:
            return ResourceMetadata(
                updated_at=str(latest.get("updated_at") or ""),
                last_modified_by=str(latest.get("actor_name") or ""),
            )
        if path.exists():
            stat = path.stat()
            updated_at = (
                datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            return ResourceMetadata(updated_at=updated_at, last_modified_by="")
        return ResourceMetadata(updated_at="", last_modified_by="")

    def _metadata_for(self, path: Path) -> ResourceMetadata:
        return self.latest_activity(path)

    def _check_actor(self, actor_name: str) -> None:
        if not str(actor_name).strip():
            raise ValidationError("actor_name is required")

    def _assert_token(self, path: Path, current_text: str, version_token: str) -> None:
        current = self._token_for_text(path, current_text)
        if current != version_token:
            raise ConflictError("version token is stale")

    def _token_for_text(self, path: Path, text: str) -> str:
        digest = hashlib.sha256()
        digest.update(self.relative_path(path).encode("utf-8"))
        digest.update(b"\n")
        digest.update(text.encode("utf-8"))
        return digest.hexdigest()

    def _token_for_json(self, path: Path, data: dict[str, Any]) -> str:
        return self._token_for_text(path, self._stable_json(data))

    def _stable_json(self, data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)

    def _atomic_write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=f"{path.name}.", dir=str(path.parent))
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        Path(tmp_path).replace(path)

    def _normalize_page_name(self, page: str) -> str:
        value = str(page).strip().replace("\\", "/")
        if value in {"", ".", ".."}:
            raise ValidationError("wiki page name must not be empty")
        parts = [part for part in value.split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise ValidationError("wiki page name contains invalid path segments")
        return "/".join(parts)

    def _ensure_trailing_newline(self, body_md: str) -> str:
        return body_md if body_md.endswith("\n") else body_md + "\n"

    def _now(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    def _read_users_payload(self) -> dict[str, Any]:
        if not self.users_path.exists():
            return {"version": 1, "users": []}
        try:
            payload = json.loads(self.users_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid users file: {self.users_path}") from exc
        if not isinstance(payload, dict):
            raise ValidationError("users payload must be an object")
        return payload
