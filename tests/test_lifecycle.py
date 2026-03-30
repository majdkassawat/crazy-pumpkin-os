"""Tests for agent lifecycle management."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.lifecycle import (
    AgentLifecycleError,
    AgentNotFoundError,
    LifecycleState,
    MaxRestartsExceededError,
    RestartConfig,
    RestartPolicy,
    RestartState,
    health_check,
    managed_restart,
    restart_agent,
    should_restart,
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


# ---------------------------------------------------------------------------
# RestartPolicy enum
# ---------------------------------------------------------------------------

class TestRestartPolicy:
    def test_values(self):
        assert RestartPolicy.ALWAYS.value == "always"
        assert RestartPolicy.ON_FAILURE.value == "on-failure"
        assert RestartPolicy.NEVER.value == "never"

    def test_members(self):
        assert set(RestartPolicy) == {
            RestartPolicy.ALWAYS,
            RestartPolicy.ON_FAILURE,
            RestartPolicy.NEVER,
        }


# ---------------------------------------------------------------------------
# RestartConfig defaults
# ---------------------------------------------------------------------------

class TestRestartConfig:
    def test_defaults(self):
        cfg = RestartConfig()
        assert cfg.policy == RestartPolicy.NEVER
        assert cfg.max_restarts == 3
        assert cfg.backoff_base == 1.0
        assert cfg.backoff_max == 60.0

    def test_custom(self):
        cfg = RestartConfig(
            policy=RestartPolicy.ALWAYS,
            max_restarts=5,
            backoff_base=2.0,
            backoff_max=120.0,
        )
        assert cfg.policy == RestartPolicy.ALWAYS
        assert cfg.max_restarts == 5
        assert cfg.backoff_base == 2.0
        assert cfg.backoff_max == 120.0


# ---------------------------------------------------------------------------
# RestartState & backoff
# ---------------------------------------------------------------------------

class TestRestartState:
    def test_initial_state(self):
        state = RestartState()
        assert state.attempt == 0

    def test_record_attempt(self):
        state = RestartState()
        state.record_attempt()
        assert state.attempt == 1
        state.record_attempt()
        assert state.attempt == 2

    def test_reset(self):
        state = RestartState()
        state.record_attempt()
        state.record_attempt()
        state.reset()
        assert state.attempt == 0

    def test_compute_backoff_exponential(self):
        cfg = RestartConfig(backoff_base=1.0, backoff_max=60.0)
        state = RestartState()
        assert state.compute_backoff(cfg) == 1.0   # 1 * 2^0
        state.record_attempt()
        assert state.compute_backoff(cfg) == 2.0   # 1 * 2^1
        state.record_attempt()
        assert state.compute_backoff(cfg) == 4.0   # 1 * 2^2
        state.record_attempt()
        assert state.compute_backoff(cfg) == 8.0   # 1 * 2^3

    def test_compute_backoff_capped_at_max(self):
        cfg = RestartConfig(backoff_base=1.0, backoff_max=5.0)
        state = RestartState()
        state.attempt = 10  # 1 * 2^10 = 1024, but capped at 5
        assert state.compute_backoff(cfg) == 5.0

    def test_compute_backoff_custom_base(self):
        cfg = RestartConfig(backoff_base=0.5, backoff_max=60.0)
        state = RestartState()
        assert state.compute_backoff(cfg) == 0.5   # 0.5 * 2^0
        state.record_attempt()
        assert state.compute_backoff(cfg) == 1.0   # 0.5 * 2^1

    def test_wait_uses_injected_sleep(self):
        calls = []
        state = RestartState(_sleep=lambda d: calls.append(d))
        state.wait(2.5)
        assert calls == [2.5]


# ---------------------------------------------------------------------------
# should_restart
# ---------------------------------------------------------------------------

class TestShouldRestart:
    def test_never_policy(self):
        cfg = RestartConfig(policy=RestartPolicy.NEVER)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.ERRORED) is False
        assert should_restart(cfg, state, LifecycleState.STOPPED) is False

    def test_always_restarts_on_error(self):
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=5)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.ERRORED) is True

    def test_always_restarts_on_stopped(self):
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=5)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.STOPPED) is True

    def test_always_does_not_restart_running(self):
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=5)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.RUNNING) is False

    def test_on_failure_restarts_on_error(self):
        cfg = RestartConfig(policy=RestartPolicy.ON_FAILURE, max_restarts=5)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.ERRORED) is True

    def test_on_failure_does_not_restart_on_stopped(self):
        cfg = RestartConfig(policy=RestartPolicy.ON_FAILURE, max_restarts=5)
        state = RestartState()
        assert should_restart(cfg, state, LifecycleState.STOPPED) is False

    def test_max_restarts_exceeded(self):
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=2)
        state = RestartState()
        state.attempt = 2
        assert should_restart(cfg, state, LifecycleState.ERRORED) is False

    def test_max_restarts_zero_means_unlimited(self):
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=0)
        state = RestartState()
        state.attempt = 100
        assert should_restart(cfg, state, LifecycleState.ERRORED) is True


# ---------------------------------------------------------------------------
# managed_restart
# ---------------------------------------------------------------------------

class TestManagedRestart:
    def _noop_sleep(self, _d):
        """No-op sleep for tests."""

    def test_always_restarts_errored_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.DISABLED)
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=3)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE
        assert state.attempt == 1

    def test_always_restarts_stopped_agent(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.IDLE)
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=3)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.RUNNING
        assert stub.agent.status == AgentStatus.ACTIVE

    def test_on_failure_restarts_errored(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.DISABLED)
        cfg = RestartConfig(policy=RestartPolicy.ON_FAILURE, max_restarts=5)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.RUNNING

    def test_on_failure_does_not_restart_stopped(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.IDLE)
        cfg = RestartConfig(policy=RestartPolicy.ON_FAILURE, max_restarts=5)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.STOPPED

    def test_never_policy_does_not_restart(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.DISABLED)
        cfg = RestartConfig(policy=RestartPolicy.NEVER)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.ERRORED
        assert stub.agent.status == AgentStatus.DISABLED

    def test_max_restarts_exceeded_raises(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.DISABLED)
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=2)
        state = RestartState(_sleep=self._noop_sleep)
        state.attempt = 2
        with pytest.raises(MaxRestartsExceededError, match="exceeded max restarts"):
            managed_restart(registry, "a1", cfg, state)

    def test_backoff_delay_applied(self):
        registry, _ = _make_registry_with_agent(status=AgentStatus.DISABLED)
        cfg = RestartConfig(
            policy=RestartPolicy.ALWAYS,
            max_restarts=5,
            backoff_base=1.0,
            backoff_max=60.0,
        )
        delays = []
        state = RestartState(_sleep=lambda d: delays.append(d))

        managed_restart(registry, "a1", cfg, state)
        assert delays == [1.0]  # 1 * 2^0

        # Set back to errored to restart again
        registry._agents["a1"].agent.status = AgentStatus.DISABLED
        managed_restart(registry, "a1", cfg, state)
        assert delays == [1.0, 2.0]  # 1 * 2^1

        registry._agents["a1"].agent.status = AgentStatus.DISABLED
        managed_restart(registry, "a1", cfg, state)
        assert delays == [1.0, 2.0, 4.0]  # 1 * 2^2

    def test_managed_restart_running_agent_not_restarted(self):
        registry, stub = _make_registry_with_agent(status=AgentStatus.ACTIVE)
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS, max_restarts=3)
        state = RestartState(_sleep=self._noop_sleep)
        result = managed_restart(registry, "a1", cfg, state)
        assert result == LifecycleState.RUNNING
        assert state.attempt == 0  # no restart attempted

    def test_raises_agent_not_found(self):
        registry = AgentRegistry()
        cfg = RestartConfig(policy=RestartPolicy.ALWAYS)
        state = RestartState(_sleep=self._noop_sleep)
        with pytest.raises(AgentNotFoundError):
            managed_restart(registry, "missing", cfg, state)
