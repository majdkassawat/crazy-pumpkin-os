from __future__ import annotations

import json
import os

from openai import OpenAI

from crazypumpkin.llm.base import LLMProvider

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

    def __init__(self, config: dict | None = None) -> None:
        config = config or {}
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self._default_model = config.get("model", DEFAULT_MODEL)

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
    ) -> str:
        resolved = self._resolve_model(model)
        kwargs: dict = {
            "model": resolved,
            "messages": [{"role": "user", "content": prompt}],
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = [_anthropic_tool_to_openai(t) for t in tools]
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        return message.content or ""

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        response = self._client.chat.completions.create(
            model=resolved,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)
