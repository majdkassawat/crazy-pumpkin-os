"""
Agent registry — manages all agents and their roles.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from typing import Callable

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, AgentStatus, deterministic_id

if TYPE_CHECKING:
    from crazypumpkin.framework.store import Store

logger = logging.getLogger("crazypumpkin.registry")


class AgentRegistry:
    """Central registry of all agents in the organization."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.id] = agent

    def unregister(self, agent_id: str) -> BaseAgent | None:
        return self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def by_role(self, role: AgentRole) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.role == role and a.agent.status == AgentStatus.ACTIVE]

    def by_name(self, name: str) -> BaseAgent | None:
        for a in self._agents.values():
            if a.name == name:
                return a
        return None

    def all_active(self) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.agent.status == AgentStatus.ACTIVE]

    def active_ids(self) -> set[str]:
        """Return the set of all registered agent IDs."""
        return set(self._agents.keys())

    def purge_orphans(self, store: Store) -> dict[str, int]:
        """Remove stale agent data from *store* for IDs not in this registry."""
        return store.purge_orphaned_agents(self.active_ids())

    def validate_store(self, store: Store) -> list[str]:
        """Warn about unrecognized agent IDs in the store and purge them.

        Call after ``store.load()`` and agent registration to clean up
        orphaned entries left by prior pipeline runs.

        Returns the list of orphaned agent IDs that were purged.
        """
        known = self.active_ids()
        orphaned: list[str] = []

        for aid in list(store._agent_metrics):
            if aid not in known:
                orphaned.append(aid)

        for task in store.tasks.values():
            if task.assigned_to and task.assigned_to not in known:
                if task.assigned_to not in orphaned:
                    orphaned.append(task.assigned_to)

        for oid in orphaned:
            logger.warning(
                "Unrecognized agent ID '%s' found in store — no matching "
                "agent definition; purging orphaned data",
                oid,
            )

        if orphaned:
            self.purge_orphans(store)

        return orphaned

    @property
    def count(self) -> int:
        return len(self._agents)

    def summary(self) -> dict[str, int]:
        """Count of agents per role."""
        counts: dict[str, int] = {}
        for a in self._agents.values():
            counts[a.role.value] = counts.get(a.role.value, 0) + 1
        return counts


# Module-level default registry instance
default_registry = AgentRegistry()


def register_agent(
    name: str,
    role: AgentRole,
    registry: AgentRegistry | None = None,
) -> Callable[[type], type]:
    """Class decorator that instantiates and registers a BaseAgent subclass.

    Usage::

        @register_agent(name="my-agent", role=AgentRole.EXECUTION)
        class MyAgent(BaseAgent):
            def execute(self, task, context):
                return TaskOutput(content="done")

    Args:
        name: Display name for the agent.
        role: The agent's role in the organization.
        registry: Registry to add the agent to (defaults to ``default_registry``).

    Returns:
        The original class, unmodified.
    """
    target_registry = registry or default_registry

    def decorator(cls: type) -> type:
        if not (isinstance(cls, type) and issubclass(cls, BaseAgent)):
            raise TypeError("@register_agent can only be applied to BaseAgent subclasses")
        agent_model = Agent(
            id=deterministic_id(name),
            name=name,
            role=role,
        )
        instance = cls(agent_model)
        target_registry.register(instance)
        return cls

    return decorator
