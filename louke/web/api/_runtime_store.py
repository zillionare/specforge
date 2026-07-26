"""Shared Runtime workflow catalog and project Runtime-store accessors.

The top-level web application supplies one SQLite-backed store to every
Runtime, projects, gates and bindings sub-application. Standalone sub-apps
remain available with an isolated in-memory store for unit tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from louke.runtime.catalog import DefinitionRegistry, Edge, Step, WorkflowDefinition
from louke.runtime.release_contract import (
    DEVELOPMENT_BOOTSTRAP_MODE,
    build_entry_definition,
    is_louke_workspace,
    load_release_contract_bundle,
)
from louke.runtime.store import WorkflowRunStore

if TYPE_CHECKING:
    from starlette.applications import Starlette

#: Canonical attribute on ``app.state`` holding the Runtime store.
_STORE_ATTR: str = "runtime_run_store"
#: Read-only compatibility alias for callers released before v0.14.
_COMPAT_STORE_ATTR: str = "v12_run_store"

#: Default models offered to the v0.12 binding sub-app (FR-1301 placeholder).
DEFAULT_MODELS: dict[str, str] = {
    "devon": "claude-sonnet",
    "maestro": "claude-opus",
    "sage": "claude-haiku",
}

#: Models that may be selected as overrides.
AVAILABLE_MODELS: frozenset[str] = frozenset(
    {"claude-sonnet", "claude-opus", "claude-haiku", "gpt-4o"}
)


def _bug_fix_definition() -> WorkflowDefinition:
    """Return the minimal ``bug_fix`` workflow definition.

    The graph is: ``source_contract_verify`` (program) -> ``reproduce``
    (program) -> ``fix`` (semantic_task) -> ``complete`` (program, terminal).
    """
    verify = Step(
        step_id="source_contract_verify",
        kind="program",
        transitions=(Edge("e3", "source_contract_verify", "reproduce", "verified"),),
        implemented=True,
    )
    reproduce = Step(
        step_id="reproduce",
        kind="program",
        transitions=(Edge("e6", "reproduce", "fix", "done"),),
        implemented=True,
    )
    fix = Step(
        step_id="fix",
        kind="semantic_task",
        capability="code_generation",
        transitions=(Edge("e7", "fix", "complete", "done"),),
        implemented=True,
    )
    complete = Step(step_id="complete", kind="program", implemented=True)
    return WorkflowDefinition(
        definition_id="bug_fix",
        version="1",
        start_step="source_contract_verify",
        steps=(verify, reproduce, fix, complete),
    )


def build_catalog(
    workspace_root: str | None = None,
    *,
    mode: str | None = None,
) -> DefinitionRegistry:
    """Return the Runtime catalog for a workspace and explicit runtime mode.

    Args:
        workspace_root: Workspace whose Runtime contract is being served.
        mode: ``development_bootstrap`` only for Louke's own v0.14 workspace.
            ``None`` retains the legacy host-project compatibility definition.

    Returns:
        A registry containing the canonical v0.14 ``new_feature`` definition
        when bootstrap is enabled, plus the compatibility ``bug_fix`` entry.

    Raises:
        DevelopmentBootstrapError: If bootstrap is requested by a host project.
        ReleaseContractError: If Louke's bundle is missing or stale.
    """
    registry = DefinitionRegistry()
    if (
        mode is None
        and workspace_root is not None
        and is_louke_workspace(workspace_root)
    ):
        mode = DEVELOPMENT_BOOTSTRAP_MODE
    if mode == DEVELOPMENT_BOOTSTRAP_MODE:
        if workspace_root is None:
            raise ValueError("workspace_root is required for development bootstrap")
        bundle = load_release_contract_bundle(workspace_root, mode=mode)
        registry.register(build_entry_definition(bundle))
    else:
        registry.register(_host_compatibility_definition())
        registry.register(_project_entry_definition())
    registry.register(_bug_fix_definition())
    return registry


def _host_compatibility_definition() -> WorkflowDefinition:
    """Return the read-only compatibility graph for host workspaces."""
    start = Step(
        step_id="start",
        kind="program",
        transitions=(Edge("e1", "start", "requirements_approval", "done"),),
        implemented=True,
    )
    req = Step(
        step_id="requirements_approval",
        kind="human_gate",
        transitions=(Edge("e2", "requirements_approval", "design", "approved"),),
        implemented=True,
    )
    design = Step(
        step_id="design",
        kind="program",
        transitions=(Edge("e3", "design", "m_lock", "done"),),
        implemented=True,
    )
    m_lock = Step(
        step_id="m_lock",
        kind="human_gate",
        transitions=(Edge("e4", "m_lock", "implementation", "approved"),),
        implemented=True,
    )
    implementation = Step(
        step_id="implementation",
        kind="semantic_task",
        capability="code_generation",
        transitions=(Edge("e5", "implementation", "complete", "done"),),
        implemented=True,
    )
    complete = Step(step_id="complete", kind="program", implemented=True)
    return WorkflowDefinition(
        definition_id="new_feature",
        version="1",
        start_step="start",
        steps=(start, req, design, m_lock, implementation, complete),
    )


def _project_entry_definition() -> WorkflowDefinition:
    """Return the stable Project-creation entry flow for a host workspace."""
    entry = Step(
        step_id="M-START",
        kind="program",
        transitions=(Edge("entry-story", "M-START", "M-STORY", "done"),),
        handler="project.start_story",
        implemented=True,
    )
    story = Step(step_id="M-STORY", kind="program", implemented=True)
    return WorkflowDefinition(
        definition_id="project_entry",
        version="1",
        start_step=entry.step_id,
        steps=(entry, story),
    )


def build_run_store(
    db_path: str | None = None,
    *,
    workspace_root: str | None = None,
    mode: str | None = None,
) -> WorkflowRunStore:
    """Return a catalog-bound ``WorkflowRunStore``.

    Args:
        db_path: Optional SQLite file path. ``None`` creates an isolated
            in-memory store, which is the default for standalone sub-app tests.

        workspace_root: Workspace whose Runtime catalog is being served.
        mode: Explicit Runtime mode passed to :func:`build_catalog`.

    Returns:
        A ``WorkflowRunStore`` bound to the selected immutable catalog.
    """
    return WorkflowRunStore(
        db_path=db_path,
        catalog=build_catalog(workspace_root, mode=mode),
    )


def get_definition(store: WorkflowRunStore, definition_id: str, version: str):
    """Look up a registered workflow definition by id/version.

    Args:
        store: The ``WorkflowRunStore`` whose catalog holds the definition.
        definition_id: The stable definition identifier.
        version: The immutable version string.

    Returns:
        The matching ``WorkflowDefinition``.

    Raises:
        DefinitionNotFoundError: If no definition with that id/version is
            registered.
    """
    from louke.runtime.catalog import DefinitionNotFoundError

    catalog = store._catalog
    if catalog is None:
        raise DefinitionNotFoundError(
            f"store has no catalog; definition {definition_id!r} not found"
        )
    if definition_id == "new_feature" and version == "1":
        try:
            return catalog.get(definition_id, "0.14.0")
        except DefinitionNotFoundError:
            pass
    return catalog.get(definition_id, version)


def get_or_create_store(app: "Starlette") -> WorkflowRunStore:
    """Return the per-app singleton ``WorkflowRunStore``, creating it lazily.

    The store is created on first call (inside the request thread) and cached
    on ``app.state.runtime_run_store`` so subsequent requests reuse it. The
    legacy ``v12_run_store`` injection alias is promoted to the canonical
    identity when present. This is required because the ``sqlite3`` connection
    is thread-bound and Starlette dispatches requests in a portal thread
    distinct from the app-build thread.

    Args:
        app: The Starlette sub-app whose ``state`` caches the store.

    Returns:
        The cached or newly-created ``WorkflowRunStore``.
    """
    store = getattr(app.state, _STORE_ATTR, None)
    if store is None:
        store = getattr(app.state, _COMPAT_STORE_ATTR, None)
    if store is None:
        store = build_run_store()
    _cache_store_aliases(app, store)
    return store


def _cache_store_aliases(app: "Starlette", store: WorkflowRunStore) -> None:
    """Cache one store under the canonical and legacy app-state attributes."""
    setattr(app.state, _STORE_ATTR, store)
    setattr(app.state, _COMPAT_STORE_ATTR, store)
