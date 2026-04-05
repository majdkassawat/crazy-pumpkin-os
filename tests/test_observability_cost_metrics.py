"""Tests for per-product cost snapshot in observability metrics."""

from __future__ import annotations

import pytest

from crazypumpkin.llm.base import CallCost, get_default_tracker
from crazypumpkin.observability.metrics import (
    get_cost_by_product_snapshot,
    get_metrics_snapshot,
    reset,
)


@pytest.fixture(autouse=True)
def _clean():
    """Reset metrics and cost tracker between tests."""
    reset()
    get_default_tracker().reset()
    yield
    reset()
    get_default_tracker().reset()


class TestGetCostByProductSnapshot:
    def test_returns_dict_with_product_keys(self):
        tracker = get_default_tracker()
        tracker.record("model-a", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.01), product_id="product-x")
        tracker.record("model-a", CallCost(prompt_tokens=20, completion_tokens=10, cost_usd=0.02), product_id="product-y")

        result = get_cost_by_product_snapshot()
        assert isinstance(result, dict)
        assert "product-x" in result
        assert "product-y" in result

    def test_product_values_are_cost_dicts(self):
        tracker = get_default_tracker()
        tracker.record("model-a", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.01), product_id="product-x")

        result = get_cost_by_product_snapshot()
        cost = result["product-x"]
        assert cost["total_cost_usd"] == pytest.approx(0.01)
        assert cost["call_count"] == 1
        assert cost["total_prompt_tokens"] == 10
        assert cost["total_completion_tokens"] == 5

    def test_empty_when_no_costs(self):
        result = get_cost_by_product_snapshot()
        assert result == {}

    def test_aggregates_multiple_calls_per_product(self):
        tracker = get_default_tracker()
        tracker.record("model-a", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.01), product_id="p1")
        tracker.record("model-b", CallCost(prompt_tokens=20, completion_tokens=10, cost_usd=0.03), product_id="p1")

        result = get_cost_by_product_snapshot()
        assert result["p1"]["total_cost_usd"] == pytest.approx(0.04)
        assert result["p1"]["call_count"] == 2
        assert result["p1"]["total_prompt_tokens"] == 30
        assert result["p1"]["total_completion_tokens"] == 15


class TestGetMetricsSnapshotLLMKeys:
    def test_includes_llm_costs_key(self):
        snapshot = get_metrics_snapshot()
        assert "llm_costs" in snapshot

    def test_includes_llm_costs_by_product_key(self):
        snapshot = get_metrics_snapshot()
        assert "llm_costs_by_product" in snapshot

    def test_llm_costs_empty_state(self):
        snapshot = get_metrics_snapshot()
        assert snapshot["llm_costs"]["total_cost_usd"] == 0.0
        assert snapshot["llm_costs"]["call_count"] == 0

    def test_llm_costs_by_product_empty_state(self):
        snapshot = get_metrics_snapshot()
        assert snapshot["llm_costs_by_product"] == {}

    def test_llm_costs_reflects_recorded_data(self):
        tracker = get_default_tracker()
        tracker.record("model-a", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.05))

        snapshot = get_metrics_snapshot()
        assert snapshot["llm_costs"]["total_cost_usd"] == pytest.approx(0.05)
        assert snapshot["llm_costs"]["call_count"] == 1

    def test_llm_costs_by_product_reflects_recorded_data(self):
        tracker = get_default_tracker()
        tracker.record("model-a", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.01), product_id="prod-a")
        tracker.record("model-a", CallCost(prompt_tokens=20, completion_tokens=10, cost_usd=0.02), product_id="prod-b")

        snapshot = get_metrics_snapshot()
        by_product = snapshot["llm_costs_by_product"]
        assert by_product["prod-a"]["total_cost_usd"] == pytest.approx(0.01)
        assert by_product["prod-b"]["total_cost_usd"] == pytest.approx(0.02)
