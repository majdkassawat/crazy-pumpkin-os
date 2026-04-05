"""Tests for SessionRecord model and Store session persistence methods."""

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_models = importlib.import_module("crazypumpkin.framework.models")
_store_mod = importlib.import_module("crazypumpkin.framework.store")

SessionRecord = _models.SessionRecord
Store = _store_mod.Store


# ── SessionRecord dataclass ──────────────────────────────────────────


class TestSessionRecordDataclass:
    def test_fields_exist(self):
        rec = SessionRecord()
        assert hasattr(rec, "session_id")
        assert hasattr(rec, "agent_id")
        assert hasattr(rec, "messages")
        assert hasattr(rec, "created_at")
        assert hasattr(rec, "updated_at")
        assert hasattr(rec, "metadata")

    def test_defaults(self):
        rec = SessionRecord()
        assert isinstance(rec.session_id, str) and len(rec.session_id) > 0
        assert rec.agent_id == ""
        assert rec.messages == []
        assert isinstance(rec.created_at, str) and len(rec.created_at) > 0
        assert isinstance(rec.updated_at, str) and len(rec.updated_at) > 0
        assert rec.metadata == {}

    def test_custom_values(self):
        rec = SessionRecord(
            session_id="s1",
            agent_id="a1",
            messages=[{"role": "user", "content": "hi"}],
            metadata={"key": "val"},
        )
        assert rec.session_id == "s1"
        assert rec.agent_id == "a1"
        assert rec.messages == [{"role": "user", "content": "hi"}]
        assert rec.metadata == {"key": "val"}


# ── save_session persists to disk ────────────────────────────────────


class TestSaveSession:
    def test_writes_json_to_disk(self, tmp_path):
        store = Store(data_dir=tmp_path)
        rec = SessionRecord(session_id="sess1", agent_id="agent1")
        store.save_session(rec)

        path = tmp_path / "sessions" / "sess1.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess1"
        assert data["agent_id"] == "agent1"

    def test_no_disk_write_without_data_dir(self):
        store = Store()
        rec = SessionRecord(session_id="sess2", agent_id="agent1")
        store.save_session(rec)
        # Should not raise; session is only in memory
        assert store.load_session("sess2") is rec


# ── load_session ─────────────────────────────────────────────────────


class TestLoadSession:
    def test_returns_none_for_nonexistent(self):
        store = Store()
        assert store.load_session("does-not-exist") is None

    def test_returns_none_for_nonexistent_with_data_dir(self, tmp_path):
        store = Store(data_dir=tmp_path)
        assert store.load_session("does-not-exist") is None

    def test_returns_correct_record_after_save(self, tmp_path):
        store = Store(data_dir=tmp_path)
        rec = SessionRecord(
            session_id="sess3",
            agent_id="agent2",
            messages=[{"role": "user", "content": "hello"}],
            metadata={"foo": "bar"},
        )
        store.save_session(rec)
        loaded = store.load_session("sess3")
        assert loaded is rec

    def test_loads_from_disk_when_not_in_memory(self, tmp_path):
        # Save with one store instance
        store1 = Store(data_dir=tmp_path)
        rec = SessionRecord(
            session_id="sess4",
            agent_id="agent3",
            messages=[{"role": "assistant", "content": "ok"}],
            metadata={"x": 1},
        )
        store1.save_session(rec)

        # Load with a fresh store instance (not in memory)
        store2 = Store(data_dir=tmp_path)
        loaded = store2.load_session("sess4")
        assert loaded is not None
        assert loaded.session_id == "sess4"
        assert loaded.agent_id == "agent3"
        assert loaded.messages == [{"role": "assistant", "content": "ok"}]
        assert loaded.metadata == {"x": 1}


# ── list_sessions ────────────────────────────────────────────────────


class TestListSessions:
    def test_list_all(self):
        store = Store()
        s1 = SessionRecord(session_id="s1", agent_id="a1")
        s2 = SessionRecord(session_id="s2", agent_id="a2")
        store.save_session(s1)
        store.save_session(s2)
        result = store.list_sessions()
        assert len(result) == 2

    def test_filter_by_agent_id(self):
        store = Store()
        s1 = SessionRecord(session_id="s1", agent_id="a1")
        s2 = SessionRecord(session_id="s2", agent_id="a2")
        s3 = SessionRecord(session_id="s3", agent_id="a1")
        store.save_session(s1)
        store.save_session(s2)
        store.save_session(s3)

        filtered = store.list_sessions(agent_id="a1")
        assert len(filtered) == 2
        assert all(s.agent_id == "a1" for s in filtered)

    def test_filter_empty_result(self):
        store = Store()
        s1 = SessionRecord(session_id="s1", agent_id="a1")
        store.save_session(s1)
        assert store.list_sessions(agent_id="nonexistent") == []


# ── delete_session ───────────────────────────────────────────────────


class TestDeleteSession:
    def test_removes_from_memory_and_disk(self, tmp_path):
        store = Store(data_dir=tmp_path)
        rec = SessionRecord(session_id="del1", agent_id="a1")
        store.save_session(rec)

        path = tmp_path / "sessions" / "del1.json"
        assert path.exists()

        result = store.delete_session("del1")
        assert result is True
        assert not path.exists()
        assert store.load_session("del1") is None

    def test_returns_false_for_missing(self):
        store = Store()
        assert store.delete_session("no-such-session") is False

    def test_returns_false_for_missing_with_data_dir(self, tmp_path):
        store = Store(data_dir=tmp_path)
        assert store.delete_session("no-such-session") is False

    def test_removes_from_memory_only(self):
        store = Store()
        rec = SessionRecord(session_id="del2", agent_id="a1")
        store.save_session(rec)
        result = store.delete_session("del2")
        assert result is True
        assert store.load_session("del2") is None
