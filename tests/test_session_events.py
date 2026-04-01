"""Tests for session lifecycle events emitted by BaseAgent."""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.events import (
    EventBus,
    SESSION_ENDED,
    SESSION_MESSAGE_ADDED,
    SESSION_RESUMED,
    SESSION_STARTED,
)
from crazypumpkin.framework.models import Agent, AgentRole, AuditEvent, Task, TaskOutput
from crazypumpkin.framework.store import Store


# -- Helpers ------------------------------------------------------------------


class _DummyAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        return TaskOutput(content="ok")


def _make_agent(event_bus: EventBus, store: Store) -> _DummyAgent:
    return _DummyAgent(
        Agent(name="test-agent", role=AgentRole.EXECUTION),
        event_bus=event_bus,
        store=store,
    )


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def agent(bus, store):
    return _make_agent(bus, store)


@pytest.fixture
def captured_events(bus):
    """Return a list that accumulates all emitted events."""
    events: list[AuditEvent] = []
    bus.subscribe_all(lambda e: events.append(e))
    return events


# -- SESSION_STARTED ----------------------------------------------------------


class TestSessionStarted:
    def test_event_emitted(self, agent, captured_events):
        agent.start_session()
        assert len(captured_events) == 1
        assert captured_events[0].action == SESSION_STARTED

    def test_payload_contains_session_id(self, agent, captured_events):
        session = agent.start_session()
        meta = captured_events[0].metadata
        assert meta["session_id"] == session.session_id

    def test_payload_contains_agent_name(self, agent, captured_events):
        agent.start_session()
        meta = captured_events[0].metadata
        assert meta["agent_name"] == "test-agent"

    def test_entity_type_is_session(self, agent, captured_events):
        agent.start_session()
        assert captured_events[0].entity_type == "session"

    def test_entity_id_matches_session(self, agent, captured_events):
        session = agent.start_session()
        assert captured_events[0].entity_id == session.session_id


# -- SESSION_RESUMED ----------------------------------------------------------


class TestSessionResumed:
    def test_event_emitted(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.resume_session(session.session_id)
        assert len(captured_events) == 1
        assert captured_events[0].action == SESSION_RESUMED

    def test_payload_contains_session_id(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.resume_session(session.session_id)
        assert captured_events[0].metadata["session_id"] == session.session_id

    def test_payload_contains_agent_name(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.resume_session(session.session_id)
        assert captured_events[0].metadata["agent_name"] == "test-agent"

    def test_payload_contains_message_count(self, agent, store, captured_events):
        session = agent.start_session()
        store.append_message(session.session_id, "user", "hello")
        store.append_message(session.session_id, "assistant", "hi")
        captured_events.clear()
        agent.resume_session(session.session_id)
        assert captured_events[0].metadata["message_count"] == 2

    def test_resume_nonexistent_session_raises(self, agent):
        with pytest.raises(KeyError):
            agent.resume_session("nonexistent")


# -- SESSION_MESSAGE_ADDED ---------------------------------------------------


class TestSessionMessageAdded:
    def test_event_emitted(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.add_message(session.session_id, "user", "hello")
        assert len(captured_events) == 1
        assert captured_events[0].action == SESSION_MESSAGE_ADDED

    def test_payload_contains_session_id(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.add_message(session.session_id, "user", "hello")
        assert captured_events[0].metadata["session_id"] == session.session_id

    def test_payload_contains_role(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.add_message(session.session_id, "assistant", "hi there")
        assert captured_events[0].metadata["role"] == "assistant"

    def test_message_stored_in_session(self, agent, store):
        session = agent.start_session()
        agent.add_message(session.session_id, "user", "hello")
        stored = store.get_session(session.session_id)
        assert len(stored.messages) == 1
        assert stored.messages[0].role == "user"
        assert stored.messages[0].content == "hello"


# -- SESSION_ENDED -----------------------------------------------------------


class TestSessionEnded:
    def test_event_emitted(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.end_session(session.session_id)
        assert len(captured_events) == 1
        assert captured_events[0].action == SESSION_ENDED

    def test_payload_contains_session_id(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.end_session(session.session_id)
        assert captured_events[0].metadata["session_id"] == session.session_id

    def test_payload_contains_status(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.end_session(session.session_id, status="closed")
        assert captured_events[0].metadata["status"] == "closed"

    def test_custom_status(self, agent, captured_events):
        session = agent.start_session()
        captured_events.clear()
        agent.end_session(session.session_id, status="error")
        assert captured_events[0].metadata["status"] == "error"

    def test_session_status_updated(self, agent, store):
        session = agent.start_session()
        agent.end_session(session.session_id, status="closed")
        stored = store.get_session(session.session_id)
        assert stored.status == "closed"

    def test_end_nonexistent_session_raises(self, agent):
        with pytest.raises(KeyError):
            agent.end_session("nonexistent")


# -- Full lifecycle -----------------------------------------------------------


class TestFullLifecycle:
    def test_start_message_end(self, agent, captured_events):
        session = agent.start_session()
        agent.add_message(session.session_id, "user", "hello")
        agent.add_message(session.session_id, "assistant", "hi")
        agent.end_session(session.session_id)

        actions = [e.action for e in captured_events]
        assert actions == [
            SESSION_STARTED,
            SESSION_MESSAGE_ADDED,
            SESSION_MESSAGE_ADDED,
            SESSION_ENDED,
        ]

    def test_start_resume_end(self, agent, captured_events):
        session = agent.start_session()
        agent.resume_session(session.session_id)
        agent.end_session(session.session_id)

        actions = [e.action for e in captured_events]
        assert actions == [SESSION_STARTED, SESSION_RESUMED, SESSION_ENDED]
