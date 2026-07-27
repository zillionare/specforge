"""AC coverage for the Batch C Chat workbench contract."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from louke.web.app import create_app
from tests.test_web_server import authenticate, build_project


def _html(tmp_path: Path) -> str:
    client = TestClient(create_app(build_project(tmp_path)))
    authenticate(client)
    return client.get("/workbench?activity=chat").text


def test_chat_agent_list_default_maestro(tmp_path: Path) -> None:
    """AC-FR1305-01/02/03: Chat exposes the canonical ordered Agent roster."""
    html = _html(tmp_path)
    expected_ids = [
        "maestro",
        "archer",
        "devon",
        "judge",
        "lex",
        "librarian",
        "prism",
        "sage",
        "scribe",
        "shield",
    ]
    positions = [
        html.index(f'data-chat-agent="{agent_id}"') for agent_id in expected_ids
    ]

    assert html.count("data-chat-agent=") == len(expected_ids)
    assert positions == sorted(positions)
    assert 'data-testid="chat-agent-maestro"' in html
    assert 'data-chat-agent="maestro" aria-selected="true"' in html
    assert 'data-chat-agent="scout"' not in html
    assert 'data-chat-agent="warden"' not in html
    assert 'data-chat-agent="keeper"' not in html


def test_chat_transcript_renders_input(tmp_path: Path) -> None:
    """AC-FR1306-01/03: Chat renders an empty transcript and plain input."""
    html = _html(tmp_path)
    assert 'data-testid="chat-transcript"' in html
    assert 'data-testid="chat-transcript-maestro"' in html
    assert 'data-testid="chat-input"' in html
    assert 'data-testid="chat-submit"' in html
    assert 'placeholder="Type a message to Maestro..."' in html


def test_chat_submit_clears_input(tmp_path: Path) -> None:
    """AC-FR1306-03: submit clears the input immediately."""
    html = _html(tmp_path)
    assert "input.value=''" in html or "input.value = ''" in html
    assert "submit" in html


def test_chat_agent_switch_isolates_transcript(tmp_path: Path) -> None:
    """AC-FR1307-01/02: each agent owns a separate transcript element."""
    html = _html(tmp_path)
    assert 'data-testid="chat-transcript-maestro"' in html
    assert 'data-testid="chat-transcript-devon"' in html
    assert "transcripts[agent]" in html
    assert "activeAgent" in html


def test_chat_unknown_agent_falls_back_to_maestro(tmp_path: Path) -> None:
    """AC-FR1307-04: unknown agent selection falls back with a visible toast."""
    html = _html(tmp_path)
    assert "未知 Agent:" in html
    assert "Maestro" in html
    assert "chat-agent-maestro" in html
