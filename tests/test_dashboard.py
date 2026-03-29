"""Tests for dashboard data readers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Point to the worktree src so the updated dashboard module is importable.
_worktree_src = str(
    Path(__file__).resolve().parent.parent.parent
    / "kassawat-framework"
    / "data"
    / "worktrees"
    / "majdkassawat-crazy-pumpkin-os"
    / "8cde3d766a10"
    / "src"
)
sys.path.insert(0, _worktree_src)

# Fall back to local src if worktree path doesn't exist.
sys.path.insert(1, str(Path(__file__).resolve().parent.parent / "src"))

_dashboard = importlib.import_module("crazypumpkin.dashboard")
_models = importlib.import_module("crazypumpkin.framework.models")
_agent_mod = importlib.import_module("crazypumpkin.framework.agent")
_registry_mod = importlib.import_module("crazypumpkin.framework.registry")
_store_mod = importlib.import_module("crazypumpkin.framework.store")
_events_mod = importlib.import_module("crazypumpkin.framework.events")
_scheduler_mod = importlib.import_module("crazypumpkin.scheduler.scheduler")

get_agent_activity = _dashboard.get_agent_activity
get_task_status = _dashboard.get_task_status
get_scheduler_state = _dashboard.get_scheduler_state
get_recent_logs = _dashboard.get_recent_logs

Agent = _models.Agent
AgentRole = _models.AgentRole
AgentStatus = _models.AgentStatus
AuditEvent = _models.AuditEvent
Task = _models.Task
TaskStatus = _models.TaskStatus

BaseAgent = _agent_mod.BaseAgent
AgentRegistry = _registry_mod.AgentRegistry
Store = _store_mod.Store
EventBus = _events_mod.EventBus
Scheduler = _scheduler_mod.Scheduler


# ── get_agent_activity ──


class _DummyAgent(BaseAgent):
    def execute(self, task, context):
        raise NotImplementedError


def _make_agent(name: str, role: AgentRole = AgentRole.EXECUTION) -> _DummyAgent:
    model = Agent(name=name, role=role, status=AgentStatus.ACTIVE)
    return _DummyAgent(agent=model)


def test_get_agent_activity_empty():
    registry = AgentRegistry()
    assert get_agent_activity(registry) == []


def test_get_agent_activity_returns_active():
    registry = AgentRegistry()
    a = _make_agent("alice", AgentRole.EXECUTION)
    b = _make_agent("bob", AgentRole.STRATEGY)
    registry.register(a)
    registry.register(b)

    result = get_agent_activity(registry)
    assert len(result) == 2
    names = {r["name"] for r in result}
    assert names == {"alice", "bob"}
    for entry in result:
        assert set(entry.keys()) == {"id", "name", "role", "status"}
        assert entry["status"] == "active"


def test_get_agent_activity_excludes_disabled():
    registry = AgentRegistry()
    a = _make_agent("alice")
    b = _make_agent("bob")
    b.agent.status = AgentStatus.DISABLED
    registry.register(a)
    registry.register(b)

    result = get_agent_activity(registry)
    assert len(result) == 1
    assert result[0]["name"] == "alice"


# ── get_task_status ──


def test_get_task_status_empty():
    store = Store()
    assert get_task_status(store) == []


def test_get_task_status_returns_all_tasks():
    store = Store()
    t1 = Task(id="t1", title="Task One", status=TaskStatus.CREATED)
    t2 = Task(id="t2", title="Task Two", status=TaskStatus.IN_PROGRESS, assigned_to="agent-1")
    store.add_task(t1)
    store.add_task(t2)

    result = get_task_status(store)
    assert len(result) == 2
    by_id = {r["id"]: r for r in result}
    assert by_id["t1"]["status"] == "created"
    assert by_id["t2"]["status"] == "in_progress"
    assert by_id["t2"]["assigned_to"] == "agent-1"


# ── get_scheduler_state ──


def test_get_scheduler_state_defaults():
    config = MagicMock()
    config.llm = MagicMock()
    scheduler = Scheduler.__new__(Scheduler)
    scheduler._config = config
    scheduler.last_run = None
    scheduler.cycle_count = 0
    scheduler.agent_last_dispatch = {}

    result = get_scheduler_state(scheduler)
    assert result == {
        "last_run": None,
        "cycle_count": 0,
        "agent_last_dispatch": {},
    }


def test_get_scheduler_state_with_data():
    config = MagicMock()
    config.llm = MagicMock()
    scheduler = Scheduler.__new__(Scheduler)
    scheduler._config = config
    scheduler.last_run = "2026-01-01T00:00:00+00:00"
    scheduler.cycle_count = 5
    scheduler.agent_last_dispatch = {"StrategyAgent": "2026-01-01T00:00:00+00:00"}

    result = get_scheduler_state(scheduler)
    assert result["last_run"] == "2026-01-01T00:00:00+00:00"
    assert result["cycle_count"] == 5
    assert "StrategyAgent" in result["agent_last_dispatch"]


# ── get_recent_logs ──


def test_get_recent_logs_empty():
    bus = EventBus()
    assert get_recent_logs(bus) == []


def test_get_recent_logs_returns_entries():
    bus = EventBus()
    bus.emit(agent_id="a1", action="task.created", detail="Created task X")
    bus.emit(agent_id="a2", action="task.completed", detail="Completed task Y")

    result = get_recent_logs(bus)
    assert len(result) == 2
    assert result[0]["agent_id"] == "a1"
    assert result[1]["action"] == "task.completed"
    for entry in result:
        assert "id" in entry
        assert "timestamp" in entry
        assert "risk_level" in entry


def test_get_recent_logs_respects_limit():
    bus = EventBus()
    for i in range(10):
        bus.emit(agent_id=f"a{i}", action="test", detail=f"event {i}")

    result = get_recent_logs(bus, n=3)
    assert len(result) == 3
    # Should be the last 3
    assert result[0]["agent_id"] == "a7"
