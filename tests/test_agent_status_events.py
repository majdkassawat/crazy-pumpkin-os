"""Tests for AgentStatusEvent and emit_agent_status integration."""

import sys
from pathlib import Path
from typing import Any

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.events import (
    AgentStatusEvent,
    EventBus,
    default_event_bus,
    emit_agent_status,
    subscribe_agent_status,
    _status_handlers,
)
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


# ── AgentStatusEvent dataclass tests ────────────────────────────────


class TestAgentStatusEventDataclass:
    """AgentStatusEvent has all required fields with correct defaults."""

    def test_required_fields(self):
        evt = AgentStatusEvent(agent_id="a1", status="running")
        assert evt.agent_id == "a1"
        assert evt.status == "running"

    def test_optional_task_id_defaults_none(self):
        evt = AgentStatusEvent(agent_id="a1", status="idle")
        assert evt.task_id is None

    def test_timestamp_auto_populated(self):
        evt = AgentStatusEvent(agent_id="a1", status="idle")
        assert isinstance(evt.timestamp, float)
        assert evt.timestamp > 0

    def test_metadata_defaults_to_empty_dict(self):
        evt = AgentStatusEvent(agent_id="a1", status="idle")
        assert evt.metadata == {}

    def test_all_fields_settable(self):
        evt = AgentStatusEvent(
            agent_id="a1",
            status="error",
            task_id="t1",
            timestamp=123.0,
            metadata={"key": "value"},
        )
        assert evt.agent_id == "a1"
        assert evt.status == "error"
        assert evt.task_id == "t1"
        assert evt.timestamp == 123.0
        assert evt.metadata == {"key": "value"}


# ── emit_agent_status tests ─────────────────────────────────────────


class TestEmitAgentStatus:
    """emit_agent_status publishes to the default EventBus and notifies status handlers."""

    @pytest.fixture(autouse=True)
    def _clear_handlers(self):
        """Ensure status handlers are clean before/after each test."""
        original = _status_handlers.copy()
        _status_handlers.clear()
        yield
        _status_handlers.clear()
        _status_handlers.extend(original)

    def test_emits_to_default_event_bus(self):
        received = []
        default_event_bus.subscribe("agent_status", lambda e: received.append(e))

        emit_agent_status("agent-1", "running", task_id="t1")

        assert len(received) == 1
        assert received[0].agent_id == "agent-1"
        assert received[0].action == "agent_status"
        assert received[0].metadata["status"] == "running"
        assert received[0].metadata["task_id"] == "t1"

    def test_dispatches_to_status_handlers(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        emit_agent_status("agent-2", "error", task_id="t2", reason="timeout")

        assert len(captured) == 1
        evt = captured[0]
        assert evt.agent_id == "agent-2"
        assert evt.status == "error"
        assert evt.task_id == "t2"
        assert evt.metadata["reason"] == "timeout"

    def test_emit_without_task_id(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        emit_agent_status("agent-3", "idle")

        assert captured[0].task_id is None

    def test_metadata_kwargs_forwarded(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        emit_agent_status("a", "stopped", foo="bar", count=42)

        assert captured[0].metadata == {"foo": "bar", "count": 42}


# ── Agent integration tests ─────────────────────────────────────────


class _StubAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    def __init__(self, *, fail: bool = False):
        super().__init__(Agent(name="stub", role=AgentRole.EXECUTION))
        self._fail = fail

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        if self._fail:
            raise RuntimeError("boom")
        return TaskOutput(content="done")


class TestAgentRunEmitsStatusEvents:
    """BaseAgent.run() emits running/idle/error status events."""

    @pytest.fixture(autouse=True)
    def _clear_handlers(self):
        original = _status_handlers.copy()
        _status_handlers.clear()
        yield
        _status_handlers.clear()
        _status_handlers.extend(original)

    def test_successful_run_emits_running_then_idle(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        agent = _StubAgent()
        task = Task(title="test task")
        agent.run(task, {})

        statuses = [e.status for e in captured]
        assert statuses == ["running", "idle"]
        assert all(e.task_id == task.id for e in captured)
        assert all(e.agent_id == agent.id for e in captured)

    def test_failed_run_emits_running_then_error(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        agent = _StubAgent(fail=True)
        task = Task(title="fail task")

        with pytest.raises(RuntimeError, match="boom"):
            agent.run(task, {})

        statuses = [e.status for e in captured]
        assert statuses == ["running", "error"]
        assert all(e.task_id == task.id for e in captured)

    def test_events_have_timestamps(self):
        captured: list[AgentStatusEvent] = []
        subscribe_agent_status(lambda e: captured.append(e))

        _StubAgent().run(Task(title="t"), {})

        assert len(captured) == 2
        assert captured[0].timestamp <= captured[1].timestamp
