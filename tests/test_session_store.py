"""Tests for session models and Store session operations."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.models import AgentSession, SessionMessage
from crazypumpkin.framework.store import Store


class TestSessionMessageCreation:
    def test_fields(self):
        msg = SessionMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.timestamp  # auto-populated

    def test_defaults(self):
        msg = SessionMessage()
        assert msg.role == ""
        assert msg.content == ""


class TestAgentSessionCreation:
    def test_defaults(self):
        session = AgentSession(agent_name="test-agent")
        assert session.session_id  # auto-generated
        assert session.agent_name == "test-agent"
        assert session.status == "active"
        assert session.messages == []
        assert session.created_at
        assert session.updated_at


class TestSaveAndLoadSession:
    def test_round_trip(self, tmp_path):
        store = Store(data_dir=tmp_path)
        session = store.create_session("agent-x")
        store.append_message(session.session_id, "user", "hi")
        store.save_session(session)

        # Load from a fresh store to verify disk persistence
        store2 = Store(data_dir=tmp_path)
        loaded = store2.load_session(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.agent_name == "agent-x"
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "hi"


class TestListSessionsFilterByAgent:
    def test_filter(self):
        store = Store()
        store.create_session("agent_a")
        store.create_session("agent_a")
        store.create_session("agent_b")
        results = store.list_sessions(agent_name="agent_a")
        assert len(results) == 2
        assert all(s.agent_name == "agent_a" for s in results)


class TestListSessionsFilterByStatus:
    def test_filter(self):
        store = Store()
        s1 = store.create_session("agent-x")
        s2 = store.create_session("agent-y")
        s2.status = "completed"
        active = store.list_sessions(status="active")
        completed = store.list_sessions(status="completed")
        assert len(active) == 1
        assert active[0].session_id == s1.session_id
        assert len(completed) == 1
        assert completed[0].session_id == s2.session_id


class TestDeleteSession:
    def test_delete(self):
        store = Store()
        session = store.create_session("agent-x")
        assert store.delete_session(session.session_id) is True
        assert store.get_session(session.session_id) is None


class TestLoadNonexistentSession:
    def test_returns_none(self):
        store = Store()
        assert store.get_session("fake-id-12345") is None
