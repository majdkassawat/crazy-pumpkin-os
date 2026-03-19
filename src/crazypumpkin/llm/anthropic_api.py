from __future__ import annotations

import json
import os

from anthropic import Anthropic

from crazypumpkin.llm.base import LLMProvider

MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "smart": "claude-sonnet-4-6",
    "fast": "claude-haiku-4-5-20251001",
}

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic messages API."""

    def __init__(self, config: dict | None = None) -> None:
        config = config or {}
        api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=api_key)
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
    ) -> str:
        resolved = self._resolve_model(model)
        kwargs: dict = {
            "model": resolved,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = tools
        response = self._client.messages.create(**kwargs)
        parts = [block.text for block in response.content if block.type == "text"]
        return "\n".join(parts)

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        response = self._client.messages.create(
            model=resolved,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in response.content if block.type == "text"]
        text = "\n".join(parts) or "{}"
        return json.loads(text)
