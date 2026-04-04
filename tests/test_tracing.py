"""Tests for trace_span and shutdown methods on LangfuseTracer."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from crazypumpkin.observability.tracing import LangfuseTracer, get_tracer, reset_tracer


def test_trace_span_creates_trace():
    client = MagicMock()
    tracer = LangfuseTracer(client)

    tracer.trace_span(
        name="tool-call",
        metadata={"tool": "grep"},
        input_data="query",
        output_data="result",
    )

    client.trace.assert_called_once_with(
        name="tool-call",
        metadata={"tool": "grep"},
        input="query",
        output="result",
    )


def test_trace_span_defaults():
    client = MagicMock()
    tracer = LangfuseTracer(client)

    tracer.trace_span(name="step")

    client.trace.assert_called_once_with(
        name="step",
        metadata={},
        input=None,
        output=None,
    )


def test_shutdown_flushes_and_shuts_down():
    client = MagicMock()
    tracer = LangfuseTracer(client)

    tracer.shutdown()

    client.flush.assert_called_once()
    client.shutdown.assert_called_once()
    # Verify flush is called before shutdown
    assert client.method_calls == [call.flush(), call.shutdown()]


def test_get_tracer_returns_none_without_keys():
    reset_tracer()
    assert get_tracer() is None
