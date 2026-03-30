"""Agent lifecycle management — start, stop, restart, and health-check agents."""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from crazypumpkin.framework.models import AgentStatus

if TYPE_CHECKING:
    from crazypumpkin.framework.registry import AgentRegistry

logger = logging.getLogger("crazypumpkin.lifecycle")


class LifecycleState(str, Enum):
    """Observable lifecycle state for an agent."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERRORED = "errored"


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
