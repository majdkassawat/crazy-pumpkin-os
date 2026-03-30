"""Tests for dashboard API endpoint (get_dashboard_data)."""

from __future__ import annotations

import json

from crazypumpkin.dashboard.api import get_agent_statuses, get_dashboard_data
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import (
    Agent,
    AgentRole,
    AgentStatus,
    Task,
    TaskStatus,
)
from crazypumpkin.framework.registry import AgentRegistry
from crazypumpkin.framework.store import Store


# ── Helpers ──


class _StubAgent(BaseAgent):
    def execute(self, task, context):
        raise NotImplementedError


def _agent(name: str, role: AgentRole = AgentRole.EXECUTION, status: AgentStatus = AgentStatus.ACTIVE) -> _StubAgent:
    return _StubAgent(agent=Agent(name=name, role=role, status=status))


def _task(tid: str, title: str, status: TaskStatus, assigned_to: str = "", updated_at: str = "") -> Task:
    t = Task(id=tid, title=title, status=status, assigned_to=assigned_to)
    if updated_at:
        t.updated_at = updated_at
    return t


# ── Structure & types ──


def test_returns_dict_with_required_sections():
    data = get_dashboard_data(AgentRegistry(), Store())
    assert isinstance(data, dict)
    assert "agents" in data
    assert "tasks" in data
    assert "errors" in data


def test_json_serializable():
    registry = AgentRegistry()
    registry.register(_agent("a1"))
    store = Store()
    store.add_task(_task("t1", "T", TaskStatus.COMPLETED))
    data = get_dashboard_data(registry, store)
    # Should not raise
    json.dumps(data)


def test_agents_field_is_list_of_dicts():
    registry = AgentRegistry()
    registry.register(_agent("alice"))
    data = get_dashboard_data(registry, Store())
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) == 1
    entry = data["agents"][0]
    assert isinstance(entry, dict)
    for key in ("id", "name", "role", "status"):
        assert key in entry
        assert isinstance(entry[key], str)


def test_tasks_field_structure():
    data = get_dashboard_data(AgentRegistry(), Store())
    tasks = data["tasks"]
    assert isinstance(tasks, dict)
    assert "counts" in tasks
    assert "recent_completions" in tasks
    assert isinstance(tasks["counts"], dict)
    assert isinstance(tasks["recent_completions"], list)


def test_errors_field_is_list():
    data = get_dashboard_data(AgentRegistry(), Store())
    assert isinstance(data["errors"], list)


# ── Agents ──


def test_agents_excludes_disabled():
    registry = AgentRegistry()
    registry.register(_agent("active-one"))
    registry.register(_agent("disabled-one", status=AgentStatus.DISABLED))
    data = get_dashboard_data(registry, Store())
    names = [a["name"] for a in data["agents"]]
    assert "active-one" in names
    assert "disabled-one" not in names


def test_agents_includes_role():
    registry = AgentRegistry()
    registry.register(_agent("strategist", role=AgentRole.STRATEGY))
    data = get_dashboard_data(registry, Store())
    assert data["agents"][0]["role"] == "strategy"


# ── Task counts ──


def test_task_counts_all_buckets_present():
    data = get_dashboard_data(AgentRegistry(), Store())
    counts = data["tasks"]["counts"]
    for bucket in ("planned", "in_progress", "completed", "failed"):
        assert bucket in counts
        assert isinstance(counts[bucket], int)


def test_task_counts_planned():
    store = Store()
    store.add_task(_task("t1", "A", TaskStatus.PLANNED))
    store.add_task(_task("t2", "B", TaskStatus.CREATED))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["tasks"]["counts"]["planned"] == 2


def test_task_counts_in_progress():
    store = Store()
    store.add_task(_task("t1", "A", TaskStatus.IN_PROGRESS))
    store.add_task(_task("t2", "B", TaskStatus.ASSIGNED))
    store.add_task(_task("t3", "C", TaskStatus.SUBMITTED_FOR_REVIEW))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["tasks"]["counts"]["in_progress"] == 3


def test_task_counts_completed():
    store = Store()
    store.add_task(_task("t1", "A", TaskStatus.COMPLETED))
    store.add_task(_task("t2", "B", TaskStatus.APPROVED))
    store.add_task(_task("t3", "C", TaskStatus.ARCHIVED))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["tasks"]["counts"]["completed"] == 3


def test_task_counts_failed():
    store = Store()
    store.add_task(_task("t1", "A", TaskStatus.REJECTED))
    store.add_task(_task("t2", "B", TaskStatus.ESCALATED))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["tasks"]["counts"]["failed"] == 2


# ── Recent completions ──


def test_recent_completions_includes_completed_tasks():
    store = Store()
    store.add_task(_task("t1", "Done task", TaskStatus.COMPLETED, updated_at="2026-03-01T00:00:00"))
    data = get_dashboard_data(AgentRegistry(), store)
    rc = data["tasks"]["recent_completions"]
    assert len(rc) == 1
    assert rc[0]["id"] == "t1"
    assert rc[0]["title"] == "Done task"
    assert "updated_at" in rc[0]


def test_recent_completions_excludes_non_completed():
    store = Store()
    store.add_task(_task("t1", "In progress", TaskStatus.IN_PROGRESS))
    store.add_task(_task("t2", "Planned", TaskStatus.PLANNED))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["tasks"]["recent_completions"] == []


def test_recent_completions_max_10():
    store = Store()
    for i in range(15):
        store.add_task(_task(f"t{i}", f"Task {i}", TaskStatus.COMPLETED, updated_at=f"2026-03-{i+1:02d}T00:00:00"))
    data = get_dashboard_data(AgentRegistry(), store)
    rc = data["tasks"]["recent_completions"]
    assert len(rc) == 10


def test_recent_completions_ordered_newest_first():
    store = Store()
    store.add_task(_task("old", "Old", TaskStatus.COMPLETED, updated_at="2026-01-01T00:00:00"))
    store.add_task(_task("new", "New", TaskStatus.COMPLETED, updated_at="2026-03-01T00:00:00"))
    data = get_dashboard_data(AgentRegistry(), store)
    rc = data["tasks"]["recent_completions"]
    assert rc[0]["id"] == "new"
    assert rc[1]["id"] == "old"


# ── Errors ──


def test_errors_contains_rejected_and_escalated():
    store = Store()
    store.add_task(_task("t1", "Bad task", TaskStatus.REJECTED, assigned_to="agent-x"))
    store.add_task(_task("t2", "Stuck task", TaskStatus.ESCALATED, assigned_to="agent-y"))
    data = get_dashboard_data(AgentRegistry(), store)
    errors = data["errors"]
    assert len(errors) == 2
    ids = {e["id"] for e in errors}
    assert ids == {"t1", "t2"}
    for e in errors:
        assert "id" in e
        assert "title" in e
        assert "status" in e
        assert "assigned_to" in e


def test_errors_excludes_healthy_tasks():
    store = Store()
    store.add_task(_task("t1", "OK", TaskStatus.COMPLETED))
    store.add_task(_task("t2", "WIP", TaskStatus.IN_PROGRESS))
    data = get_dashboard_data(AgentRegistry(), store)
    assert data["errors"] == []


# ── Empty state ──


def test_empty_state():
    data = get_dashboard_data(AgentRegistry(), Store())
    assert data["agents"] == []
    assert data["tasks"]["counts"] == {"planned": 0, "in_progress": 0, "completed": 0, "failed": 0}
    assert data["tasks"]["recent_completions"] == []
    assert data["errors"] == []


# ── get_agent_statuses (GET /api/agents/status) ──


def test_agent_statuses_returns_200_shape():
    """GET /api/agents/status returns list of agent status objects."""
    registry = AgentRegistry()
    registry.register(_agent("alice"))
    result = get_agent_statuses(registry)
    assert isinstance(result, list)
    assert len(result) == 1
    entry = result[0]
    assert isinstance(entry, dict)
    for key in ("name", "status", "last_heartbeat", "tasks_completed", "health"):
        assert key in entry


def test_agent_statuses_field_types():
    """Each agent object has correct field types."""
    registry = AgentRegistry()
    registry.register(_agent("bob"))
    entry = get_agent_statuses(registry)[0]
    assert isinstance(entry["name"], str)
    assert isinstance(entry["status"], str)
    assert entry["last_heartbeat"] is None or isinstance(entry["last_heartbeat"], str)
    assert isinstance(entry["tasks_completed"], int)
    assert isinstance(entry["health"], str)


def test_agent_statuses_empty_registry():
    """Endpoint returns empty list when no agents are registered."""
    assert get_agent_statuses(AgentRegistry()) == []


def test_agent_statuses_health_reflects_check():
    """Health field reflects actual health_check result for each agent."""
    registry = AgentRegistry()
    healthy = _agent("healthy-agent")
    registry.register(healthy)

    disabled = _agent("disabled-agent", status=AgentStatus.DISABLED)
    registry.register(disabled)

    result = get_agent_statuses(registry)
    by_name = {r["name"]: r for r in result}

    assert by_name["healthy-agent"]["health"] == "healthy"
    assert by_name["disabled-agent"]["health"] == "degraded"


def test_agent_statuses_includes_all_registered():
    """All registered agents appear in the result, including disabled."""
    registry = AgentRegistry()
    registry.register(_agent("a1"))
    registry.register(_agent("a2"))
    registry.register(_agent("a3", status=AgentStatus.DISABLED))
    result = get_agent_statuses(registry)
    assert len(result) == 3
    names = {r["name"] for r in result}
    assert names == {"a1", "a2", "a3"}


def test_agent_statuses_status_value():
    """Status field reflects the agent's current status string."""
    registry = AgentRegistry()
    registry.register(_agent("idle-one", status=AgentStatus.IDLE))
    result = get_agent_statuses(registry)
    assert result[0]["status"] == "idle"


def test_agent_statuses_json_serializable():
    """Agent status response must be JSON-serializable for the REST endpoint."""
    registry = AgentRegistry()
    registry.register(_agent("ser-agent"))
    registry.register(_agent("dis-agent", status=AgentStatus.DISABLED))
    result = get_agent_statuses(registry)
    # Should not raise
    json.dumps({"agents": result})
