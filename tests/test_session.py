"""Tests for Session, SessionMessage models and SessionStore."""

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_models = importlib.import_module("crazypumpkin.framework.models")
_store_mod = importlib.import_module("crazypumpkin.framework.store")
_session_mod = importlib.import_module("crazypumpkin.framework.session")

SessionMessage = _models.SessionMessage
Session = _models.Session
Store = _store_mod.Store
SessionStore = _session_mod.SessionStore


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── SessionMessage model ────────────────────────────────────────────


class TestSessionMessageModel:
    def test_has_required_fields(self):
        msg = SessionMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_defaults(self):
        msg = SessionMessage()
        assert msg.role == ""
        assert msg.content == ""
        assert isinstance(msg.timestamp, str)
        assert len(msg.timestamp) > 0
        assert msg.metadata == {}

    def test_metadata_not_shared(self):
        a = SessionMessage()
        b = SessionMessage()
        a.metadata["k"] = "v"
        assert b.metadata == {}


# ── Session model ───────────────────────────────────────────────────


class TestSessionModel:
    def test_has_required_fields(self):
        s = Session(agent_name="test-agent")
        assert s.agent_name == "test-agent"
        assert isinstance(s.session_id, str)
        assert len(s.session_id) > 0

    def test_defaults(self):
        s = Session()
        assert s.agent_name == ""
        assert s.messages == []
        assert s.context == {}
        assert s.max_turns == 50
        assert s.status == "active"
        assert isinstance(s.created_at, str) and len(s.created_at) > 0
        assert isinstance(s.updated_at, str) and len(s.updated_at) > 0

    def test_unique_session_ids(self):
        a = Session()
        b = Session()
        assert a.session_id != b.session_id

    def test_messages_not_shared(self):
        a = Session()
        b = Session()
        a.messages.append(SessionMessage(role="user", content="hi"))
        assert b.messages == []

    def test_context_not_shared(self):
        a = Session()
        b = Session()
        a.context["key"] = "val"
        assert b.context == {}


# ── SessionStore.create ─────────────────────────────────────────────


class TestSessionStoreCreate:
    def test_returns_session_with_unique_id(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        assert isinstance(s, Session)
        assert isinstance(s.session_id, str)
        assert len(s.session_id) > 0

    def test_status_is_active(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        assert s.status == "active"

    def test_agent_name_set(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-b"))
        assert s.agent_name == "agent-b"

    def test_max_turns_default(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        assert s.max_turns == 50

    def test_max_turns_custom(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a", max_turns=10))
        assert s.max_turns == 10

    def test_unique_ids_across_creates(self):
        ss = SessionStore(Store())
        ids = {_run(ss.create("agent-a")).session_id for _ in range(5)}
        assert len(ids) == 5


# ── SessionStore.get ────────────────────────────────────────────────


class TestSessionStoreGet:
    def test_get_returns_none_for_nonexistent(self):
        ss = SessionStore(Store())
        assert _run(ss.get("nonexistent")) is None

    def test_get_returns_created_session(self):
        ss = SessionStore(Store())
        created = _run(ss.create("agent-a"))
        got = _run(ss.get(created.session_id))
        assert got is not None
        assert got.session_id == created.session_id
        assert got.agent_name == "agent-a"
        assert got.status == "active"


# ── SessionStore.append_message ─────────────────────────────────────


class TestSessionStoreAppendMessage:
    def test_adds_message(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        updated = _run(ss.append_message(s.session_id, "user", "hello"))
        assert len(updated.messages) == 1
        assert updated.messages[0].role == "user"
        assert updated.messages[0].content == "hello"

    def test_updates_updated_at(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        original_updated = s.updated_at
        updated = _run(ss.append_message(s.session_id, "user", "hello"))
        # updated_at should be >= original (both are ISO strings, lexicographic compare works)
        assert updated.updated_at >= original_updated

    def test_multiple_messages(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        _run(ss.append_message(s.session_id, "user", "hi"))
        _run(ss.append_message(s.session_id, "assistant", "hello"))
        got = _run(ss.get(s.session_id))
        assert len(got.messages) == 2
        assert got.messages[0].role == "user"
        assert got.messages[1].role == "assistant"

    def test_message_metadata(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        updated = _run(ss.append_message(
            s.session_id, "user", "hello", metadata={"source": "test"}
        ))
        assert updated.messages[0].metadata == {"source": "test"}

    def test_raises_for_nonexistent_session(self):
        ss = SessionStore(Store())
        with pytest.raises(KeyError):
            _run(ss.append_message("missing", "user", "hi"))


# ── SessionStore.close ──────────────────────────────────────────────


class TestSessionStoreClose:
    def test_sets_status_completed(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        closed = _run(ss.close(s.session_id))
        assert closed.status == "completed"

    def test_persists_completed_status(self):
        ss = SessionStore(Store())
        s = _run(ss.create("agent-a"))
        _run(ss.close(s.session_id))
        got = _run(ss.get(s.session_id))
        assert got.status == "completed"

    def test_raises_for_nonexistent(self):
        ss = SessionStore(Store())
        with pytest.raises(KeyError):
            _run(ss.close("missing"))


# ── SessionStore.list_sessions ──────────────────────────────────────


class TestSessionStoreListSessions:
    def test_list_all(self):
        ss = SessionStore(Store())
        _run(ss.create("agent-a"))
        _run(ss.create("agent-b"))
        result = _run(ss.list_sessions())
        assert len(result) == 2

    def test_filter_by_agent_name(self):
        ss = SessionStore(Store())
        _run(ss.create("agent-a"))
        _run(ss.create("agent-b"))
        _run(ss.create("agent-a"))
        result = _run(ss.list_sessions(agent_name="agent-a"))
        assert len(result) == 2
        assert all(s.agent_name == "agent-a" for s in result)

    def test_filter_by_status(self):
        ss = SessionStore(Store())
        s1 = _run(ss.create("agent-a"))
        _run(ss.create("agent-a"))
        _run(ss.close(s1.session_id))
        result = _run(ss.list_sessions(status="completed"))
        assert len(result) == 1
        assert result[0].status == "completed"

    def test_filter_by_agent_name_and_status(self):
        ss = SessionStore(Store())
        s1 = _run(ss.create("agent-a"))
        _run(ss.create("agent-b"))
        _run(ss.create("agent-a"))
        _run(ss.close(s1.session_id))
        result = _run(ss.list_sessions(agent_name="agent-a", status="active"))
        assert len(result) == 1
        assert result[0].status == "active"
        assert result[0].agent_name == "agent-a"

    def test_filter_no_match(self):
        ss = SessionStore(Store())
        _run(ss.create("agent-a"))
        result = _run(ss.list_sessions(agent_name="nonexistent"))
        assert result == []


# ── Round-trip persistence ──────────────────────────────────────────


class TestSessionRoundTrip:
    def test_create_append_close_get(self, tmp_path):
        store = Store(data_dir=tmp_path)
        ss = SessionStore(store)

        # Create
        s = _run(ss.create("agent-x", max_turns=20))
        sid = s.session_id

        # Append messages
        _run(ss.append_message(sid, "user", "question"))
        _run(ss.append_message(sid, "assistant", "answer"))

        # Close
        _run(ss.close(sid))

        # Get from a fresh store (disk round-trip)
        store2 = Store(data_dir=tmp_path)
        ss2 = SessionStore(store2)
        got = _run(ss2.get(sid))

        assert got is not None
        assert got.session_id == sid
        assert got.agent_name == "agent-x"
        assert got.status == "completed"
        assert got.max_turns == 20
        assert len(got.messages) == 2
        assert got.messages[0].role == "user"
        assert got.messages[0].content == "question"
        assert got.messages[1].role == "assistant"
        assert got.messages[1].content == "answer"
