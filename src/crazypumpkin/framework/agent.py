"""
Base agent interface.

Every agent in the framework extends BaseAgent and implements execute().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput

if TYPE_CHECKING:
    from crazypumpkin.framework.orchestrator import Orchestrator


class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(self, agent: Agent):
        self.agent = agent

    @property
    def id(self) -> str:
        return self.agent.id

    @property
    def name(self) -> str:
        return self.agent.name

    @property
    def role(self) -> AgentRole:
        return self.agent.role

    @abstractmethod
    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Execute a task and return an output.

        Args:
            task: The task to execute.
            context: Runtime context (project info, codebase state, etc.)

        Returns:
            TaskOutput with content and optional artifacts.
        """
        raise NotImplementedError

    def can_handle(self, task: Task) -> bool:
        """Whether this agent can handle the given task. Override for custom logic."""
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name} ({self.role.value})>"
