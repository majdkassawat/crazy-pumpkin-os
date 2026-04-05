"""Langfuse tracing integration for LLM providers."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional


_tracer: Optional[LangfuseTracer] = None


class LangfuseTracer:
    """Wrapper around Langfuse client for tracing LLM calls."""

    def __init__(
        self,
        public_key: str = "",
        secret_key: str = "",
        host: str = "https://cloud.langfuse.com",
        product_name: str = "default",
        *,
        client: Any = None,
    ) -> None:
        self._product_name = product_name
        self._spans: Dict[str, Any] = {}
        self._traces: Dict[str, Any] = {}

        if client is not None:
            # Legacy path: accept a pre-built Langfuse client directly.
            self._client = client
        else:
            try:
                from langfuse import Langfuse
            except ImportError:
                raise ImportError(
                    "langfuse is required for LangfuseTracer. "
                    "Install it with: pip install langfuse>=2.0"
                )
            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_span(
        self, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start a new traced span, returning its unique ID."""
        span_id = uuid.uuid4().hex
        merged_metadata = {"product_name": self._product_name}
        if metadata:
            merged_metadata.update(metadata)

        trace = self._client.trace(name=name, metadata=merged_metadata)
        span = trace.span(name=name, metadata=merged_metadata)

        self._traces[span_id] = trace
        self._spans[span_id] = span
        return span_id

    def end_span(
        self,
        span_id: str,
        output: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        cost: Optional[float] = None,
    ) -> None:
        """End a previously started span, attaching output and cost data."""
        span = self._spans.pop(span_id, None)
        if span is None:
            raise KeyError(f"Unknown span_id: {span_id}")

        update_kwargs: Dict[str, Any] = {}
        if output is not None:
            update_kwargs["output"] = output
        if token_usage is not None:
            update_kwargs["usage"] = token_usage
        if cost is not None:
            update_kwargs["metadata"] = {
                "product_name": self._product_name,
                "cost": cost,
            }
        span.end(**update_kwargs)
        self._traces.pop(span_id, None)

    # ------------------------------------------------------------------
    # Flush / shutdown
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush pending traces to Langfuse."""
        self._client.flush()

    def shutdown(self) -> None:
        """Flush pending traces and shut down the Langfuse client."""
        self.flush()
        self._client.shutdown()

    # ------------------------------------------------------------------
    # Legacy helpers (kept for backward compatibility)
    # ------------------------------------------------------------------

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
        """Record a named span (non-LLM operation) in Langfuse."""
        self._client.trace(
            name=name,
            metadata=metadata or {},
            input=input_data,
            output=output_data,
        )


def configure_tracer(client: Any) -> LangfuseTracer:
    """Set the global tracer instance."""
    global _tracer
    _tracer = LangfuseTracer(client=client)
    return _tracer


def get_tracer() -> Optional[LangfuseTracer]:
    """Return the current global tracer, or None if not configured."""
    return _tracer


def reset_tracer() -> None:
    """Clear the global tracer (useful for testing)."""
    global _tracer
    _tracer = None
