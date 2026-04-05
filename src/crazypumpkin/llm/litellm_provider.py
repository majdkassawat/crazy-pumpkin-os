from __future__ import annotations

import json
import logging
import os
from typing import Optional

import litellm

from crazypumpkin.llm.base import CallCost, LLMProvider, get_default_tracker
from crazypumpkin.observability.cost import CostTracker, get_cost_tracker
from crazypumpkin.observability.tracing import LangfuseTracer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"


class LiteLLMProvider(LLMProvider):
    """LLM provider backed by LiteLLM, supporting multiple model backends."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        cost_tracker: CostTracker | None = None,
        tracer: Optional[LangfuseTracer] = None,
    ) -> None:
        config = config or {}
        self._default_model = config.get("model", DEFAULT_MODEL)
        api_key = config.get("api_key")
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        self._api_key = api_key
        self.cost_tracker = cost_tracker
        self.tracer = tracer

        langfuse_public_key = config.get("langfuse_public_key")
        langfuse_secret_key = config.get("langfuse_secret_key")
        if langfuse_public_key and langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", langfuse_public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", langfuse_secret_key)
            if "langfuse" not in litellm.success_callback:
                litellm.success_callback = list(litellm.success_callback) + ["langfuse"]

    def _resolve_model(self, model: str | None) -> str:
        return model or self._default_model

    def _start_trace(self, model: str, metadata: dict | None = None) -> str | None:
        """Start a tracer span if a tracer is configured. Returns span_id or None."""
        if self.tracer is None:
            return None
        try:
            return self.tracer.start_span(model, metadata=metadata)
        except Exception:
            logger.exception("Failed to start tracing span")
            return None

    def _end_trace(self, span_id: str | None, response: object, content: str) -> None:
        """End a tracer span, recording token usage and cost from the response."""
        if span_id is None or self.tracer is None:
            return
        try:
            usage = getattr(response, "usage", None)
            token_usage = None
            if usage is not None:
                token_usage = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                }
            hidden = getattr(response, "_hidden_params", None)
            cost = None
            if isinstance(hidden, dict):
                cost = hidden.get("response_cost")
            self.tracer.end_span(span_id, output=content, token_usage=token_usage, cost=cost)
        except Exception:
            logger.exception("Failed to end tracing span")

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
        product_id: str | None = None,
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
        span_id = self._start_trace(resolved, metadata={"prompt": prompt, "agent": agent or agent_name})
        response = litellm.completion(**kwargs)
        content = response.choices[0].message.content or ""
        self._end_trace(span_id, response, content)
        self._record_cost_from_response(resolved, response, agent_name=agent or agent_name, product=product or '')

        # Also record to the base CostTracker with product_id
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            try:
                cost_usd = litellm.completion_cost(completion_response=response)
            except Exception:
                cost_usd = 0.0
            call_cost = CallCost(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=cost_usd)
            get_default_tracker().record(resolved, call_cost, agent=agent, product_id=product_id)

        return content

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
        span_id = self._start_trace(resolved, metadata={"prompt": prompt, "agent": agent or agent_name})
        response = litellm.completion(**completion_kwargs)
        text = response.choices[0].message.content or "{}"
        self._end_trace(span_id, response, text)
        self._record_cost_from_response(resolved, response, agent_name=agent or '', product=product or '')
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
        product_id: str | None = None,
    ) -> str:
        """Single-turn fallback until agentic loop is implemented."""
        return self.call(prompt, model=None, timeout=timeout, cwd=cwd, tools=tools, agent=agent, agent_name=agent_name, product_id=product_id)
