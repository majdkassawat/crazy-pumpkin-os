"""Tests for CLI session management commands: session list/show/close.

Covers: list sessions table, --agent/--status filtering, show messages,
close transitions, and error handling for invalid IDs.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cli
from crazypumpkin.framework.models import Session, SessionMessage


# -- helpers ----------------------------------------------------------------


def _make_session(
    session_id="sess-001",
    agent_name="myagent",
    status="active",
    messages=None,
    created_at="2026-01-01T00:00:00Z",
    updated_at="2026-01-01T01:00:00Z",
):
    msgs = messages or [
        SessionMessage(role="user", content="hello", timestamp="2026-01-01T00:00:01Z"),
        SessionMessage(role="assistant", content="hi there", timestamp="2026-01-01T00:00:02Z"),
    ]
    return Session(
        session_id=session_id,
        agent_name=agent_name,
        messages=msgs,
        created_at=created_at,
        updated_at=updated_at,
        status=status,
    )


def _mock_session_store(sessions=None, get_result=None, close_result=None, close_error=None):
    """Return a mock SessionStore."""
    ss = MagicMock()
    ss.list_sessions = AsyncMock(return_value=sessions or [])
    if get_result is not None:
        ss.get = AsyncMock(return_value=get_result)
    else:
        ss.get = AsyncMock(return_value=None)
    if close_error:
        ss.close = AsyncMock(side_effect=close_error)
    elif close_result is not None:
        ss.close = AsyncMock(return_value=close_result)
    else:
        ss.close = AsyncMock(side_effect=KeyError("not found"))
    return ss


def _patch_store_and_session_store(ss_mock):
    """Return a context-manager-composable pair of patches."""
    store_mock = MagicMock()
    store_mock.load.return_value = False
    return (
        patch("crazypumpkin.cli.Store", return_value=store_mock),
        patch("crazypumpkin.cli.SessionStore", return_value=ss_mock),
    )


# -- session list -----------------------------------------------------------


class TestSessionList:
    """Tests for ``cpos session list``."""

    def test_exit_code_zero(self):
        ss = _mock_session_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list"])
        assert result.exit_code == 0

    def test_shows_table_header(self):
        ss = _mock_session_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list"])
        assert "id" in result.output
        assert "agent" in result.output
        assert "status" in result.output
        assert "turns" in result.output
        assert "created_at" in result.output

    def test_shows_session_rows(self):
        sessions = [
            _make_session(session_id="sess-001", agent_name="agent-a", status="active"),
            _make_session(session_id="sess-002", agent_name="agent-b", status="completed"),
        ]
        ss = _mock_session_store(sessions=sessions)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list"])
        assert "sess-001" in result.output
        assert "agent-a" in result.output
        assert "active" in result.output
        assert "sess-002" in result.output
        assert "agent-b" in result.output
        assert "completed" in result.output

    def test_shows_turn_count(self):
        sessions = [
            _make_session(session_id="sess-t", agent_name="a", messages=[
                SessionMessage(role="user", content="hi", timestamp="t1"),
                SessionMessage(role="assistant", content="hey", timestamp="t2"),
                SessionMessage(role="user", content="bye", timestamp="t3"),
            ]),
        ]
        ss = _mock_session_store(sessions=sessions)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list"])
        assert "3" in result.output

    def test_filter_by_agent(self):
        sessions = [_make_session(agent_name="myagent")]
        ss = _mock_session_store(sessions=sessions)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list", "--agent", "myagent"])
        assert result.exit_code == 0
        ss.list_sessions.assert_called_once_with(agent_name="myagent", status=None)

    def test_filter_by_status(self):
        ss = _mock_session_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list", "--status", "active"])
        assert result.exit_code == 0
        ss.list_sessions.assert_called_once_with(agent_name=None, status="active")

    def test_empty_list(self):
        ss = _mock_session_store(sessions=[])
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "list"])
        assert result.exit_code == 0
        assert "id" in result.output  # header still present


# -- session show -----------------------------------------------------------


class TestSessionShow:
    """Tests for ``cpos session show <id>``."""

    def test_shows_all_messages(self):
        messages = [
            SessionMessage(role="user", content="hello world", timestamp="2026-01-01T00:00:01Z"),
            SessionMessage(role="assistant", content="hi there", timestamp="2026-01-01T00:00:02Z"),
            SessionMessage(role="user", content="bye", timestamp="2026-01-01T00:00:03Z"),
        ]
        session = _make_session(session_id="sess-show", messages=messages)
        ss = _mock_session_store(get_result=session)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "show", "sess-show"])
        assert result.exit_code == 0
        assert "user" in result.output
        assert "assistant" in result.output
        assert "hello world" in result.output
        assert "hi there" in result.output
        assert "bye" in result.output

    def test_shows_role_and_timestamp(self):
        messages = [
            SessionMessage(role="user", content="test", timestamp="2026-01-01T00:00:01Z"),
        ]
        session = _make_session(session_id="sess-ts", messages=messages)
        ss = _mock_session_store(get_result=session)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "show", "sess-ts"])
        assert "2026-01-01T00:00:01Z" in result.output
        assert "user" in result.output

    def test_shows_session_metadata(self):
        session = _make_session(session_id="sess-meta", agent_name="agentX", status="active")
        ss = _mock_session_store(get_result=session)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "show", "sess-meta"])
        assert "sess-meta" in result.output
        assert "agentX" in result.output
        assert "active" in result.output

    def test_invalid_session_id_exits_with_error(self):
        ss = _mock_session_store(get_result=None)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "show", "no-such-id"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()


# -- session close ----------------------------------------------------------


class TestSessionClose:
    """Tests for ``cpos session close <id>``."""

    def test_closes_active_session(self):
        closed = _make_session(session_id="sess-close", status="completed")
        ss = _mock_session_store(close_result=closed)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "close", "sess-close"])
        assert result.exit_code == 0
        assert "closed" in result.output.lower()
        assert "sess-close" in result.output

    def test_close_calls_session_store(self):
        closed = _make_session(session_id="sess-c2", status="completed")
        ss = _mock_session_store(close_result=closed)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "close", "sess-c2"])
        ss.close.assert_called_once_with("sess-c2")

    def test_invalid_session_id_exits_with_error(self):
        ss = _mock_session_store(close_error=KeyError("Session not-exist not found"))
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store") as MockStore, \
             patch("crazypumpkin.framework.session.SessionStore", return_value=ss):
            MockStore.return_value.load.return_value = False
            result = runner.invoke(cli, ["session", "close", "not-exist"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()
