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

    def trace_span(
        self,
        name: str,
        *,
        metadata: Optional[dict[str, Any]] = None,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
    ) -> None:
        """Record a named span (non-LLM operation) in Langfuse.

        Use this for tracing tool calls, retrieval steps, agent
        orchestration phases, or any operation that is not a direct
        LLM generation.

        Args:
            name: Identifier for the span (e.g. ``"retrieval/fetch_docs"``).
            metadata: Arbitrary key-value pairs attached to the span.
            input_data: The input payload of the operation (any JSON-serialisable value).
            output_data: The output/result of the operation (any JSON-serialisable value).
        """
        self._client.trace(
            name=name,
            metadata=metadata or {},
            input=input_data,
            output=output_data,
        )

    def shutdown(self) -> None:
        """Flush pending traces and shut down the Langfuse client.

        Call this during application teardown to ensure all buffered
        traces are sent before the process exits. After calling
        ``shutdown()``, the tracer should not be used for further
        tracing calls.
        """
        self._client.flush()
        self._client.shutdown()


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
