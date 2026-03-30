"""
Base agent interface.

Every agent in the framework extends BaseAgent and implements execute().
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from crazypumpkin.framework.logging import AgentLogContext, configure_agent_logging
from crazypumpkin.framework.metrics import default_metrics
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

    def setup(self, context: dict[str, Any]) -> None:
        """Optional setup hook called before execute(). Override for custom logic."""

    def teardown(self, context: dict[str, Any]) -> None:
        """Optional teardown hook called after execute(). Always runs, even on error."""

    def run(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Run the full agent lifecycle: setup, execute, teardown.

        Calls setup(), then execute(), then teardown(). Teardown is
        guaranteed to run even if execute() raises an exception.
        Logs structured JSON for start/completion and records metrics.

        Args:
            task: The task to execute.
            context: Runtime context.

        Returns:
            TaskOutput from execute().
        """
        log_ctx = AgentLogContext(
            agent_id=self.id,
            task_id=task.id,
            cycle_id=context.get("cycle_id", ""),
        )
        configure_agent_logging()
        logger = log_ctx.bind(logging.getLogger("crazypumpkin.agent"))
        logger.info("Agent execution started")

        self.setup(context)
        start = time.monotonic()
        try:
            result = self.execute(task, context)
            duration = time.monotonic() - start
            logger.info("Agent execution completed", extra={"duration": duration})
            default_metrics.record_execution(
                self.id, duration, tokens=context.get("token_usage"), error=False,
            )
        except Exception:
            duration = time.monotonic() - start
            logger.error("Agent execution failed", extra={"duration": duration})
            default_metrics.record_execution(self.id, duration, error=True)
            raise
        finally:
            self.teardown(context)
        return result

    def can_handle(self, task: Task) -> bool:
        """Whether this agent can handle the given task. Override for custom logic."""
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name} ({self.role.value})>"


class ClaudeSDKAgent(BaseAgent):
    """Agent that wraps the Anthropic Claude Agent SDK.

    Manages tool permissions and supports multi-turn sessions by
    maintaining a message history list across ``execute()`` calls.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        agent: Agent,
        tool_permissions: dict[str, bool] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(agent)
        self.tool_permissions: dict[str, bool] = tool_permissions or {
            "read": True,
            "write": False,
            "bash": False,
        }
        self.system_prompt: str | None = system_prompt
        self._history: list[dict[str, Any]] = []

    def _build_tools(self) -> list[dict[str, Any]]:
        """Build tool definitions based on configured permissions."""
        tools: list[dict[str, Any]] = []
        if self.tool_permissions.get("read") or self.tool_permissions.get("write"):
            tools.append({"type": "text_editor_20250429"})
        if self.tool_permissions.get("bash"):
            tools.append({"type": "bash_20250429"})
        return tools

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Execute a task using the Anthropic Claude Agent SDK.

        Appends the user prompt and assistant response to the internal
        history so that subsequent calls on the same instance carry
        conversational context.

        Args:
            task: The task to execute.
            context: Runtime context (project info, codebase state, etc.)

        Returns:
            TaskOutput with content populated from the SDK response.
        """
        import anthropic

        client = anthropic.Anthropic()
        model = self.agent.config.model or self.DEFAULT_MODEL

        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        user_message = (
            f"Task: {task.title}\n\n"
            f"Description:\n{task.description}\n\n"
            f"Acceptance criteria:\n{criteria}"
        )
        self._history.append({"role": "user", "content": user_message})

        tools = self._build_tools()
        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": list(self._history),
        }
        if self.system_prompt is not None:
            create_kwargs["system"] = [
                {"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}},
            ]
        if tools:
            create_kwargs["tools"] = tools

        response = client.messages.create(**create_kwargs)

        # Extract text content from the response
        content_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                content_parts.append(block.text)
        content = "\n".join(content_parts)

        # Preserve assistant turn for multi-turn continuity
        self._history.append({
            "role": "assistant",
            "content": response.content,
        })

        return TaskOutput(content=content)
