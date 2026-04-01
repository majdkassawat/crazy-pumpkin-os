"""Tests for LLM call cost tracking model and storage."""

from datetime import datetime, timedelta

import pytest

from crazypumpkin.observability.cost import CostTracker, LLMUsageRecord


def _make_record(
    agent_name: str = "agent-a",
    provider: str = "openai",
    model: str = "gpt-4",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cached_tokens: int = 0,
    cost_usd: float = 0.01,
    timestamp: datetime | None = None,
    metadata: dict | None = None,
) -> LLMUsageRecord:
    kwargs: dict = dict(
        agent_name=agent_name,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cost_usd=cost_usd,
        metadata=metadata,
    )
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return LLMUsageRecord(**kwargs)


# ---------------------------------------------------------------------------
# LLMUsageRecord
# ---------------------------------------------------------------------------

class TestLLMUsageRecord:
    def test_instantiation_with_required_fields(self):
        rec = LLMUsageRecord(
            agent_name="planner",
            provider="openai",
            model="gpt-4",
            input_tokens=200,
            output_tokens=80,
            cached_tokens=10,
            cost_usd=0.05,
        )
        assert rec.agent_name == "planner"
        assert rec.provider == "openai"
        assert rec.model == "gpt-4"
        assert rec.input_tokens == 200
        assert rec.output_tokens == 80
        assert rec.cached_tokens == 10
        assert rec.cost_usd == 0.05
        assert isinstance(rec.timestamp, datetime)
        assert rec.metadata is None

    def test_custom_timestamp_and_metadata(self):
        ts = datetime(2025, 1, 1, 12, 0, 0)
        rec = LLMUsageRecord(
            agent_name="a",
            provider="p",
            model="m",
            input_tokens=1,
            output_tokens=1,
            cached_tokens=0,
            cost_usd=0.0,
            timestamp=ts,
            metadata={"key": "value"},
        )
        assert rec.timestamp == ts
        assert rec.metadata == {"key": "value"}


# ---------------------------------------------------------------------------
# CostTracker.record
# ---------------------------------------------------------------------------

class TestCostTrackerRecord:
    def test_record_stores_usage(self):
        tracker = CostTracker()
        rec = _make_record()
        tracker.record(rec)
        summary = tracker.get_usage_summary()
        assert summary["record_count"] == 1

    def test_record_multiple(self):
        tracker = CostTracker()
        tracker.record(_make_record(cost_usd=0.01))
        tracker.record(_make_record(cost_usd=0.02))
        tracker.record(_make_record(cost_usd=0.03))
        assert tracker.get_usage_summary()["record_count"] == 3


# ---------------------------------------------------------------------------
# CostTracker.get_spend_by_agent
# ---------------------------------------------------------------------------

class TestGetSpendByAgent:
    def test_correct_cumulative_cost(self):
        tracker = CostTracker()
        tracker.record(_make_record(agent_name="alpha", cost_usd=0.10))
        tracker.record(_make_record(agent_name="alpha", cost_usd=0.20))
        tracker.record(_make_record(agent_name="beta", cost_usd=0.50))
        assert tracker.get_spend_by_agent("alpha") == pytest.approx(0.30)

    def test_unknown_agent_returns_zero(self):
        tracker = CostTracker()
        tracker.record(_make_record(agent_name="alpha", cost_usd=0.10))
        assert tracker.get_spend_by_agent("unknown") == 0.0

    def test_since_filter(self):
        tracker = CostTracker()
        old = datetime(2025, 1, 1)
        recent = datetime(2025, 6, 1)
        tracker.record(_make_record(agent_name="a", cost_usd=0.10, timestamp=old))
        tracker.record(_make_record(agent_name="a", cost_usd=0.20, timestamp=recent))
        cutoff = datetime(2025, 3, 1)
        assert tracker.get_spend_by_agent("a", since=cutoff) == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# CostTracker.get_total_spend
# ---------------------------------------------------------------------------

class TestGetTotalSpend:
    def test_sum_of_all_costs(self):
        tracker = CostTracker()
        tracker.record(_make_record(agent_name="a", cost_usd=0.10))
        tracker.record(_make_record(agent_name="b", cost_usd=0.20))
        tracker.record(_make_record(agent_name="c", cost_usd=0.30))
        assert tracker.get_total_spend() == pytest.approx(0.60)

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.get_total_spend() == 0.0

    def test_since_filter(self):
        tracker = CostTracker()
        old = datetime(2025, 1, 1)
        recent = datetime(2025, 6, 1)
        tracker.record(_make_record(cost_usd=0.10, timestamp=old))
        tracker.record(_make_record(cost_usd=0.20, timestamp=recent))
        cutoff = datetime(2025, 3, 1)
        assert tracker.get_total_spend(since=cutoff) == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# CostTracker.get_usage_summary
# ---------------------------------------------------------------------------

class TestGetUsageSummary:
    def test_per_agent_breakdown(self):
        tracker = CostTracker()
        tracker.record(_make_record(agent_name="alpha", cost_usd=0.10))
        tracker.record(_make_record(agent_name="alpha", cost_usd=0.05))
        tracker.record(_make_record(agent_name="beta", cost_usd=0.30))
        summary = tracker.get_usage_summary()
        assert summary["by_agent"]["alpha"] == pytest.approx(0.15)
        assert summary["by_agent"]["beta"] == pytest.approx(0.30)

    def test_per_model_breakdown(self):
        tracker = CostTracker()
        tracker.record(_make_record(model="gpt-4", cost_usd=0.10))
        tracker.record(_make_record(model="gpt-4", cost_usd=0.05))
        tracker.record(_make_record(model="claude-3", cost_usd=0.20))
        summary = tracker.get_usage_summary()
        assert summary["by_model"]["gpt-4"] == pytest.approx(0.15)
        assert summary["by_model"]["claude-3"] == pytest.approx(0.20)

    def test_total_cost_matches(self):
        tracker = CostTracker()
        tracker.record(_make_record(cost_usd=0.10))
        tracker.record(_make_record(cost_usd=0.20))
        summary = tracker.get_usage_summary()
        assert summary["total_cost_usd"] == pytest.approx(0.30)

    def test_empty_tracker_summary(self):
        tracker = CostTracker()
        summary = tracker.get_usage_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["record_count"] == 0
        assert summary["by_agent"] == {}
        assert summary["by_model"] == {}
