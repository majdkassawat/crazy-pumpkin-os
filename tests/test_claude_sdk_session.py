"""Tests for ClaudeSDKAgent session persistence integration."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, AgentRole, SessionRecord, Task, TaskOutput
from crazypumpkin.framework.store import Store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs) -> Agent:
    defaults = {"name": "test-session-agent", "role": AgentRole.EXECUTION}
    defaults.update(kwargs)
    return Agent(**defaults)


def _make_task(title: str = "Do something", description: str = "A task.") -> Task:
    return Task(title=title, description=description, acceptance_criteria=["Done"])


def _fake_response(text: str = "OK"):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# __init__ accepts store and session_id
# ---------------------------------------------------------------------------

class TestInitAcceptsStoreAndSessionId:
    def test_accepts_store_param(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        assert agent._store is store

    def test_accepts_session_id_param(self):
        agent = ClaudeSDKAgent(_make_agent(), session_id="s1")
        assert agent._session_id == "s1"

    def test_defaults_to_none(self):
        agent = ClaudeSDKAgent(_make_agent())
        assert agent._store is None
        assert agent._session_id is None


# ---------------------------------------------------------------------------
# save_session
# ---------------------------------------------------------------------------

class TestSaveSession:
    def test_returns_session_id_string_when_store_configured(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        agent._history = [{"role": "user", "content": "hi"}]
        sid = agent.save_session()
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_returns_none_when_no_store(self):
        agent = ClaudeSDKAgent(_make_agent())
        result = agent.save_session()
        assert result is None

    def test_persists_history_to_store(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        agent._history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        sid = agent.save_session()
        loaded = store.load_session(sid)
        assert loaded is not None
        assert loaded.messages == agent._history

    def test_returns_same_session_id_on_repeated_calls(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        agent._history = [{"role": "user", "content": "a"}]
        sid1 = agent.save_session()
        agent._history.append({"role": "assistant", "content": "b"})
        sid2 = agent.save_session()
        assert sid1 == sid2


# ---------------------------------------------------------------------------
# restore_session
# ---------------------------------------------------------------------------

class TestRestoreSession:
    def test_populates_history_from_saved_session(self):
        store = Store()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        rec = SessionRecord(session_id="s1", agent_id="a1", messages=messages)
        store.save_session(rec)

        agent = ClaudeSDKAgent(_make_agent(), store=store)
        result = agent.restore_session("s1")
        assert result is True
        assert agent._history == messages

    def test_returns_false_when_not_found(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        result = agent.restore_session("nonexistent")
        assert result is False
        assert agent._history == []

    def test_returns_false_when_no_store(self):
        agent = ClaudeSDKAgent(_make_agent())
        result = agent.restore_session("any-id")
        assert result is False


# ---------------------------------------------------------------------------
# Auto-save after execute()
# ---------------------------------------------------------------------------

class TestAutoSaveAfterExecute:
    @mock.patch("anthropic.Anthropic")
    def test_session_auto_saved_after_execute(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("done")

        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        agent.execute(_make_task(), {})

        # A session should have been saved
        assert agent._session_id is not None
        loaded = store.load_session(agent._session_id)
        assert loaded is not None
        assert len(loaded.messages) == 2  # user + assistant

    @mock.patch("anthropic.Anthropic")
    def test_no_auto_save_without_store(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("done")

        agent = ClaudeSDKAgent(_make_agent())
        agent.execute(_make_task(), {})

        assert agent._session_id is None


# ---------------------------------------------------------------------------
# Auto-restore on construction
# ---------------------------------------------------------------------------

class TestAutoRestoreOnConstruction:
    def test_auto_restores_when_both_store_and_session_id(self):
        store = Store()
        messages = [
            {"role": "user", "content": "prior turn"},
            {"role": "assistant", "content": "prior response"},
        ]
        rec = SessionRecord(session_id="restore-me", agent_id="a1", messages=messages)
        store.save_session(rec)

        agent = ClaudeSDKAgent(_make_agent(), store=store, session_id="restore-me")
        assert agent._history == messages

    def test_no_restore_without_store(self):
        agent = ClaudeSDKAgent(_make_agent(), session_id="s1")
        assert agent._history == []

    def test_no_restore_without_session_id(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store)
        assert agent._history == []

    def test_missing_session_id_leaves_history_empty(self):
        store = Store()
        agent = ClaudeSDKAgent(_make_agent(), store=store, session_id="nonexistent")
        assert agent._history == []
