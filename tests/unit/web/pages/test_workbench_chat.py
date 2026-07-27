"""Unit contract tests for the Workbench Chat client behavior."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app


def _complete_workspace(tmp_path: Path) -> Path:
    """Build a workspace with the minimum Web metadata."""
    (tmp_path / ".louke" / "project" / "specs" / "demo").mkdir(parents=True)
    (tmp_path / ".louke" / "wiki" / "pages").mkdir(parents=True)
    (tmp_path / ".louke" / "wiki" / "pages" / "guides").mkdir(parents=True)
    (tmp_path / ".louke" / "project" / "project.toml").write_text(
        '[project]\nversion = "0.8"\nspec_id = "demo"\n', encoding="utf-8"
    )
    return tmp_path


def _client(tmp_path: Path) -> TestClient:
    """Return an authenticated client for the protected Workbench page."""
    client = TestClient(create_app(_complete_workspace(tmp_path)))
    response = client.post(
        "/api/auth/register", json={"username": "human", "password": "secret"}
    )
    assert response.status_code == 200
    return client


def _select_agent_source(tmp_path: Path) -> str:
    """Return the generated client-side Agent selection function.

    The caller must pass a workspace whose ``.louke/`` layout already
    includes the minimum project metadata.
    """
    response = _client(tmp_path).get("/workbench?activity=chat")

    assert response.status_code == 200
    html = response.text
    start = html.index("function selectAgent")
    end = html.index("function openTab", start)
    return html[start:end]


def test_chat_delta_registers_message_id_before_transcript_refresh(
    tmp_path: Path,
) -> None:
    """An SSE-rendered assistant id must be known to refresh deduplication."""
    response = _client(tmp_path).get("/workbench?activity=chat")

    assert response.status_code == 200
    html = response.text
    add_start = html.index("function addChatMessage")
    start = html.index("function appendChatDelta")
    end = html.index("function connectChatStream", start)
    add_message = html[add_start:start]
    append_delta = html[start:end]

    assert "renderedMessages[agent].has(id)" in add_message
    assert "renderedMessages[agent].add(id)" in add_message
    assert "renderedMessages[agent]??=new Set()" in append_delta
    assert "renderedMessages[agent].add(event.message_id)" in append_delta
    assert append_delta.index("item.textContent") < append_delta.index(
        "renderedMessages[agent].add"
    )


def test_chat_uses_normalized_agent_ids_and_inflight_submit_guard(
    tmp_path: Path,
) -> None:
    """Chat setup targets the selected Agent and admits one in-flight submit."""
    response = _client(tmp_path).get("/workbench?activity=chat")

    assert response.status_code == 200
    html = response.text
    assert 'data-chat-agent="devon"' in html
    assert 'data-testid="chat-transcript-devon"' in html
    session_start = html.index("async function chatSession")
    session_end = html.index("async function refreshChat", session_start)
    chat_session = html[session_start:session_end]
    assert "body:JSON.stringify({agent})" in chat_session
    send_start = html.index("async function sendChat")
    send_end = html.index('document.querySelector(\'[data-testid="chat-form"]')
    send_chat = html[send_start:send_end]
    assert "chatSubmissions[agent]" in send_chat


def test_chat_agent_switch_closes_only_the_previous_view_stream(tmp_path: Path) -> None:
    """Switching Agents closes the old view subscription but preserves sessions."""
    select_agent = _select_agent_source(tmp_path)

    assert "if(agent===activeAgent&&!transcripts[agent].hidden)return;" in select_agent
    assert "const previous=activeAgent" in select_agent
    assert "chatStreams[previous].close()" in select_agent
    assert "delete chatStreams[previous]" in select_agent
    assert "delete sessions" not in select_agent
    assert ".abort()" not in select_agent

    close_index = select_agent.index("chatStreams[previous].close()")
    delete_index = select_agent.index("delete chatStreams[previous]")
    activate_index = select_agent.index("activeAgent=agent")
    assert close_index < delete_index < activate_index


def test_chat_agent_switch_resyncs_and_reconnects_existing_session(
    tmp_path: Path,
) -> None:
    """Returning to a known Agent refreshes its transcript and view stream."""
    select_agent = _select_agent_source(tmp_path)

    assert "if(sessions[agent])" in select_agent
    assert "refreshChat(agent)" in select_agent
    assert "connectChatStream(agent,sessions[agent])" in select_agent
    assert select_agent.index("refreshChat(agent)") < select_agent.index(
        "connectChatStream(agent,sessions[agent])"
    )
