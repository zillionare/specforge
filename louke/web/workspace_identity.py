"""Stable internal workspace identity and user-facing workspace label."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def canonical_workspace_id(project_info: dict[str, Any]) -> str:
    """Return the normalized repository identity from ``[project].repo``."""
    repo = str(project_info.get("repo") or "").strip()
    if not repo:
        return ""
    value = re.sub(r"^https?://", "", repo, flags=re.IGNORECASE)
    value = re.sub(r"^git@", "", value, flags=re.IGNORECASE)
    value = value.replace(":", "/", 1) if value.startswith("github.com:") else value
    value = value.removeprefix("www.").strip().strip("/")
    value = value.removesuffix(".git").strip("/")
    if value.startswith("github.com/"):
        return value
    return f"github.com/{value}" if "/" in value else value


def workspace_label(workspace_root: str | Path) -> str:
    """Return the stable user-facing workspace name from its root directory."""
    return Path(workspace_root).resolve().name
