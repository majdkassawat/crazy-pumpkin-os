from __future__ import annotations

from abc import ABC, abstractmethod


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
    ) -> str: ...

    @abstractmethod
    def call_json(self, prompt: str, **kwargs: object) -> dict | list: ...

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
    ) -> str:
        """Run an agentic conversation loop until the model stops issuing tool calls or *max_turns* is reached."""
