"""Tests for SessionRecord dataclass completeness and defaults."""

import importlib
import sys
from dataclasses import fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_models = importlib.import_module("crazypumpkin.framework.models")
SessionRecord = _models.SessionRecord
_uid = _models._uid
_now = _models._now


class TestSessionRecordExists:
    """SessionRecord dataclass exists and is importable."""

    def test_importable(self):
        assert SessionRecord is not None

    def test_is_dataclass(self):
        assert hasattr(SessionRecord, "__dataclass_fields__")


class TestSessionRecordFields:
    """SessionRecord has all required fields with correct types."""

    EXPECTED_FIELDS = {
        "session_id", "agent_id", "messages",
        "created_at", "updated_at", "metadata",
    }

    def test_has_all_fields(self):
        actual = {f.name for f in fields(SessionRecord)}
        assert self.EXPECTED_FIELDS == actual

    def test_session_id_type(self):
        assert SessionRecord.__dataclass_fields__["session_id"].type == "str"

    def test_agent_id_type(self):
        assert SessionRecord.__dataclass_fields__["agent_id"].type == "str"

    def test_messages_type(self):
        msg_type = SessionRecord.__dataclass_fields__["messages"].type
        assert "list" in str(msg_type)

    def test_created_at_type(self):
        assert SessionRecord.__dataclass_fields__["created_at"].type == "str"

    def test_updated_at_type(self):
        assert SessionRecord.__dataclass_fields__["updated_at"].type == "str"

    def test_metadata_type(self):
        meta_type = SessionRecord.__dataclass_fields__["metadata"].type
        assert "dict" in str(meta_type)


class TestSessionRecordDefaults:
    """Default values are generated correctly."""

    def test_session_id_default_is_uid(self):
        rec = SessionRecord()
        assert isinstance(rec.session_id, str)
        assert len(rec.session_id) > 0

    def test_session_id_unique(self):
        a = SessionRecord()
        b = SessionRecord()
        assert a.session_id != b.session_id

    def test_agent_id_default_empty(self):
        assert SessionRecord().agent_id == ""

    def test_messages_default_empty_list(self):
        rec = SessionRecord()
        assert rec.messages == []
        assert isinstance(rec.messages, list)

    def test_messages_not_shared(self):
        a = SessionRecord()
        b = SessionRecord()
        a.messages.append({"role": "user", "content": "hi"})
        assert b.messages == []

    def test_created_at_default_is_now(self):
        rec = SessionRecord()
        assert isinstance(rec.created_at, str)
        assert len(rec.created_at) > 0

    def test_updated_at_default_is_now(self):
        rec = SessionRecord()
        assert isinstance(rec.updated_at, str)
        assert len(rec.updated_at) > 0

    def test_metadata_default_empty_dict(self):
        rec = SessionRecord()
        assert rec.metadata == {}
        assert isinstance(rec.metadata, dict)

    def test_metadata_not_shared(self):
        a = SessionRecord()
        b = SessionRecord()
        a.metadata["key"] = "val"
        assert b.metadata == {}


class TestSessionRecordCustomValues:
    """SessionRecord accepts custom values for all fields."""

    def test_custom_values(self):
        rec = SessionRecord(
            session_id="sid-1",
            agent_id="agent-1",
            messages=[{"role": "user", "content": "hello"}],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:01Z",
            metadata={"source": "test"},
        )
        assert rec.session_id == "sid-1"
        assert rec.agent_id == "agent-1"
        assert len(rec.messages) == 1
        assert rec.created_at == "2026-01-01T00:00:00Z"
        assert rec.updated_at == "2026-01-01T00:00:01Z"
        assert rec.metadata["source"] == "test"
