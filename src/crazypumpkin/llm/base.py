from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallCost:
    """Cost information for a single LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class CostTracker:
    """Thread-safe tracker for accumulating LLM call costs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_cost_usd: float = 0.0
        self._call_count: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cache_creation_tokens: int = 0
        self._total_cache_read_tokens: int = 0
        self._by_model: dict[str, dict[str, Any]] = {}

    def record(self, model: str, cost: CallCost) -> None:
        """Record the cost of a single LLM call.

        Args:
            model: The model identifier used for the call.
            cost: A ``CallCost`` instance containing token counts and USD cost.
        """
        with self._lock:
            self._total_cost_usd += cost.cost_usd
            self._call_count += 1
            self._total_prompt_tokens += cost.prompt_tokens
            self._total_completion_tokens += cost.completion_tokens
            self._total_cache_creation_tokens += cost.cache_creation_tokens
            self._total_cache_read_tokens += cost.cache_read_tokens

            if model not in self._by_model:
                self._by_model[model] = {
                    "total_cost_usd": 0.0,
                    "call_count": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cache_creation_tokens": 0,
                    "total_cache_read_tokens": 0,
                }
            m = self._by_model[model]
            m["total_cost_usd"] += cost.cost_usd
            m["call_count"] += 1
            m["total_prompt_tokens"] += cost.prompt_tokens
            m["total_completion_tokens"] += cost.completion_tokens
            m["total_cache_creation_tokens"] += cost.cache_creation_tokens
            m["total_cache_read_tokens"] += cost.cache_read_tokens

    def get_summary(self) -> dict[str, Any]:
        """Return a snapshot of accumulated cost data.

        Returns:
            A dict with keys ``total_cost_usd``, ``call_count``,
            ``total_prompt_tokens``, ``total_completion_tokens``,
            ``total_cache_creation_tokens``, ``total_cache_read_tokens``,
            and ``by_model`` (a per-model breakdown).
        """
        with self._lock:
            return {
                "total_cost_usd": self._total_cost_usd,
                "call_count": self._call_count,
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "total_cache_creation_tokens": self._total_cache_creation_tokens,
                "total_cache_read_tokens": self._total_cache_read_tokens,
                "by_model": {k: dict(v) for k, v in self._by_model.items()},
            }

    def reset(self) -> None:
        """Reset all accumulated cost data to zero."""
        with self._lock:
            self._total_cost_usd = 0.0
            self._call_count = 0
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_cache_creation_tokens = 0
            self._total_cache_read_tokens = 0
            self._by_model.clear()


_default_tracker: CostTracker | None = None
_tracker_lock = threading.Lock()


def get_default_tracker() -> CostTracker:
    """Return the global singleton CostTracker instance."""
    global _default_tracker
    with _tracker_lock:
        if _default_tracker is None:
            _default_tracker = CostTracker()
        return _default_tracker


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def call(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
        system: str | None = None,
        cache: bool = True,
    ) -> str:
        """Send a single prompt to the LLM and return the text response.

        Args:
            prompt: The user message to send.
            model: Model identifier override. When ``None`` the provider's
                default model is used.
            timeout: Optional request timeout in seconds.
            cwd: Working directory hint passed to tool-using models.
            tools: Tool definitions in provider-native format.
            system: Optional system prompt prepended to the conversation.
            cache: Whether to enable prompt caching (provider-dependent).

        Returns:
            The model's text response.
        """

    @abstractmethod
    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        """Send a prompt and parse the response as JSON.

        Args:
            prompt: The user message to send.
            **kwargs: Additional keyword arguments forwarded to the underlying
                provider (e.g. ``model``, ``timeout``, ``system``).

        Returns:
            The parsed JSON response as a ``dict`` or ``list``.

        Raises:
            json.JSONDecodeError: If the model response is not valid JSON.
        """

    @abstractmethod
    def call_multi_turn(
        self,
        prompt: str,
        *,
        max_turns: int = 10,
        tools: list | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        system: str | None = None,
        cache: bool = True,
    ) -> str:
        """Run an agentic conversation loop until the model stops issuing tool calls or *max_turns* is reached.

        Args:
            prompt: The initial user message.
            max_turns: Maximum number of request/response turns.
            tools: Tool definitions in provider-native format. If ``None``
                or empty, falls back to a single-turn ``call()``.
            timeout: Optional request timeout in seconds per turn.
            cwd: Working directory hint passed to tool-using models.
            system: Optional system prompt prepended to the conversation.
            cache: Whether to enable prompt caching (provider-dependent).

        Returns:
            The concatenated text output across all turns.
        """
