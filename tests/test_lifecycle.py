"""Tests for agent lifecycle management."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.lifecycle import (
    AgentLifecycleError,
    AgentNotFoundError,
    LifecycleState,
    health_check,
    restart_agent,
    start_agent,
    stop_agent,
)
from crazypumpkin.framework.models import Agent, AgentRole, AgentStatus
from crazypumpkin.framework.registry import AgentRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubAgent:
    """Minimal concrete BaseAgent for testing (avoids ABC restriction)."""

    def __init__(self, agent: Agent):
        self.agent = agent

    @property
    def id(self) -> str:
        return self.agent.id

    @property
    def name(self) -> str:
        return self.agent.name

    @property
    def role(self):
        return self.agent.role

    def execute(self, task, context):
        raise NotImplementedError

    def can_handle(self, task) -> bool:
        return True


def _make_registry_with_agent(
    agent_id: str = "a1",
    status: AgentStatus = AgentStatus.IDLE,
) -> tuple[AgentRegistry, _StubAgent]:
    """Create a registry with one stub agent at the given status."""
    model = Agent(id=agent_id, name="test-agent", role=AgentRole.EXECUTION, status=status)
    stub = _StubAgent(model)
    registry = AgentRegistry()
    registry._agents[agent_id] = stub
    return registry, stub


# ---------------------------------------------------------------------------
# start_agent
# ---------------------------------------------------------------------------

class TestStartAgent:
    def test_starts_idle_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.IDLE)
        result = start_agent(registry, "a1")
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE

    def test_raises_when_already_running(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.ACTIVE)
        with pytest.raises(AgentLifecycleError, match="already running"):
            start_agent(registry, "a1")

    def test_raises_when_agent_not_found(self):
        registry = AgentRegistry()
        with pytest.raises(AgentNotFoundError):
            start_agent(registry, "missing")

    def test_starts_disabled_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.DISABLED)
        result = start_agent(registry, "a1")
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE


# ---------------------------------------------------------------------------
# stop_agent
# ---------------------------------------------------------------------------

class TestStopAgent:
    def test_stops_running_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.ACTIVE)
        result = stop_agent(registry, "a1")
        assert result == LifecycleState.STOPPED
        assert stub.agent.status == AgentStatus.IDLE

    def test_raises_when_not_running(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.IDLE)
        with pytest.raises(AgentLifecycleError, match="not running"):
            stop_agent(registry, "a1")

    def test_raises_when_agent_not_found(self):
        registry = AgentRegistry()
        with pytest.raises(AgentNotFoundError):
            stop_agent(registry, "missing")


# ---------------------------------------------------------------------------
# restart_agent
# ---------------------------------------------------------------------------

class TestRestartAgent:
    def test_restart_running_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.ACTIVE)
        result = restart_agent(registry, "a1")
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE

    def test_restart_stopped_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.IDLE)
        result = restart_agent(registry, "a1")
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE

    def test_raises_when_agent_not_found(self):
        registry = AgentRegistry()
        with pytest.raises(AgentNotFoundError):
            restart_agent(registry, "missing")


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_running(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.ACTIVE)
        assert health_check(registry, "a1") == LifecycleState.RUNNING

    def test_stopped(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.IDLE)
        assert health_check(registry, "a1") == LifecycleState.STOPPED

    def test_errored(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.DISABLED)
        assert health_check(registry, "a1") == LifecycleState.ERRORED

    def test_raises_when_agent_not_found(self):
        registry = AgentRegistry()
        with pytest.raises(AgentNotFoundError):
            health_check(registry, "missing")
