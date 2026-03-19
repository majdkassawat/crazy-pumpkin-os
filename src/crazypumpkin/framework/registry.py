"""
Agent registry — manages all agents and their roles.
"""

from __future__ import annotations

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, AgentStatus


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

    @property
    def count(self) -> int:
        return len(self._agents)

    def summary(self) -> dict[str, int]:
        """Count of agents per role."""
        counts: dict[str, int] = {}
        for a in self._agents.values():
            counts[a.role.value] = counts.get(a.role.value, 0) + 1
        return counts
