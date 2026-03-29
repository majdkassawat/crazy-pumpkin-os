from __future__ import annotations

import json
import os

import litellm

from crazypumpkin.llm.base import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class LiteLLMProvider(LLMProvider):
    """LLM provider backed by LiteLLM, supporting multiple model backends."""

    def __init__(self, config: dict | None = None) -> None:
        config = config or {}
        self._default_model = config.get("model", DEFAULT_MODEL)
        api_key = config.get("api_key")
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        self._api_key = api_key

        langfuse_public_key = config.get("langfuse_public_key")
        langfuse_secret_key = config.get("langfuse_secret_key")
        if langfuse_public_key and langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", langfuse_public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", langfuse_secret_key)
            if "langfuse" not in litellm.success_callback:
                litellm.success_callback = list(litellm.success_callback) + ["langfuse"]

    def _resolve_model(self, model: str | None) -> str:
        return model or self._default_model

    def call(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
        agent: str | None = None,
    ) -> str:
        """Call the LLM and return the text response."""
        resolved = self._resolve_model(model)
        kwargs: dict = {
            "model": resolved,
            "messages": [{"role": "user", "content": prompt}],
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = tools
        if agent is not None:
            kwargs["metadata"] = {"generation_name": agent, "trace_name": agent}
        response = litellm.completion(**kwargs)
        return response.choices[0].message.content or ""

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        """Call the LLM and parse the response as JSON."""
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        agent = kwargs.pop("agent", None)
        completion_kwargs: dict = {
            "model": resolved,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        if agent is not None:
            completion_kwargs["metadata"] = {"generation_name": agent, "trace_name": agent}
        response = litellm.completion(**completion_kwargs)
        text = response.choices[0].message.content or "{}"
        return json.loads(text)

    def call_multi_turn(
        self,
        prompt: str,
        *,
        max_turns: int = 10,
        tools: list | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        agent: str | None = None,
    ) -> str:
        """Single-turn fallback until agentic loop is implemented."""
        return self.call(prompt, model=None, timeout=timeout, cwd=cwd, tools=tools, agent=agent)
