"""Unit contracts for session-bound v0.14 mutation protection."""

from pathlib import Path
from types import SimpleNamespace
import json

import pytest


from louke.web.auth import (
    csrf_token_for_session,
    issue_session_cookie,
    verify_csrf_token,
)
from starlette.responses import Response
from louke.web.app import _set_session_cookie
from louke.web.api.projects import _require_human as require_project_human
from louke.web.api.scribe import _require_human as require_scribe_human
from louke.web.store import ProjectStore
from louke.web.api.projects import _require_human


def _store(tmp_path: Path) -> ProjectStore:
    """Create the smallest project store fixture required by session signing."""
    project_dir = tmp_path / ".louke" / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "project.toml").write_text(
        "[project]\nrepo = 'example/repo'\n", encoding="utf-8"
    )
    return ProjectStore(tmp_path)


def test_csrf_token_is_bound_to_the_authenticated_session(tmp_path: Path) -> None:
    """AC-FR0600-03: CSRF tokens are valid only for their original session."""
    store = _store(tmp_path)
    session = issue_session_cookie(store, "human")
    token = csrf_token_for_session(store, session)

    assert verify_csrf_token(store, session, token)
    assert not verify_csrf_token(store, session + "x", token)
    assert not verify_csrf_token(store, session, token + "x")


def test_csrf_token_requires_non_empty_values(tmp_path: Path) -> None:
    """AC-FR0600-03: missing session or token fails closed."""
    store = _store(tmp_path)

    assert not verify_csrf_token(store, "", "")
    assert not verify_csrf_token(store, "session", "")


def test_release_mutation_requires_header_even_when_csrf_cookie_exists(
    tmp_path: Path,
) -> None:
    """AC-FR0600-03: a CSRF cookie alone cannot authorize a mutation."""
    store = _store(tmp_path)
    store.create_user("human", "password")
    session = issue_session_cookie(store, "human")
    csrf = csrf_token_for_session(store, session)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(store=store, allowed_origin="https://louke.example")
        ),
        cookies={"louke_session": session, "louke_csrf": csrf},
        headers={"origin": "https://louke.example"},
    )

    response = _require_human(request, csrf_required=True)

    assert response.status_code == 403
    assert json.loads(response.body)["error_code"] == "CSRF_INVALID"


def test_session_cookie_contract_is_strict_and_only_session_cookie_is_set(
    tmp_path: Path,
) -> None:
    """AC-NFR0100-01: auth cookies are Strict, HttpOnly, and CSRF is header-only."""
    store = _store(tmp_path)
    response = Response()

    _set_session_cookie(response, store, "human")

    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 1
    assert cookies[0].startswith("louke_session=")
    assert "HttpOnly" in cookies[0]
    assert "SameSite=strict" in cookies[0]
    assert "louke_csrf=" not in cookies[0]


@pytest.mark.parametrize("require_human", [require_project_human, require_scribe_human])
@pytest.mark.parametrize("origin", [None, "https://foreign.example"])
def test_v14_mutations_reject_missing_or_foreign_origin_without_state_change(
    tmp_path: Path, require_human, origin: str | None
) -> None:
    """AC-FR0600-03: v0.14 mutations require the configured same-origin header."""
    store = _store(tmp_path)
    store.create_user("human", "password")
    session = issue_session_cookie(store, "human")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(store=store, allowed_origin="https://louke.example")
        ),
        cookies={"louke_session": session},
        headers={"origin": origin} if origin else {},
    )

    response = require_human(request, csrf_required=True)

    assert response.status_code == 403
    assert json.loads(response.body)["error_code"] == "ORIGIN_FORBIDDEN"
