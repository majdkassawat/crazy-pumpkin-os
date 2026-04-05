"""Tests for LangfuseTracer integration in LiteLLMProvider."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from crazypumpkin.llm.litellm_provider import LiteLLMProvider
from crazypumpkin.observability.tracing import LangfuseTracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracer() -> LangfuseTracer:
    """Create a LangfuseTracer backed by a mock Langfuse client."""
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_trace.span.return_value = mock_span
    mock_client.trace.return_value = mock_trace
    return LangfuseTracer(client=mock_client, product_name="test")


def _fake_response(
    content: str = "hello",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    total_tokens: int = 15,
    response_cost: float = 0.001,
) -> SimpleNamespace:
    """Build a fake LiteLLM response object with usage and _hidden_params."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        _hidden_params={"response_cost": response_cost},
    )


# ---------------------------------------------------------------------------
# Constructor accepts optional tracer
# ---------------------------------------------------------------------------


class TestConstructorAcceptsTracer:
    def test_tracer_none_by_default(self):
        provider = LiteLLMProvider({"model": "gpt-4o"})
        assert provider.tracer is None

    def test_tracer_stored_when_provided(self):
        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)
        assert provider.tracer is tracer


# ---------------------------------------------------------------------------
# Completion call creates and closes a span when tracer is present
# ---------------------------------------------------------------------------


class TestCallCreatesAndClosesSpan:
    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_starts_and_ends_span(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("world")
        mock_litellm.completion_cost.return_value = 0.001
        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        # Spy on the tracer
        tracer.start_span = MagicMock(return_value="span-123")
        tracer.end_span = MagicMock()

        result = provider.call("hello")

        assert result == "world"
        tracer.start_span.assert_called_once()
        tracer.end_span.assert_called_once()

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_json_starts_and_ends_span(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response('{"key": "val"}')
        mock_litellm.completion_cost.return_value = 0.0
        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="span-456")
        tracer.end_span = MagicMock()

        result = provider.call_json("give json")

        assert result == {"key": "val"}
        tracer.start_span.assert_called_once()
        tracer.end_span.assert_called_once()

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_multi_turn_traces(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("multi")
        mock_litellm.completion_cost.return_value = 0.0
        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="span-789")
        tracer.end_span = MagicMock()

        result = provider.call_multi_turn("turn prompt")

        assert result == "multi"
        tracer.start_span.assert_called_once()
        tracer.end_span.assert_called_once()


# ---------------------------------------------------------------------------
# Token usage and cost are recorded on spans
# ---------------------------------------------------------------------------


class TestTokenUsageAndCostRecorded:
    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_end_span_receives_token_usage_and_cost(self, mock_litellm):
        resp = _fake_response(
            content="ok",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            response_cost=0.005,
        )
        mock_litellm.completion.return_value = resp
        mock_litellm.completion_cost.return_value = 0.005

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="s1")
        tracer.end_span = MagicMock()

        provider.call("test")

        tracer.end_span.assert_called_once_with(
            "s1",
            output="ok",
            token_usage={
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
            cost=0.005,
        )

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_span_model_name_passed_to_start_span(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response()
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "claude-3"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="s2")
        tracer.end_span = MagicMock()

        provider.call("hi")

        args, kwargs = tracer.start_span.call_args
        assert args[0] == "claude-3"

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_no_usage_still_calls_end_span(self, mock_litellm):
        """If usage is None, token_usage should be None but span still ends."""
        resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
            usage=None,
            _hidden_params={"response_cost": 0.0},
        )
        mock_litellm.completion.return_value = resp
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="s3")
        tracer.end_span = MagicMock()

        provider.call("p")

        tracer.end_span.assert_called_once_with(
            "s3",
            output="x",
            token_usage=None,
            cost=0.0,
        )


# ---------------------------------------------------------------------------
# Tracing errors are caught and logged, never propagated
# ---------------------------------------------------------------------------


class TestTracingErrorsNeverPropagate:
    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_start_span_error_does_not_break_call(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("safe")
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(side_effect=RuntimeError("boom"))
        tracer.end_span = MagicMock()

        result = provider.call("test")
        assert result == "safe"
        # end_span should NOT be called since start_span failed (span_id is None)
        tracer.end_span.assert_not_called()

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_end_span_error_does_not_break_call(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("safe2")
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)

        tracer.start_span = MagicMock(return_value="s-err")
        tracer.end_span = MagicMock(side_effect=RuntimeError("end boom"))

        result = provider.call("test")
        assert result == "safe2"

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_start_span_error_is_logged(self, mock_litellm, caplog):
        mock_litellm.completion.return_value = _fake_response()
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)
        tracer.start_span = MagicMock(side_effect=RuntimeError("start fail"))

        with caplog.at_level(logging.ERROR):
            provider.call("test")

        assert any("Failed to start tracing span" in r.message for r in caplog.records)

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_end_span_error_is_logged(self, mock_litellm, caplog):
        mock_litellm.completion.return_value = _fake_response()
        mock_litellm.completion_cost.return_value = 0.0

        tracer = _make_tracer()
        provider = LiteLLMProvider({"model": "gpt-4o"}, tracer=tracer)
        tracer.start_span = MagicMock(return_value="s-log")
        tracer.end_span = MagicMock(side_effect=RuntimeError("end fail"))

        with caplog.at_level(logging.ERROR):
            provider.call("test")

        assert any("Failed to end tracing span" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Provider works normally when tracer is None
# ---------------------------------------------------------------------------


class TestNoTracerWorks:
    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_without_tracer(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("no-trace")
        mock_litellm.completion_cost.return_value = 0.0

        provider = LiteLLMProvider({"model": "gpt-4o"})
        assert provider.tracer is None

        result = provider.call("hello")
        assert result == "no-trace"
        mock_litellm.completion.assert_called_once()

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_json_without_tracer(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response('{"a": 1}')
        mock_litellm.completion_cost.return_value = 0.0

        provider = LiteLLMProvider({"model": "gpt-4o"})
        result = provider.call_json("json please")
        assert result == {"a": 1}

    @patch("crazypumpkin.llm.litellm_provider.litellm")
    def test_call_multi_turn_without_tracer(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("multi-no-trace")
        mock_litellm.completion_cost.return_value = 0.0

        provider = LiteLLMProvider({"model": "gpt-4o"})
        result = provider.call_multi_turn("prompt")
        assert result == "multi-no-trace"
