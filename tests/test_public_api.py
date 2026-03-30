"""Tests for lifecycle hooks, teardown-on-error, and @register_agent decorator."""

import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput, deterministic_id
from crazypumpkin.framework.registry import AgentRegistry, default_registry, register_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task() -> Task:
    return Task(id="t1", project_id="p1", title="Test task")


def _make_context() -> dict[str, Any]:
    return {"project": "test"}


class RecordingAgent(BaseAgent):
    """Agent that records lifecycle call order."""

    def __init__(self, agent: Agent | None = None):
        if agent is None:
            agent = Agent(name="recorder", role=AgentRole.EXECUTION)
        super().__init__(agent)
        self.calls: list[str] = []

    def setup(self, context: dict[str, Any]) -> None:
        self.calls.append("setup")

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        self.calls.append("execute")
        return TaskOutput(content="done")

    def teardown(self, context: dict[str, Any]) -> None:
        self.calls.append("teardown")


class FailingAgent(RecordingAgent):
    """Agent whose execute() raises."""

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        self.calls.append("execute")
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Tests — lifecycle hook invocation order
# ---------------------------------------------------------------------------


class TestLifecycleOrder:
    """run() calls setup, execute, teardown in that order."""

    def test_run_calls_setup_execute_teardown_in_order(self):
        agent = RecordingAgent()
        agent.run(_make_task(), _make_context())
        assert agent.calls == ["setup", "execute", "teardown"]

    def test_run_returns_execute_result(self):
        agent = RecordingAgent()
        result = agent.run(_make_task(), _make_context())
        assert result.content == "done"


# ---------------------------------------------------------------------------
# Tests — teardown-on-error guarantee
# ---------------------------------------------------------------------------


class TestTeardownOnError:
    """teardown() runs even when execute() raises."""

    def test_teardown_runs_when_execute_raises(self):
        agent = FailingAgent()
        with pytest.raises(RuntimeError, match="boom"):
            agent.run(_make_task(), _make_context())
        assert "teardown" in agent.calls

    def test_full_order_on_error(self):
        agent = FailingAgent()
        with pytest.raises(RuntimeError):
            agent.run(_make_task(), _make_context())
        assert agent.calls == ["setup", "execute", "teardown"]


# ---------------------------------------------------------------------------
# Tests — @register_agent decorator
# ---------------------------------------------------------------------------


class TestRegisterAgentDecorator:
    """@register_agent creates and registers agents correctly."""

    def setup_method(self):
        # Clear default registry before each test
        default_registry._agents.clear()

    def test_decorator_registers_agent_retrievable_by_name(self):
        @register_agent(name="test-agent", role=AgentRole.EXECUTION)
        class MyAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        found = default_registry.by_name("test-agent")
        assert found is not None
        assert found.name == "test-agent"

    def test_decorator_sets_correct_role(self):
        @register_agent(name="strat-agent", role=AgentRole.STRATEGY)
        class StratAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        found = default_registry.by_name("strat-agent")
        assert found is not None
        assert found.role == AgentRole.STRATEGY

    def test_decorator_sets_deterministic_id(self):
        @register_agent(name="det-agent", role=AgentRole.EXECUTION)
        class DetAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        expected_id = deterministic_id("det-agent")
        found = default_registry.get(expected_id)
        assert found is not None
        assert found.id == expected_id

    def test_decorator_returns_original_class(self):
        @register_agent(name="cls-agent", role=AgentRole.EXECUTION)
        class ClsAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        assert isinstance(ClsAgent, type)
        assert issubclass(ClsAgent, BaseAgent)

    def test_decorator_rejects_non_base_agent(self):
        with pytest.raises(TypeError, match="BaseAgent subclasses"):
            @register_agent(name="bad", role=AgentRole.EXECUTION)
            class NotAnAgent:
                pass


# ---------------------------------------------------------------------------
# Tests — registry retrieval by name and role
# ---------------------------------------------------------------------------


class TestRegistryRetrieval:
    """Registered agents can be retrieved by name/role from the default registry."""

    def setup_method(self):
        default_registry._agents.clear()

    def test_retrieve_by_name(self):
        @register_agent(name="lookup-agent", role=AgentRole.REVIEWER)
        class LookupAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        assert default_registry.by_name("lookup-agent") is not None
        assert default_registry.by_name("nonexistent") is None

    def test_retrieve_by_role(self):
        @register_agent(name="exec-agent", role=AgentRole.EXECUTION)
        class ExecAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        agents = default_registry.by_role(AgentRole.EXECUTION)
        assert len(agents) == 1
        assert agents[0].name == "exec-agent"

    def test_retrieve_by_id(self):
        @register_agent(name="id-agent", role=AgentRole.EXECUTION)
        class IdAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="ok")

        agent_id = deterministic_id("id-agent")
        assert default_registry.get(agent_id) is not None
