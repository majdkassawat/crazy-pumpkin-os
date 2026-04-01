"""Tests for CLI session commands: sessions, session-show, session-delete."""

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_sessions, cmd_session_show, cmd_session_delete
from crazypumpkin.framework.models import AgentSession, SessionMessage
from crazypumpkin.framework.store import Store


def _make_store_with_sessions():
    """Create a Store pre-populated with two sessions."""
    store = Store()
    s1 = store.create_session("strategist")
    store.append_message(s1.session_id, "user", "hello")
    store.append_message(s1.session_id, "assistant", "hi there")

    s2 = store.create_session("developer")
    s2.status = "closed"

    return store, s1, s2


STORE_PATCH = "crazypumpkin.framework.store.Store"


class TestCmdSessions:
    """Tests for 'crazypumpkin sessions'."""

    def test_lists_sessions_tabular(self):
        store, s1, s2 = _make_store_with_sessions()
        args = argparse.Namespace(command="sessions", agent=None, status=None)

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_sessions(args)

        output = buf.getvalue()
        assert "session_id" in output
        assert "agent_name" in output
        assert "status" in output
        assert "message_count" in output
        assert "updated_at" in output
        assert s1.session_id in output
        assert "strategist" in output

    def test_lists_sessions_filter_by_agent(self):
        store, s1, s2 = _make_store_with_sessions()
        args = argparse.Namespace(command="sessions", agent="developer", status=None)

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_sessions(args)

        output = buf.getvalue()
        assert s2.session_id in output
        assert s1.session_id not in output

    def test_lists_sessions_filter_by_status(self):
        store, s1, s2 = _make_store_with_sessions()
        args = argparse.Namespace(command="sessions", agent=None, status="active")

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_sessions(args)

        output = buf.getvalue()
        assert s1.session_id in output
        assert s2.session_id not in output

    def test_empty_sessions_message(self):
        store = Store()
        args = argparse.Namespace(command="sessions", agent=None, status="active")

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_sessions(args)

        assert "No sessions found" in buf.getvalue()


class TestCmdSessionShow:
    """Tests for 'crazypumpkin session-show <id>'."""

    def test_shows_session_metadata_and_messages(self):
        store, s1, _ = _make_store_with_sessions()
        args = argparse.Namespace(command="session-show", session_id=s1.session_id)

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_show(args)

        output = buf.getvalue()
        assert s1.session_id in output
        assert "strategist" in output
        assert "active" in output
        assert "[user] hello" in output
        assert "[assistant] hi there" in output

    def test_shows_session_not_found(self):
        store = Store()
        args = argparse.Namespace(command="session-show", session_id="nonexistent")

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_show(args)

        assert "not found" in buf.getvalue()

    def test_shows_session_no_messages(self):
        store = Store()
        s = store.create_session("reviewer")
        args = argparse.Namespace(command="session-show", session_id=s.session_id)

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_show(args)

        output = buf.getvalue()
        assert s.session_id in output
        assert "No messages" in output


class TestCmdSessionDelete:
    """Tests for 'crazypumpkin session-delete <id>'."""

    def test_delete_with_force(self):
        store, s1, _ = _make_store_with_sessions()
        args = argparse.Namespace(
            command="session-delete", session_id=s1.session_id, force=True,
        )

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_delete(args)

        assert "deleted" in buf.getvalue()
        assert store.get_session(s1.session_id) is None

    def test_delete_not_found(self):
        store = Store()
        args = argparse.Namespace(
            command="session-delete", session_id="nonexistent", force=True,
        )

        with patch(STORE_PATCH, return_value=store):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_delete(args)

        assert "not found" in buf.getvalue()

    def test_delete_aborted_without_force(self):
        store, s1, _ = _make_store_with_sessions()
        args = argparse.Namespace(
            command="session-delete", session_id=s1.session_id, force=False,
        )

        with patch(STORE_PATCH, return_value=store), \
             patch("builtins.input", return_value="n"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_delete(args)

        assert "Aborted" in buf.getvalue()
        assert store.get_session(s1.session_id) is not None

    def test_delete_confirmed_without_force(self):
        store, s1, _ = _make_store_with_sessions()
        args = argparse.Namespace(
            command="session-delete", session_id=s1.session_id, force=False,
        )

        with patch(STORE_PATCH, return_value=store), \
             patch("builtins.input", return_value="y"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_session_delete(args)

        assert "deleted" in buf.getvalue()
        assert store.get_session(s1.session_id) is None
