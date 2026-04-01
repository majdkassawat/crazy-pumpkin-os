from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from crazypumpkin.llm.base import CallCost, LLMProvider

PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_mtok": 2.50, "output_per_mtok": 10.0},
    "gpt-4o-mini": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    "gpt-4-turbo": {"input_per_mtok": 10.0, "output_per_mtok": 30.0},
    "gpt-4": {"input_per_mtok": 30.0, "output_per_mtok": 60.0},
    "gpt-3.5-turbo": {"input_per_mtok": 0.50, "output_per_mtok": 1.50},
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD for a given model and token counts."""
    prices = PRICING.get(model)
    if prices is None:
        return 0.0
    return (input_tokens * prices["input_per_mtok"] + output_tokens * prices["output_per_mtok"]) / 1_000_000

MODEL_ALIASES: dict[str, str] = {
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4": "gpt-4",
    "gpt-3.5-turbo": "gpt-3.5-turbo",
    "smart": "gpt-4o",
    "fast": "gpt-4o-mini",
}

DEFAULT_MODEL = "gpt-4o"


def _anthropic_tool_to_openai(tool: dict) -> dict:
    """Convert an Anthropic-style tool definition to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI chat completions API."""

    def __init__(self, config: dict | None = None, *, cache_enabled: bool = True) -> None:
        config = config or {}
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self._default_model = config.get("model", DEFAULT_MODEL)
        self.cache_enabled = cache_enabled

    def _apply_cache_hints(self, messages: list[dict]) -> list[dict]:
        """Move system messages to the front for optimal prefix caching."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        return system_msgs + other_msgs

    def _resolve_model(self, model: str | None) -> str:
        name = model or self._default_model
        return MODEL_ALIASES.get(name, name)

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
        agent: str | None = None,
    ) -> str:
        resolved = self._resolve_model(model)
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        use_cache = cache and self.cache_enabled
        if use_cache:
            messages = self._apply_cache_hints(messages)
        kwargs: dict = {
            "model": resolved,
            "messages": messages,
        }
        if use_cache:
            kwargs["store"] = True
        if timeout is not None:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = [_anthropic_tool_to_openai(t) for t in tools]
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        return message.content or ""

    def call_with_cost(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        system: str | None = None,
        cache: bool = True,
    ) -> tuple[str, CallCost]:
        """Like call() but also returns a CallCost with token/cost info."""
        resolved = self._resolve_model(model)
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        use_cache = cache and self.cache_enabled
        if use_cache:
            messages = self._apply_cache_hints(messages)
        kwargs: dict = {
            "model": resolved,
            "messages": messages,
        }
        if use_cache:
            kwargs["store"] = True
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self._client.chat.completions.create(**kwargs)

        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

        cost_usd = _compute_cost(resolved, input_tokens, output_tokens)
        text = response.choices[0].message.content or ""

        call_cost = CallCost(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        return text, call_cost

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
        agent: str | None = None,
    ) -> str:
        """Single-turn fallback — OpenAI multi-turn not yet implemented."""
        return self.call(prompt, model=None, timeout=timeout, cwd=cwd, tools=tools, system=system, cache=cache, agent=agent)

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        system = kwargs.pop("system", None)
        cache = kwargs.pop("cache", True)
        kwargs.pop("agent", None)
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        use_cache = bool(cache) and self.cache_enabled
        if use_cache:
            messages = self._apply_cache_hints(messages)
        create_kwargs: dict = {
            "model": resolved,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if use_cache:
            create_kwargs["store"] = True
        response = self._client.chat.completions.create(**create_kwargs)
        text = response.choices[0].message.content or "{}"
        return json.loads(text)
