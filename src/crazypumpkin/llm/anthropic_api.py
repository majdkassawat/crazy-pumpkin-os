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
        timeout = kwargs.pop("timeout", None)
        create_kwargs: dict = {
            "model": resolved,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if timeout is not None:
            create_kwargs["timeout"] = timeout
        response = self._client.messages.create(**create_kwargs)
        parts = [block.text for block in response.content if block.type == "text"]
        text = "\n".join(parts) or "{}"
        return json.loads(text)

    def call_multi_turn(
        self,
        prompt: str,
        *,
        max_turns: int = 10,
        tools: list | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tool_executor: object | None = None,
    ) -> str:
        """Run an agentic conversation loop until the model stops issuing tool calls or *max_turns* is reached.

        Args:
            prompt: The initial user message.
            max_turns: Maximum number of request/response turns.
            tools: Anthropic-format tool definitions. If ``None`` or empty,
                falls back to a single-turn ``call()``.
            timeout: Optional timeout forwarded to the Anthropic client.
            cwd: Working directory hint (unused by this provider directly).
            tool_executor: Optional callable ``(name, input) -> str`` that
                executes a tool call and returns its string result. When
                ``None`` every tool call returns ``"ok"``.
        """
        if not tools:
            return self.call(prompt, timeout=timeout, cwd=cwd)

        resolved = self._resolve_model(None)
        messages: list[dict] = [{"role": "user", "content": prompt}]

        collected_text: list[str] = []

        for _turn in range(max_turns):
            kwargs: dict = {
                "model": resolved,
                "max_tokens": 4096,
                "messages": messages,
                "tools": tools,
            }
            if timeout is not None:
                kwargs["timeout"] = timeout

            response = self._client.messages.create(**kwargs)

            # Collect any text blocks from this turn
            assistant_content: list[dict] = []
            for block in response.content:
                if block.type == "text":
                    collected_text.append(block.text)
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            # Append the full assistant message
            messages.append({"role": "assistant", "content": assistant_content})

            # If the model did not request tool use, we are done
            if response.stop_reason != "tool_use":
                break

            # Execute each tool_use block and build tool_result messages
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    if tool_executor is not None:
                        result_text = str(tool_executor(block.name, block.input))
                    else:
                        result_text = "ok"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})

        return "\n".join(collected_text)
