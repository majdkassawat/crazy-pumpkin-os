"""Langfuse tracing integration for LLM providers."""

from __future__ import annotations

from typing import Any, Optional


_tracer: Optional[LangfuseTracer] = None


class LangfuseTracer:
    """Wrapper around Langfuse client for tracing LLM calls."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def trace_llm_call(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        product: str = "crazy-pumpkin-os",
    ) -> None:
        """Send a single LLM call trace to Langfuse."""
        self._client.generation(
            name=f"{product}/{agent_name}",
            model=model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            metadata={"cost_usd": cost_usd, "product": product},
        )


def configure_tracer(client: Any) -> LangfuseTracer:
    """Set the global tracer instance."""
    global _tracer
    _tracer = LangfuseTracer(client)
    return _tracer


def get_tracer() -> Optional[LangfuseTracer]:
    """Return the current global tracer, or None if not configured."""
    return _tracer


def reset_tracer() -> None:
    """Clear the global tracer (useful for testing)."""
    global _tracer
    _tracer = None
