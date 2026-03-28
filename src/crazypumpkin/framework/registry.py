"""
Agent registry — manages all agents and their roles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, AgentStatus

if TYPE_CHECKING:
    from crazypumpkin.framework.store import Store


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

    @property
    def count(self) -> int:
        return len(self._agents)

    def summary(self) -> dict[str, int]:
        """Count of agents per role."""
        counts: dict[str, int] = {}
        for a in self._agents.values():
            counts[a.role.value] = counts.get(a.role.value, 0) + 1
        return counts
