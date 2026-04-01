"""Tests for session CLI commands: list, show, replay."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_session_list, cmd_session_show, cmd_session_replay
from crazypumpkin.framework.models import Session, SessionMessage, SessionStatus
from crazypumpkin.framework.store import Store


@pytest.fixture()
def store_with_sessions(tmp_path):
    """Create a store with sample sessions and persist to disk."""
    store = Store(tmp_path)

    s1 = Session(id="sess1", agent_id="dev-agent", model="gpt-4", status=SessionStatus.OPEN)
    s1.messages = [
        SessionMessage(role="user", content="Hello", timestamp="2025-01-01T00:00:00"),
        SessionMessage(role="assistant", content="Hi there!", timestamp="2025-01-01T00:00:01"),
    ]
    store.create_session(s1)

    s2 = Session(id="sess2", agent_id="review-agent", model="claude-3", status=SessionStatus.OPEN)
    s2.messages = [
        SessionMessage(role="user", content="Review this", timestamp="2025-01-02T00:00:00"),
    ]
    store.create_session(s2)
    store.close_session("sess2")

    s3 = Session(id="sess3", agent_id="dev-agent", model="gpt-4", status=SessionStatus.OPEN)
    store.create_session(s3)

    store.save()
    return tmp_path


# ── session list ──


class TestSessionList:
    def test_list_all_sessions(self, store_with_sessions, capsys):
        args = argparse.Namespace(agent=None, status=None)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = store_with_sessions.parent
            # data dir is the store_with_sessions path itself
            # We need Path.cwd() / "data" to point to our tmp_path
            MockPath.cwd.return_value = store_with_sessions.parent
            MockPath.side_effect = Path
            # Override: make cwd / "data" point to store_with_sessions
            with patch.object(Path, "__truediv__", side_effect=lambda self, other: store_with_sessions if other == "data" else Path.__truediv__(self, other)):
                pass
        # Simpler approach: patch the Store directly
        store = Store(store_with_sessions)
        store.load()
        with patch("crazypumpkin.cli.Path") as MockPath:
            mock_cwd = store_with_sessions.parent
            data_path = store_with_sessions
            MockPath.cwd.return_value = mock_cwd
            MockPath.side_effect = Path
            # The command does Path.cwd() / "data", we need this to be our tmp_path
            # Let's just mock the whole thing at Store level
        # Actually let's just test more directly
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = store_with_sessions  # cwd / "data" will be store_with_sessions / "data"
            MockPath.side_effect = Path
        # The function does: data_dir = Path.cwd() / "data"
        # So we need a parent dir where "data" subdir is our store_with_sessions
        # Easiest: create the structure
        pass

    def test_list_all(self, store_with_sessions, capsys):
        """List all sessions prints all three."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        # Copy state.json into data/
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(agent=None, status=None)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_list(args)

        out = capsys.readouterr().out
        assert "sess1" in out
        assert "sess2" in out
        assert "sess3" in out

    def test_list_filter_by_agent(self, store_with_sessions, capsys):
        """Filter sessions by agent_id."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(agent="dev-agent", status=None)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_list(args)

        out = capsys.readouterr().out
        assert "sess1" in out
        assert "sess3" in out
        assert "review-agent" not in out

    def test_list_filter_by_status(self, store_with_sessions, capsys):
        """Filter sessions by status."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(agent=None, status="closed")
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_list(args)

        out = capsys.readouterr().out
        assert "sess2" in out
        assert "sess1" not in out
        assert "sess3" not in out

    def test_list_no_sessions(self, tmp_path, capsys):
        """No sessions prints a message."""
        parent = tmp_path / "workspace"
        parent.mkdir()

        args = argparse.Namespace(agent=None, status=None)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_list(args)

        out = capsys.readouterr().out
        assert "No sessions found" in out


# ── session show ──


class TestSessionShow:
    def test_show_session(self, store_with_sessions, capsys):
        """Show a session displays its messages."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(session_id="sess1")
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_show(args)

        out = capsys.readouterr().out
        assert "sess1" in out
        assert "dev-agent" in out
        assert "gpt-4" in out
        assert "Hello" in out
        assert "Hi there!" in out
        assert "[1]" in out
        assert "[2]" in out

    def test_show_session_not_found(self, tmp_path):
        """Show a non-existent session exits with error."""
        parent = tmp_path / "workspace"
        parent.mkdir()

        args = argparse.Namespace(session_id="nonexistent")
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            with pytest.raises(SystemExit) as exc_info:
                cmd_session_show(args)
            assert exc_info.value.code == 1


# ── session replay ──


class TestSessionReplay:
    def test_replay_session(self, store_with_sessions, capsys):
        """Replay a session outputs all messages."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(session_id="sess1", speed=0)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_replay(args)

        out = capsys.readouterr().out
        assert "Replaying session sess1" in out
        assert "Turn 1: USER" in out
        assert "Hello" in out
        assert "Turn 2: ASSISTANT" in out
        assert "Hi there!" in out
        assert "Replay complete" in out

    def test_replay_session_not_found(self, tmp_path):
        """Replay a non-existent session exits with error."""
        parent = tmp_path / "workspace"
        parent.mkdir()

        args = argparse.Namespace(session_id="nonexistent", speed=0)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            with pytest.raises(SystemExit) as exc_info:
                cmd_session_replay(args)
            assert exc_info.value.code == 1

    def test_replay_empty_session(self, store_with_sessions, capsys):
        """Replay a session with no messages still completes."""
        parent = store_with_sessions.parent
        data_dir = parent / "data"
        data_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(store_with_sessions / "state.json", data_dir / "state.json")

        args = argparse.Namespace(session_id="sess3", speed=0)
        with patch("crazypumpkin.cli.Path") as MockPath:
            MockPath.cwd.return_value = parent
            MockPath.side_effect = Path
            cmd_session_replay(args)

        out = capsys.readouterr().out
        assert "Replaying session sess3" in out
        assert "0 messages" in out
        assert "Replay complete" in out
