"""
Base agent interface.

Every agent in the framework extends BaseAgent and implements execute().
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Optional

from crazypumpkin.framework.events import ChannelRegistry, EventChannel
from crazypumpkin.framework.logging import AgentLogContext, configure_agent_logging
from crazypumpkin.framework.metrics import default_metrics
from crazypumpkin.framework.models import Agent, AgentRole, Session, SessionRecord, Task, TaskOutput
from crazypumpkin.framework.session import SessionStore
from crazypumpkin.framework.store import Store
from crazypumpkin.observability.budget import AlertLevel, BudgetEnforcer, BudgetThreshold
from crazypumpkin.observability.budget_notifier import BudgetNotifier

if TYPE_CHECKING:
    from crazypumpkin.framework.orchestrator import Orchestrator


class BudgetExceededError(Exception):
    """Raised when an agent exceeds its budget and hard_stop is enabled."""
    pass


class EventParticipantMixin:
    """Mixin that gives agents pub/sub event channel participation."""

    _channel_registry: ChannelRegistry | None
    _outbox: deque[tuple[str, Any]]

    def bind_channels(self, registry: ChannelRegistry) -> None:
        """Bind this agent to a :class:`ChannelRegistry`."""
        self._channel_registry = registry
        self._outbox = deque()

    def emit(self, channel_name: str, event: Any) -> None:
        """Queue *event* for async delivery on *channel_name*."""
        if not hasattr(self, "_outbox"):
            raise RuntimeError("call bind_channels() before emit()")
        self._outbox.append((channel_name, event))

    def on(
        self,
        channel_name: str,
        handler: Callable,
        filter_fn: Callable | None = None,
    ) -> None:
        """Subscribe *handler* to *channel_name* on the bound registry."""
        if not hasattr(self, "_channel_registry") or self._channel_registry is None:
            raise RuntimeError("call bind_channels() before on()")
        channel = self._channel_registry.get_or_create(channel_name, object)
        channel.subscribe(handler, filter_fn=filter_fn)

    async def drain_events(self) -> None:
        """Flush all pending outbound events (publish each queued event)."""
        if not hasattr(self, "_channel_registry") or self._channel_registry is None:
            raise RuntimeError("call bind_channels() before drain_events()")
        while self._outbox:
            channel_name, event = self._outbox.popleft()
            channel = self._channel_registry.get_or_create(channel_name, object)
            await channel.publish(event)


class BaseAgent(ABC):
    """Abstract base for all agents."""

    def __init__(self, agent: Agent):
        self.agent = agent
        self._budget_enforcer: BudgetEnforcer | None = None
        self._budget_notifier: BudgetNotifier | None = None
        self._hard_stop: bool = False
        self._session_store: Optional[SessionStore] = None
        self._current_session: Optional[Session] = None

    def configure_budget(
        self,
        enforcer: BudgetEnforcer,
        notifier: BudgetNotifier | None = None,
        hard_stop: bool = False,
    ) -> None:
        """Configure budget enforcement for this agent."""
        self._budget_enforcer = enforcer
        self._budget_notifier = notifier or BudgetNotifier()
        self._hard_stop = hard_stop

    async def _check_budget_after_call(self, cost: float) -> None:
        """Check budget thresholds after an LLM call and dispatch alerts if needed."""
        if self._budget_enforcer is None:
            return
        self._budget_enforcer.record_spend(self.name, cost)
        alert = self._budget_enforcer.check_thresholds(self.name)
        if alert is not None:
            if self._budget_notifier is not None:
                await self._budget_notifier.dispatch(alert)
            if alert.level == AlertLevel.EXCEEDED and self._hard_stop:
                raise BudgetExceededError(
                    f"Agent {self.name} exceeded budget: {alert.message}"
                )

    @property
    def id(self) -> str:
        return self.agent.id

    @property
    def name(self) -> str:
        return self.agent.name

    @property
    def role(self) -> AgentRole:
        return self.agent.role

    async def start_session(self, max_turns: int = 50) -> Session:
        """Begin a new multi-turn session for this agent."""
        if self._session_store is None:
            self._session_store = SessionStore(Store())
        session = await self._session_store.create(self.name, max_turns=max_turns)
        self._current_session = session
        return session

    async def resume_session(self, session_id: str) -> Session:
        """Resume an existing session by ID."""
        if self._session_store is None:
            self._session_store = SessionStore(Store())
        session = await self._session_store.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")
        self._current_session = session
        return session

    async def end_session(self) -> Session:
        """Close the current session."""
        if self._current_session is None or self._session_store is None:
            raise RuntimeError("No active session to end")
        session = await self._session_store.close(self._current_session.session_id)
        self._current_session = session
        result = session
        self._current_session = None
        return result

    def get_session_messages(self) -> list[dict]:
        """Return current session messages as list of dicts for LLM context."""
        if self._current_session is None:
            return []
        return [
            {"role": m.role, "content": m.content}
            for m in self._current_session.messages
        ]

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

        # Record user input to session if active
        if self._current_session is not None and self._session_store is not None:
            user_content = f"Task: {task.title}\n{task.description}"
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._session_store.append_message(
                        self._current_session.session_id, "user", user_content,
                    )
                )
                self._current_session = loop.run_until_complete(
                    self._session_store.get(self._current_session.session_id)
                )
            finally:
                loop.close()

        # Prepend session messages to context
        if self._current_session is not None:
            context = dict(context)
            context["session_messages"] = self.get_session_messages()

        self.setup(context)
        start = time.monotonic()
        try:
            result = self.execute(task, context)
            duration = time.monotonic() - start
            logger.info("Agent execution completed", extra={"duration": duration})
            default_metrics.record_execution(
                self.id, duration, tokens=context.get("token_usage"), error=False,
            )

            # Record agent response to session if active
            if self._current_session is not None and self._session_store is not None:
                loop2 = asyncio.new_event_loop()
                try:
                    loop2.run_until_complete(
                        self._session_store.append_message(
                            self._current_session.session_id, "assistant", result.content,
                        )
                    )
                    self._current_session = loop2.run_until_complete(
                        self._session_store.get(self._current_session.session_id)
                    )
                finally:
                    loop2.close()
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
        store: Store | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(agent)
        self.tool_permissions: dict[str, bool] = tool_permissions or {
            "read": True,
            "write": False,
            "bash": False,
        }
        self.system_prompt: str | None = system_prompt
        self._history: list[dict[str, Any]] = []
        self._store: Store | None = store
        self._session_id: str | None = session_id
        if store is not None and session_id is not None:
            self.restore_session(session_id)

    def save_session(self) -> str | None:
        """Persist the current history to the store as a SessionRecord.

        Returns the session_id, or None if no store is configured.
        """
        if self._store is None:
            return None
        from crazypumpkin.framework.models import _now
        if self._session_id is None:
            from crazypumpkin.framework.models import _uid
            self._session_id = _uid()
        record = SessionRecord(
            session_id=self._session_id,
            agent_id=self.id,
            messages=list(self._history),
            updated_at=_now(),
        )
        self._store.save_session(record)
        return self._session_id

    def restore_session(self, session_id: str) -> bool:
        """Load a SessionRecord from the store and set history.

        Returns False if the session is not found or no store is configured.
        """
        if self._store is None:
            return False
        session = self._store.load_session(session_id)
        if session is None:
            return False
        self._history = list(session.messages)
        self._session_id = session_id
        return True

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

        if self._store is not None:
            self.save_session()

        return TaskOutput(content=content)
