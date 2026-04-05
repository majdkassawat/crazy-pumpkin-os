"""Tests for LangfuseTracer span lifecycle and configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from crazypumpkin.observability.tracing import LangfuseTracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracer(product_name: str = "test-product") -> LangfuseTracer:
    """Create a LangfuseTracer backed by a mock Langfuse client."""
    mock_client = MagicMock()
    # trace() returns a mock trace that has .span()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_trace.span.return_value = mock_span
    mock_client.trace.return_value = mock_trace
    return LangfuseTracer(client=mock_client, product_name=product_name)


# ---------------------------------------------------------------------------
# Class existence and interface
# ---------------------------------------------------------------------------


class TestLangfuseTracerExists:
    """LangfuseTracer class exists with all 5 required methods."""

    def test_class_exists_in_module(self):
        from crazypumpkin.observability.tracing import LangfuseTracer as Cls
        assert Cls is not None

    @pytest.mark.parametrize(
        "method",
        ["start_span", "end_span", "flush", "shutdown", "__init__"],
    )
    def test_has_required_methods(self, method: str):
        assert hasattr(LangfuseTracer, method), f"Missing method: {method}"


# ---------------------------------------------------------------------------
# start_span
# ---------------------------------------------------------------------------


class TestStartSpan:
    """start_span returns a span_id string and attaches product_name metadata."""

    def test_returns_string(self):
        tracer = _make_tracer()
        span_id = tracer.start_span("my-span")
        assert isinstance(span_id, str)
        assert len(span_id) > 0

    def test_returns_unique_ids(self):
        tracer = _make_tracer()
        ids = {tracer.start_span(f"span-{i}") for i in range(20)}
        assert len(ids) == 20

    def test_product_name_in_metadata(self):
        tracer = _make_tracer(product_name="billing-service")
        tracer.start_span("op", metadata={"extra": 1})

        trace_call = tracer._client.trace.call_args
        meta = trace_call.kwargs.get("metadata") or trace_call[1].get("metadata")
        assert meta["product_name"] == "billing-service"
        assert meta["extra"] == 1

    def test_product_name_default_metadata(self):
        tracer = _make_tracer(product_name="billing-service")
        tracer.start_span("op")

        trace_call = tracer._client.trace.call_args
        meta = trace_call.kwargs.get("metadata") or trace_call[1].get("metadata")
        assert meta["product_name"] == "billing-service"


# ---------------------------------------------------------------------------
# end_span
# ---------------------------------------------------------------------------


class TestEndSpan:
    """end_span records token_usage and cost on the span."""

    def test_end_span_with_token_usage_and_cost(self):
        tracer = _make_tracer()
        span_id = tracer.start_span("gen")

        mock_span = tracer._spans[span_id]
        tracer.end_span(
            span_id,
            output="hello world",
            token_usage={"prompt_tokens": 10, "completion_tokens": 5},
            cost=0.0015,
        )

        mock_span.end.assert_called_once()
        kwargs = mock_span.end.call_args.kwargs
        assert kwargs["output"] == "hello world"
        assert kwargs["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
        assert kwargs["metadata"]["cost"] == 0.0015

    def test_end_span_removes_from_tracking(self):
        tracer = _make_tracer()
        span_id = tracer.start_span("gen")
        assert span_id in tracer._spans
        tracer.end_span(span_id)
        assert span_id not in tracer._spans

    def test_end_span_unknown_id_raises(self):
        tracer = _make_tracer()
        with pytest.raises(KeyError, match="Unknown span_id"):
            tracer.end_span("nonexistent-id")

    def test_end_span_output_only(self):
        tracer = _make_tracer()
        span_id = tracer.start_span("gen")
        mock_span = tracer._spans[span_id]
        tracer.end_span(span_id, output="result")

        kwargs = mock_span.end.call_args.kwargs
        assert kwargs["output"] == "result"
        assert "usage" not in kwargs
        assert "metadata" not in kwargs

    def test_end_span_cost_includes_product_name(self):
        tracer = _make_tracer(product_name="my-product")
        span_id = tracer.start_span("gen")
        mock_span = tracer._spans[span_id]
        tracer.end_span(span_id, cost=0.05)

        kwargs = mock_span.end.call_args.kwargs
        assert kwargs["metadata"]["product_name"] == "my-product"
        assert kwargs["metadata"]["cost"] == 0.05


# ---------------------------------------------------------------------------
# flush
# ---------------------------------------------------------------------------


class TestFlush:
    """flush() delegates to the underlying client."""

    def test_flush_calls_client(self):
        tracer = _make_tracer()
        tracer.flush()
        tracer._client.flush.assert_called_once()


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    """shutdown() calls flush() before closing the client."""

    def test_shutdown_calls_flush_then_shutdown(self):
        tracer = _make_tracer()
        tracer.shutdown()

        tracer._client.flush.assert_called_once()
        tracer._client.shutdown.assert_called_once()

    def test_shutdown_flush_called_before_shutdown(self):
        """Verify ordering: flush() is called before shutdown()."""
        tracer = _make_tracer()
        call_order: list[str] = []
        tracer._client.flush.side_effect = lambda: call_order.append("flush")
        tracer._client.shutdown.side_effect = lambda: call_order.append("shutdown")

        tracer.shutdown()

        assert call_order == ["flush", "shutdown"]


# ---------------------------------------------------------------------------
# setup.cfg / pyproject.toml extras
# ---------------------------------------------------------------------------


class TestDependencyConfig:
    """langfuse is listed as optional dependency under 'tracing'."""

    def test_setup_cfg_has_tracing_extra(self):
        from pathlib import Path

        setup_cfg = Path(__file__).resolve().parent.parent / "setup.cfg"
        assert setup_cfg.exists(), "setup.cfg not found"
        content = setup_cfg.read_text()
        assert "langfuse" in content
        assert "tracing" in content

    def test_pyproject_has_tracing_extra(self):
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml not found"
        content = pyproject.read_text()
        assert 'tracing' in content
        assert 'langfuse>=2.0' in content
