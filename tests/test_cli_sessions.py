"""Tests for CLI session management commands: sessions, session-delete.

Covers: list sessions (tabular output), --agent filtering, delete confirmation,
and not-found handling.  All commands exit 0 on success.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cli
from crazypumpkin.framework.models import SessionRecord


# -- helpers ----------------------------------------------------------------


def _make_session(session_id="sess-001", agent_id="agent-a", num_messages=3,
                  created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T01:00:00Z"):
    return SessionRecord(
        session_id=session_id,
        agent_id=agent_id,
        messages=[{"role": "user", "content": f"msg{i}"} for i in range(num_messages)],
        created_at=created_at,
        updated_at=updated_at,
    )


def _mock_store(sessions=None, delete_return=True):
    """Return a MagicMock Store with list_sessions and delete_session configured."""
    store = MagicMock()
    store.list_sessions.return_value = sessions or []
    store.delete_session.return_value = delete_return
    store.load.return_value = False
    return store


# -- sessions command -------------------------------------------------------


class TestSessionsList:
    """Tests for ``crazypumpkin sessions``."""

    def test_exit_code_zero(self):
        store = _mock_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions"])
        assert result.exit_code == 0

    def test_shows_table_header(self):
        store = _mock_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions"])
        assert "session_id" in result.output
        assert "agent_id" in result.output
        assert "messages_count" in result.output
        assert "created_at" in result.output
        assert "updated_at" in result.output

    def test_shows_session_rows(self):
        sessions = [
            _make_session(session_id="sess-001", agent_id="agent-a", num_messages=3),
            _make_session(session_id="sess-002", agent_id="agent-b", num_messages=5,
                          created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T02:00:00Z"),
        ]
        store = _mock_store(sessions=sessions)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions"])
        assert "sess-001" in result.output
        assert "agent-a" in result.output
        assert "3" in result.output
        assert "sess-002" in result.output
        assert "agent-b" in result.output
        assert "5" in result.output

    def test_empty_sessions(self):
        store = _mock_store(sessions=[])
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions"])
        assert result.exit_code == 0
        # Header is still shown
        assert "session_id" in result.output


class TestSessionsFilterByAgent:
    """Tests for ``crazypumpkin sessions --agent <id>``."""

    def test_passes_agent_filter(self):
        store = _mock_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions", "--agent", "agent-x"])
        assert result.exit_code == 0
        store.list_sessions.assert_called_once_with(agent_id="agent-x")

    def test_no_filter_passes_empty_string(self):
        store = _mock_store()
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions"])
        assert result.exit_code == 0
        store.list_sessions.assert_called_once_with(agent_id="")

    def test_filtered_results_shown(self):
        sessions = [
            _make_session(session_id="sess-filtered", agent_id="agent-x", num_messages=2),
        ]
        store = _mock_store(sessions=sessions)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["sessions", "--agent", "agent-x"])
        assert "sess-filtered" in result.output
        assert "agent-x" in result.output


# -- session-delete command -------------------------------------------------


class TestSessionDelete:
    """Tests for ``crazypumpkin session-delete <id>``."""

    def test_delete_existing_session(self):
        store = _mock_store(delete_return=True)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["session-delete", "sess-001"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        assert "sess-001" in result.output
        store.delete_session.assert_called_once_with("sess-001")

    def test_delete_nonexistent_session(self):
        store = _mock_store(delete_return=False)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["session-delete", "no-such-id"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()
        assert "no-such-id" in result.output

    def test_delete_exit_code_zero(self):
        store = _mock_store(delete_return=True)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["session-delete", "sess-001"])
        assert result.exit_code == 0

    def test_delete_nonexistent_exit_code_zero(self):
        store = _mock_store(delete_return=False)
        runner = CliRunner()
        with patch("crazypumpkin.framework.store.Store", return_value=store):
            result = runner.invoke(cli, ["session-delete", "nonexistent"])
        assert result.exit_code == 0
