from __future__ import annotations

import json
import os

import litellm

from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.observability.cost import CostTracker, get_cost_tracker

DEFAULT_MODEL = "gpt-4o"


class LiteLLMProvider(LLMProvider):
    """LLM provider backed by LiteLLM, supporting multiple model backends."""

    def __init__(self, config: dict | None = None, *, cost_tracker: CostTracker | None = None) -> None:
        config = config or {}
        self._default_model = config.get("model", DEFAULT_MODEL)
        api_key = config.get("api_key")
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        self._api_key = api_key
        self.cost_tracker = cost_tracker

        langfuse_public_key = config.get("langfuse_public_key")
        langfuse_secret_key = config.get("langfuse_secret_key")
        if langfuse_public_key and langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", langfuse_public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", langfuse_secret_key)
            if "langfuse" not in litellm.success_callback:
                litellm.success_callback = list(litellm.success_callback) + ["langfuse"]

    def _resolve_model(self, model: str | None) -> str:
        return model or self._default_model

    def _record_cost_from_response(
        self,
        model: str,
        response: object,
        agent_name: str = "unknown",
        product: str = "crazy-pumpkin-os",
    ) -> None:
        """Extract token counts from a LiteLLM response and record via cost tracker."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        try:
            cost_usd = litellm.completion_cost(completion_response=response)
        except Exception:
            cost_usd = 0.0
        tracker = self.cost_tracker or get_cost_tracker()
        tracker.record(
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            product=product,
        )

    def call(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
        system: str | None = None,
        agent: str | None = None,
        agent_name: str = "unknown",
        product: str | None = None,
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
        self._record_cost_from_response(resolved, response, agent_name=agent or agent_name, product=product or '')
        return response.choices[0].message.content or ""

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        """Call the LLM and parse the response as JSON."""
        resolved = self._resolve_model(kwargs.pop("model", None))  # type: ignore[arg-type]
        agent = kwargs.pop("agent", None)
        agent_name = kwargs.pop("agent_name", "unknown")
        product = kwargs.pop("product", None)
        completion_kwargs: dict = {
            "model": resolved,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        if agent is not None:
            completion_kwargs["metadata"] = {"generation_name": agent, "trace_name": agent}
        response = litellm.completion(**completion_kwargs)
        self._record_cost_from_response(resolved, response, agent_name=agent or '', product=product or '')
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
        agent_name: str = "unknown",
    ) -> str:
        """Single-turn fallback until agentic loop is implemented."""
        return self.call(prompt, model=None, timeout=timeout, cwd=cwd, tools=tools, agent=agent, agent_name=agent_name)
