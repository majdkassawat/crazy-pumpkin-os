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
    ) -> str: ...

    @abstractmethod
    def call_json(self, prompt: str, **kwargs: object) -> dict | list: ...
