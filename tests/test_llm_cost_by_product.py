"""Tests for per-product LLM cost tracking."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from crazypumpkin.llm.base import CallCost, CostTracker, LLMProvider


# ---------------------------------------------------------------------------
# CostTracker.record() accepts product_id
# ---------------------------------------------------------------------------

class TestCostTrackerProductId:
    def test_record_with_product_id(self):
        tracker = CostTracker()
        cost = CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01)
        tracker.record("model-a", cost, product_id="product-x")
        summary = tracker.get_summary_by_product()
        assert "product-x" in summary

    def test_record_without_product_id_does_not_add_entry(self):
        tracker = CostTracker()
        cost = CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01)
        tracker.record("model-a", cost)
        assert tracker.get_summary_by_product() == {}

    def test_record_with_product_id_none_does_not_add_entry(self):
        tracker = CostTracker()
        cost = CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01)
        tracker.record("model-a", cost, product_id=None)
        assert tracker.get_summary_by_product() == {}


# ---------------------------------------------------------------------------
# get_summary_by_product() returns correct totals for 2+ products
# ---------------------------------------------------------------------------

class TestGetSummaryByProduct:
    def test_single_product_totals(self):
        tracker = CostTracker()
        tracker.record("m1", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01), product_id="alpha")
        tracker.record("m1", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.02), product_id="alpha")
        summary = tracker.get_summary_by_product()
        assert summary["alpha"]["total_cost_usd"] == pytest.approx(0.03)
        assert summary["alpha"]["call_count"] == 2
        assert summary["alpha"]["total_prompt_tokens"] == 300
        assert summary["alpha"]["total_completion_tokens"] == 130

    def test_two_products_separate_totals(self):
        tracker = CostTracker()
        tracker.record("m1", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01), product_id="alpha")
        tracker.record("m2", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.05), product_id="beta")
        tracker.record("m1", CallCost(prompt_tokens=50, completion_tokens=25, cost_usd=0.005), product_id="alpha")

        summary = tracker.get_summary_by_product()
        assert len(summary) == 2

        assert summary["alpha"]["total_cost_usd"] == pytest.approx(0.015)
        assert summary["alpha"]["call_count"] == 2
        assert summary["alpha"]["total_prompt_tokens"] == 150
        assert summary["alpha"]["total_completion_tokens"] == 75

        assert summary["beta"]["total_cost_usd"] == pytest.approx(0.05)
        assert summary["beta"]["call_count"] == 1
        assert summary["beta"]["total_prompt_tokens"] == 200
        assert summary["beta"]["total_completion_tokens"] == 80

    def test_summary_keys(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001), product_id="p")
        entry = tracker.get_summary_by_product()["p"]
        assert set(entry.keys()) == {"total_cost_usd", "call_count", "total_prompt_tokens", "total_completion_tokens"}

    def test_reset_clears_product_data(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001), product_id="p")
        tracker.reset()
        assert tracker.get_summary_by_product() == {}

    def test_mixed_product_and_no_product(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01), product_id="alpha")
        tracker.record("m", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.02))  # no product_id
        summary = tracker.get_summary_by_product()
        assert len(summary) == 1
        assert summary["alpha"]["call_count"] == 1


# ---------------------------------------------------------------------------
# LLMProvider.call() signature accepts product_id
# ---------------------------------------------------------------------------

class TestLLMProviderSignature:
    def test_call_accepts_product_id(self):
        sig = inspect.signature(LLMProvider.call)
        assert "product_id" in sig.parameters
        param = sig.parameters["product_id"]
        assert param.default is None

    def test_call_multi_turn_accepts_product_id(self):
        sig = inspect.signature(LLMProvider.call_multi_turn)
        assert "product_id" in sig.parameters
        param = sig.parameters["product_id"]
        assert param.default is None


# ---------------------------------------------------------------------------
# AnthropicProvider forwards product_id to tracker
# ---------------------------------------------------------------------------

class TestAnthropicProviderProductId:
    def test_call_forwards_product_id(self):
        with patch("crazypumpkin.llm.anthropic_api.Anthropic") as MockAnthropic:
            # Set up mock response
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "hello"
            mock_usage = MagicMock()
            mock_usage.input_tokens = 10
            mock_usage.output_tokens = 5
            mock_usage.cache_creation_input_tokens = 0
            mock_usage.cache_read_input_tokens = 0
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.usage = mock_usage
            MockAnthropic.return_value.messages.create.return_value = mock_response

            with patch("crazypumpkin.llm.anthropic_api.get_default_tracker") as mock_get_tracker:
                mock_tracker = MagicMock()
                mock_get_tracker.return_value = mock_tracker

                from crazypumpkin.llm.anthropic_api import AnthropicProvider
                provider = AnthropicProvider({"api_key": "test-key"})
                provider.call("hello", product_id="my-product")

                mock_tracker.record.assert_called_once()
                call_kwargs = mock_tracker.record.call_args
                assert call_kwargs.kwargs.get("product_id") == "my-product" or \
                    (len(call_kwargs.args) >= 1 and call_kwargs[1].get("product_id") == "my-product")

    def test_call_without_product_id_passes_none(self):
        with patch("crazypumpkin.llm.anthropic_api.Anthropic") as MockAnthropic:
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "hello"
            mock_usage = MagicMock()
            mock_usage.input_tokens = 10
            mock_usage.output_tokens = 5
            mock_usage.cache_creation_input_tokens = 0
            mock_usage.cache_read_input_tokens = 0
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.usage = mock_usage
            MockAnthropic.return_value.messages.create.return_value = mock_response

            with patch("crazypumpkin.llm.anthropic_api.get_default_tracker") as mock_get_tracker:
                mock_tracker = MagicMock()
                mock_get_tracker.return_value = mock_tracker

                from crazypumpkin.llm.anthropic_api import AnthropicProvider
                provider = AnthropicProvider({"api_key": "test-key"})
                provider.call("hello")

                mock_tracker.record.assert_called_once()
                call_kwargs = mock_tracker.record.call_args
                assert call_kwargs.kwargs.get("product_id") is None


# ---------------------------------------------------------------------------
# LiteLLMProvider forwards product_id to tracker
# ---------------------------------------------------------------------------

class TestLiteLLMProviderProductId:
    def test_call_forwards_product_id(self):
        with patch("crazypumpkin.llm.litellm_provider.litellm") as mock_litellm:
            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 20
            mock_usage.completion_tokens = 10
            mock_message = MagicMock()
            mock_message.content = "hi"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            mock_litellm.completion.return_value = mock_response
            mock_litellm.completion_cost.return_value = 0.001

            with patch("crazypumpkin.llm.litellm_provider.get_default_tracker") as mock_get_tracker:
                mock_tracker = MagicMock()
                mock_get_tracker.return_value = mock_tracker

                with patch("crazypumpkin.llm.litellm_provider.get_cost_tracker") as mock_get_cost_tracker:
                    mock_obs_tracker = MagicMock()
                    mock_get_cost_tracker.return_value = mock_obs_tracker

                    from crazypumpkin.llm.litellm_provider import LiteLLMProvider
                    provider = LiteLLMProvider({"api_key": "test-key"})
                    provider.call("hello", product_id="my-product")

                    mock_tracker.record.assert_called_once()
                    call_kwargs = mock_tracker.record.call_args
                    assert call_kwargs.kwargs.get("product_id") == "my-product"

    def test_call_multi_turn_forwards_product_id(self):
        with patch("crazypumpkin.llm.litellm_provider.litellm") as mock_litellm:
            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 20
            mock_usage.completion_tokens = 10
            mock_message = MagicMock()
            mock_message.content = "hi"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            mock_litellm.completion.return_value = mock_response
            mock_litellm.completion_cost.return_value = 0.001

            with patch("crazypumpkin.llm.litellm_provider.get_default_tracker") as mock_get_tracker:
                mock_tracker = MagicMock()
                mock_get_tracker.return_value = mock_tracker

                with patch("crazypumpkin.llm.litellm_provider.get_cost_tracker") as mock_get_cost_tracker:
                    mock_obs_tracker = MagicMock()
                    mock_get_cost_tracker.return_value = mock_obs_tracker

                    from crazypumpkin.llm.litellm_provider import LiteLLMProvider
                    provider = LiteLLMProvider({"api_key": "test-key"})
                    provider.call_multi_turn("hello", product_id="my-product")

                    mock_tracker.record.assert_called_once()
                    call_kwargs = mock_tracker.record.call_args
                    assert call_kwargs.kwargs.get("product_id") == "my-product"
