"""Tests for BaseAgent session integration."""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.events import EventBus
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.framework.store import Store


class _DummyAgent(BaseAgent):
    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        return TaskOutput(content="ok")


@pytest.fixture
def store(tmp_path):
    return Store(data_dir=tmp_path)


@pytest.fixture
def agent(store):
    return _DummyAgent(
        Agent(name="test-agent", role=AgentRole.EXECUTION),
        event_bus=EventBus(),
        store=store,
    )


class TestStartSession:
    def test_session_created(self, agent, store):
        session = agent.start_session()
        assert session is not None
        assert session.session_id
        assert session.agent_name == "test-agent"
        assert session.status == "active"
        assert store.get_session(session.session_id) is not None


class TestResumeSession:
    def test_same_session_id(self, agent):
        session = agent.start_session()
        resumed = agent.resume_session(session.session_id)
        assert resumed.session_id == session.session_id


class TestAddMessagePersists:
    def test_message_in_store(self, agent, store):
        session = agent.start_session()
        agent.add_message(session.session_id, "user", "hello world")
        loaded = store.get_session(session.session_id)
        assert len(loaded.messages) == 1
        assert loaded.messages[0].role == "user"
        assert loaded.messages[0].content == "hello world"


class TestEndSession:
    def test_status_completed(self, agent, store):
        session = agent.start_session()
        agent.end_session(session.session_id, status="completed")
        loaded = store.get_session(session.session_id)
        assert loaded.status == "completed"


class TestGetSessionContextTruncation:
    def test_truncation(self, agent, store):
        session = agent.start_session()
        for i in range(30):
            agent.add_message(session.session_id, "user", f"msg-{i}")
        context = agent.get_session_context(session.session_id, max_messages=10)
        assert len(context) == 10
        # Should return the last 10 messages
        assert context[0].content == "msg-20"
        assert context[-1].content == "msg-29"
