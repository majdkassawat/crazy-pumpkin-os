"""Agent lifecycle management — start, stop, restart, and health-check agents."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from crazypumpkin.framework.models import AgentStatus, RunRecord

if TYPE_CHECKING:
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

logger = logging.getLogger("crazypumpkin.lifecycle")


class LifecycleState(str, Enum):
    """Observable lifecycle state for an agent."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERRORED = "errored"


class RestartPolicy(str, Enum):
    """Restart policy for an agent."""

    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NEVER = "never"


@dataclass
class RestartConfig:
    """Configuration for agent restart behaviour.

    Attributes:
        policy: When the agent should be restarted.
        max_restarts: Maximum number of restart attempts (0 = unlimited).
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum delay in seconds between restart attempts.
    """

    policy: RestartPolicy = RestartPolicy.NEVER
    max_restarts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 60.0


@dataclass
class RestartState:
    """Mutable state tracking restart attempts for a single agent."""

    attempt: int = 0
    _sleep: object = field(default=None, repr=False)

    def compute_backoff(self, config: RestartConfig) -> float:
        """Return the delay for the current attempt using exponential backoff."""
        delay = config.backoff_base * (2 ** self.attempt)
        return min(delay, config.backoff_max)

    def record_attempt(self) -> None:
        """Increment the attempt counter."""
        self.attempt += 1

    def reset(self) -> None:
        """Reset the attempt counter (e.g. after a successful start)."""
        self.attempt = 0

    def wait(self, delay: float) -> None:
        """Sleep for *delay* seconds. Overridable via ``_sleep`` for testing."""
        sleeper = self._sleep or time.sleep
        sleeper(delay)


class MaxRestartsExceededError(Exception):
    """Raised when the restart attempt limit has been reached."""

    def __init__(self, agent_id: str, max_restarts: int) -> None:
        self.agent_id = agent_id
        self.max_restarts = max_restarts
        super().__init__(
            f"Agent '{agent_id}' exceeded max restarts ({max_restarts})"
        )


class AgentNotFoundError(Exception):
    """Raised when an agent ID is not present in the registry."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found in registry")


class AgentLifecycleError(Exception):
    """Raised when a lifecycle transition is invalid."""


def _resolve(registry: AgentRegistry, agent_id: str):
    """Look up an agent in the registry or raise."""
    agent = registry.get(agent_id)
    if agent is None:
        raise AgentNotFoundError(agent_id)
    return agent


def start_agent(registry: AgentRegistry, agent_id: str) -> LifecycleState:
    """Launch an agent and mark it as running.

    Args:
        registry: The agent registry to look up the agent.
        agent_id: Unique identifier of the agent.

    Returns:
        The new lifecycle state (RUNNING).

    Raises:
        AgentNotFoundError: If *agent_id* is not in the registry.
        AgentLifecycleError: If the agent is already running.
    """
    base_agent = _resolve(registry, agent_id)

    if base_agent.agent.status == AgentStatus.ACTIVE:
        raise AgentLifecycleError(
            f"Agent '{agent_id}' is already running"
        )

    base_agent.agent.status = AgentStatus.ACTIVE
    logger.info("Agent '%s' (%s) started", agent_id, base_agent.name)
    return LifecycleState.RUNNING


def stop_agent(registry: AgentRegistry, agent_id: str) -> LifecycleState:
    """Gracefully stop a running agent.

    Args:
        registry: The agent registry to look up the agent.
        agent_id: Unique identifier of the agent.

    Returns:
        The new lifecycle state (STOPPED).

    Raises:
        AgentNotFoundError: If *agent_id* is not in the registry.
        AgentLifecycleError: If the agent is not currently running.
    """
    base_agent = _resolve(registry, agent_id)

    if base_agent.agent.status != AgentStatus.ACTIVE:
        raise AgentLifecycleError(
            f"Agent '{agent_id}' is not running (status: {base_agent.agent.status.value})"
        )

    base_agent.agent.status = AgentStatus.IDLE
    logger.info("Agent '%s' (%s) stopped", agent_id, base_agent.name)
    return LifecycleState.STOPPED


def restart_agent(registry: AgentRegistry, agent_id: str) -> LifecycleState:
    """Stop then start an agent.

    If the agent is already stopped, it is simply started.

    Args:
        registry: The agent registry to look up the agent.
        agent_id: Unique identifier of the agent.

    Returns:
        The new lifecycle state (RUNNING).

    Raises:
        AgentNotFoundError: If *agent_id* is not in the registry.
    """
    base_agent = _resolve(registry, agent_id)

    if base_agent.agent.status == AgentStatus.ACTIVE:
        stop_agent(registry, agent_id)

    return start_agent(registry, agent_id)


def health_check(registry: AgentRegistry, agent_id: str) -> LifecycleState:
    """Return the current lifecycle state of an agent.

    Args:
        registry: The agent registry to look up the agent.
        agent_id: Unique identifier of the agent.

    Returns:
        RUNNING if the agent status is ACTIVE,
        STOPPED if IDLE,
        ERRORED if DISABLED.

    Raises:
        AgentNotFoundError: If *agent_id* is not in the registry.
    """
    base_agent = _resolve(registry, agent_id)

    status_map = {
        AgentStatus.ACTIVE: LifecycleState.RUNNING,
        AgentStatus.IDLE: LifecycleState.STOPPED,
        AgentStatus.DISABLED: LifecycleState.ERRORED,
    }
    return status_map.get(base_agent.agent.status, LifecycleState.ERRORED)


def should_restart(
    config: RestartConfig,
    state: RestartState,
    lifecycle_state: LifecycleState,
) -> bool:
    """Decide whether an agent should be restarted based on policy and limits.

    Args:
        config: The restart configuration for the agent.
        state: The current restart state tracking attempts.
        lifecycle_state: The current lifecycle state of the agent.

    Returns:
        True if the agent should be restarted, False otherwise.
    """
    if config.policy == RestartPolicy.NEVER:
        return False

    if config.max_restarts > 0 and state.attempt >= config.max_restarts:
        return False

    if config.policy == RestartPolicy.ALWAYS:
        return lifecycle_state in (LifecycleState.STOPPED, LifecycleState.ERRORED)

    if config.policy == RestartPolicy.ON_FAILURE:
        return lifecycle_state == LifecycleState.ERRORED

    return False


def managed_restart(
    registry: AgentRegistry,
    agent_id: str,
    config: RestartConfig,
    state: RestartState,
) -> LifecycleState:
    """Restart an agent according to the configured restart policy.

    Checks the policy and remaining attempts, applies exponential backoff,
    then restarts the agent.

    Args:
        registry: The agent registry to look up the agent.
        agent_id: Unique identifier of the agent.
        config: Restart configuration (policy, limits, backoff).
        state: Mutable restart state for tracking attempts.

    Returns:
        The new lifecycle state after the restart attempt.

    Raises:
        AgentNotFoundError: If *agent_id* is not in the registry.
        MaxRestartsExceededError: If the restart limit has been reached.
    """
    current = health_check(registry, agent_id)

    if not should_restart(config, state, current):
        if config.policy == RestartPolicy.NEVER:
            return current
        if config.max_restarts > 0 and state.attempt >= config.max_restarts:
            raise MaxRestartsExceededError(agent_id, config.max_restarts)
        return current

    delay = state.compute_backoff(config)
    logger.info(
        "Restarting agent '%s' (attempt %d, backoff %.1fs)",
        agent_id,
        state.attempt + 1,
        delay,
    )
    state.wait(delay)
    state.record_attempt()

    base_agent = _resolve(registry, agent_id)
    if base_agent.agent.status == AgentStatus.ACTIVE:
        stop_agent(registry, agent_id)

    return start_agent(registry, agent_id)


async def execute_run(
    registry: "AgentRegistry",
    agent_id: str,
    store: "Store",
    task=None,
    context=None,
) -> RunRecord:
    """Execute an agent run with full lifecycle tracking.

    Creates a RunRecord at the start (status='running'), executes the agent,
    then updates the record on completion (status='success') or failure
    (status='failure').
    """
    base_agent = _resolve(registry, agent_id)
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)

    record = RunRecord(
        run_id=run_id,
        agent_name=base_agent.name,
        started_at=started_at,
        status="running",
    )
    await store.save_run_record(record)

    try:
        start_agent(registry, agent_id)
        if task is not None:
            base_agent.execute(task, context)
        stop_agent(registry, agent_id)

        finished_at = datetime.now(timezone.utc)
        record.status = "success"
        record.finished_at = finished_at
        record.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        record.status = "failure"
        record.finished_at = finished_at
        record.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        record.error = str(exc)

    await store.save_run_record(record)
    return record
