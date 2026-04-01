"""Tests for AgentSession model and session store."""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.models import AgentSession, SessionMessage
from crazypumpkin.framework.store import Store


def test_session_defaults():
    s = AgentSession(agent_name="test-agent")
    assert s.agent_name == "test-agent"
    assert s.status == "active"
    assert s.messages == []
    assert s.max_turns == 50
    assert s.session_id  # non-empty


def test_add_message():
    s = AgentSession(agent_name="a")
    s.add_message("user", "hello")
    assert len(s.messages) == 1
    assert s.messages[0].role == "user"
    assert s.messages[0].content == "hello"


def test_add_message_exceeds_max_turns():
    s = AgentSession(agent_name="a", max_turns=1)
    s.add_message("user", "hi")
    with pytest.raises(ValueError, match="max_turns"):
        s.add_message("user", "again")


def test_add_message_inactive_session():
    s = AgentSession(agent_name="a")
    s.expire()
    with pytest.raises(ValueError, match="expired"):
        s.add_message("user", "hi")


def test_expire():
    s = AgentSession(agent_name="a")
    s.expire()
    assert s.status == "expired"


def test_store_save_load_session():
    with tempfile.TemporaryDirectory() as td:
        store = Store(data_dir=Path(td))
        s = AgentSession(agent_name="bot")
        s.add_message("user", "test")
        store.save_session(s)
        loaded = store.load_session(s.session_id)
        assert loaded is not None
        assert loaded.agent_name == "bot"
        assert len(loaded.messages) == 1


def test_store_get_or_create_session_creates_new():
    with tempfile.TemporaryDirectory() as td:
        store = Store(data_dir=Path(td))
        s = store.get_or_create_session("new-agent")
        assert s.agent_name == "new-agent"
        assert s.status == "active"


def test_store_get_or_create_session_returns_existing():
    with tempfile.TemporaryDirectory() as td:
        store = Store(data_dir=Path(td))
        s1 = store.get_or_create_session("bot")
        s2 = store.get_or_create_session("bot")
        assert s1.session_id == s2.session_id
