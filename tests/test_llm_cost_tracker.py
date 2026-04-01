"""Tests for CostTracker session-level cost accumulator."""

import threading
from dataclasses import fields

import pytest

from crazypumpkin.llm.base import CallCost, CostTracker, get_default_tracker


class TestCallCostCacheFields:
    def test_cache_creation_tokens_default(self):
        cost = CallCost()
        assert cost.cache_creation_tokens == 0

    def test_cache_read_tokens_default(self):
        cost = CallCost()
        assert cost.cache_read_tokens == 0

    def test_cache_fields_are_dataclass_fields(self):
        names = {f.name for f in fields(CallCost)}
        assert "cache_creation_tokens" in names
        assert "cache_read_tokens" in names

    def test_cache_fields_custom_values(self):
        cost = CallCost(cache_creation_tokens=42, cache_read_tokens=99)
        assert cost.cache_creation_tokens == 42
        assert cost.cache_read_tokens == 99


class TestCostTrackerRecord:
    def test_single_record(self):
        tracker = CostTracker()
        cost = CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
                        cache_creation_tokens=10, cache_read_tokens=20)
        tracker.record("model-a", cost)
        summary = tracker.get_summary()
        assert summary["total_prompt_tokens"] == 100
        assert summary["total_completion_tokens"] == 50
        assert summary["total_cost_usd"] == pytest.approx(0.01)
        assert summary["total_cache_creation_tokens"] == 10
        assert summary["total_cache_read_tokens"] == 20
        assert summary["call_count"] == 1

    def test_accumulates_multiple_calls(self):
        tracker = CostTracker()
        tracker.record("m1", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
                                      cache_creation_tokens=5, cache_read_tokens=10))
        tracker.record("m1", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.02,
                                      cache_creation_tokens=15, cache_read_tokens=30))
        summary = tracker.get_summary()
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 130
        assert summary["total_cost_usd"] == pytest.approx(0.03)
        assert summary["total_cache_creation_tokens"] == 20
        assert summary["total_cache_read_tokens"] == 40
        assert summary["call_count"] == 2

    def test_multiple_models(self):
        tracker = CostTracker()
        tracker.record("model-a", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01))
        tracker.record("model-b", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.05))
        summary = tracker.get_summary()
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 130
        assert summary["total_cost_usd"] == pytest.approx(0.06)
        assert summary["call_count"] == 2
        assert "model-a" in summary["by_model"]
        assert "model-b" in summary["by_model"]
        assert summary["by_model"]["model-a"]["total_prompt_tokens"] == 100
        assert summary["by_model"]["model-b"]["total_prompt_tokens"] == 200


class TestCostTrackerGetSummary:
    def test_empty_tracker_summary(self):
        tracker = CostTracker()
        summary = tracker.get_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_prompt_tokens"] == 0
        assert summary["total_completion_tokens"] == 0
        assert summary["total_cache_read_tokens"] == 0
        assert summary["total_cache_creation_tokens"] == 0
        assert summary["by_model"] == {}
        assert summary["call_count"] == 0

    def test_summary_has_all_required_keys(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=1, completion_tokens=1, cost_usd=0.001))
        summary = tracker.get_summary()
        required = {"total_cost_usd", "total_prompt_tokens", "total_completion_tokens",
                     "total_cache_read_tokens", "total_cache_creation_tokens",
                     "by_model", "call_count"}
        assert required.issubset(summary.keys())

    def test_by_model_has_same_fields(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001,
                                     cache_creation_tokens=2, cache_read_tokens=3))
        model_summary = tracker.get_summary()["by_model"]["m"]
        assert model_summary["total_cost_usd"] == pytest.approx(0.001)
        assert model_summary["total_prompt_tokens"] == 10
        assert model_summary["total_completion_tokens"] == 5
        assert model_summary["total_cache_read_tokens"] == 3
        assert model_summary["total_cache_creation_tokens"] == 2
        assert model_summary["call_count"] == 1


class TestCostTrackerReset:
    def test_reset_clears_all(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
                                     cache_creation_tokens=5, cache_read_tokens=10))
        tracker.reset()
        summary = tracker.get_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_prompt_tokens"] == 0
        assert summary["total_completion_tokens"] == 0
        assert summary["total_cache_read_tokens"] == 0
        assert summary["total_cache_creation_tokens"] == 0
        assert summary["by_model"] == {}
        assert summary["call_count"] == 0

    def test_record_after_reset(self):
        tracker = CostTracker()
        tracker.record("m", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01))
        tracker.reset()
        tracker.record("m2", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001))
        summary = tracker.get_summary()
        assert summary["total_prompt_tokens"] == 10
        assert summary["call_count"] == 1
        assert "m" not in summary["by_model"]
        assert "m2" in summary["by_model"]


class TestCostTrackerThreadSafety:
    def test_concurrent_records(self):
        tracker = CostTracker()
        n_threads = 10
        n_calls = 100
        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()
            for _ in range(n_calls):
                tracker.record("m", CallCost(prompt_tokens=1, completion_tokens=1, cost_usd=0.001))

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = tracker.get_summary()
        expected = n_threads * n_calls
        assert summary["total_prompt_tokens"] == expected
        assert summary["total_completion_tokens"] == expected
        assert summary["total_cost_usd"] == pytest.approx(expected * 0.001)
        assert summary["call_count"] == expected


class TestGetDefaultTracker:
    def test_returns_cost_tracker(self):
        tracker = get_default_tracker()
        assert isinstance(tracker, CostTracker)

    def test_returns_singleton(self):
        assert get_default_tracker() is get_default_tracker()
