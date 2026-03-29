from __future__ import annotations

import json
import os
from typing import Any

from anthropic import Anthropic

from crazypumpkin.llm.base import CallCost, LLMProvider
from crazypumpkin.observability.metrics import record_cache_event

PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {"input_per_mtok": 15.0, "output_per_mtok": 75.0},
    "claude-sonnet-4-6": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    "claude-haiku-4-5-20251001": {"input_per_mtok": 0.25, "output_per_mtok": 1.25},
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD for a given model and token counts."""
    prices = PRICING.get(model)
    if prices is None:
        return 0.0
    return (input_tokens * prices["input_per_mtok"] + output_tokens * prices["output_per_mtok"]) / 1_000_000

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

    def _apply_cache_control(
        self, messages: list[dict], cache_positions: list[int] | None = None
    ) -> list[dict]:
        """Inject ``cache_control`` markers at specified content block indices.

        Args:
            messages: A list of content block dicts (e.g. system prompt blocks).
            cache_positions: Indices into *messages* to mark. When ``None``,
                every block receives the marker (default behaviour for the
                system prompt).

        Returns:
            The same list, mutated in place, with ``cache_control`` entries added.
        """
        if cache_positions is None:
            for block in messages:
                block["cache_control"] = {"type": "ephemeral"}
        else:
            for idx in cache_positions:
                if 0 <= idx < len(messages):
                    messages[idx]["cache_control"] = {"type": "ephemeral"}
        return messages

    @staticmethod
    def _record_cache_from_usage(response: Any) -> None:
        """Parse cache fields from response usage and record a cache event."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        if cache_read > 0:
            record_cache_event("anthropic", hit=True, tokens_saved=cache_read)
        else:
            record_cache_event("anthropic", hit=False)

    def _build_system_blocks(self, system: str, cache: bool) -> list[dict]:
        """Build the ``system`` parameter content blocks."""
        blocks: list[dict] = [{"type": "text", "text": system}]
        if cache:
            self._apply_cache_control(blocks)
        return blocks

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
        kwargs: dict = {
            "model": resolved,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = self._build_system_blocks(system, cache)
        if timeout is not None:
            kwargs["timeout"] = timeout
        if tools:
            kwargs["tools"] = tools
        response = self._client.messages.create(**kwargs)
        self._record_cache_from_usage(response)
        parts = [block.text for block in response.content if block.type == "text"]
        return "\n".join(parts)

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
        kwargs: dict = {
            "model": resolved,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = self._build_system_blocks(system, cache)
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self._client.messages.create(**kwargs)
        self._record_cache_from_usage(response)

        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        cost_usd = _compute_cost(resolved, input_tokens, output_tokens)
        parts = [block.text for block in response.content if block.type == "text"]
        text = "\n".join(parts)

        call_cost = CallCost(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost_usd,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
        )
        return text, call_cost

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        timeout = kwargs.pop("timeout", None)
        system = kwargs.pop("system", None)
        cache = kwargs.pop("cache", True)
        kwargs.pop("agent", None)
        create_kwargs: dict = {
            "model": resolved,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            create_kwargs["system"] = self._build_system_blocks(system, bool(cache))
        if timeout is not None:
            create_kwargs["timeout"] = timeout
        response = self._client.messages.create(**create_kwargs)
        self._record_cache_from_usage(response)
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
        system: str | None = None,
        cache: bool = True,
        agent: str | None = None,
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
            return self.call(prompt, timeout=timeout, cwd=cwd, system=system, cache=cache)

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
            if system is not None:
                kwargs["system"] = self._build_system_blocks(system, cache)
            if timeout is not None:
                kwargs["timeout"] = timeout

            response = self._client.messages.create(**kwargs)
            self._record_cache_from_usage(response)

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
