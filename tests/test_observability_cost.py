"""Tests for per-product CostTracker and Langfuse export."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from crazypumpkin.observability.cost import CostRecord, CostTracker
from crazypumpkin.observability.tracing import (
    LangfuseTracer,
    configure_tracer,
    get_tracer,
    reset_tracer,
)


@pytest.fixture(autouse=True)
def _clean_tracer():
    """Ensure no global tracer leaks between tests."""
    reset_tracer()
    yield
    reset_tracer()


# ── CostRecord dataclass ────────────────────────────────────────────────────

class TestCostRecord:
    def test_stores_all_fields(self):
        rec = CostRecord(
            agent_name="writer",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.02,
        )
        assert rec.agent_name == "writer"
        assert rec.model == "gpt-4"
        assert rec.prompt_tokens == 100
        assert rec.completion_tokens == 50
        assert rec.cost_usd == 0.02

    def test_default_product(self):
        rec = CostRecord(
            agent_name="a", model="m", prompt_tokens=0,
            completion_tokens=0, cost_usd=0.0,
        )
        assert rec.product == "crazy-pumpkin-os"

    def test_custom_product(self):
        rec = CostRecord(
            agent_name="a", model="m", prompt_tokens=0,
            completion_tokens=0, cost_usd=0.0, product="other-product",
        )
        assert rec.product == "other-product"

    def test_timestamp_is_utc_datetime(self):
        rec = CostRecord(
            agent_name="a", model="m", prompt_tokens=0,
            completion_tokens=0, cost_usd=0.0,
        )
        assert isinstance(rec.timestamp, datetime)
        assert rec.timestamp.tzinfo is not None

    def test_has_expected_dataclass_fields(self):
        names = {f.name for f in fields(CostRecord)}
        expected = {
            "agent_name", "model", "prompt_tokens",
            "completion_tokens", "cost_usd", "product", "timestamp",
        }
        assert expected == names


# ── CostTracker.record() ────────────────────────────────────────────────────

class TestCostTrackerRecord:
    def test_record_returns_cost_record(self):
        tracker = CostTracker()
        rec = tracker.record("agent-a", "gpt-4", 100, 50, 0.01)
        assert isinstance(rec, CostRecord)
        assert rec.agent_name == "agent-a"
        assert rec.model == "gpt-4"

    def test_record_stores_entry(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.001)
        assert tracker.total_spend() == pytest.approx(0.001)

    def test_record_with_custom_product(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01, product="widget")
        assert "widget" in tracker.spend_by_product()

    def test_record_calls_tracer_when_configured(self):
        mock_client = MagicMock()
        configure_tracer(mock_client)
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        mock_client.generation.assert_called_once()

    def test_record_no_tracer_no_error(self):
        tracker = CostTracker()
        rec = tracker.record("a", "m", 10, 5, 0.01)
        assert rec is not None


# ── spend_by_product() ──────────────────────────────────────────────────────

class TestSpendByProduct:
    def test_single_product(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        tracker.record("b", "m", 10, 5, 0.02)
        result = tracker.spend_by_product()
        assert result == {"crazy-pumpkin-os": pytest.approx(0.03)}

    def test_multiple_products(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01, product="alpha")
        tracker.record("b", "m", 10, 5, 0.02, product="beta")
        tracker.record("c", "m", 10, 5, 0.03, product="alpha")
        result = tracker.spend_by_product()
        assert result["alpha"] == pytest.approx(0.04)
        assert result["beta"] == pytest.approx(0.02)

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.spend_by_product() == {}


# ── spend_by_agent() ────────────────────────────────────────────────────────

class TestSpendByAgent:
    def test_all_agents(self):
        tracker = CostTracker()
        tracker.record("writer", "m", 10, 5, 0.01)
        tracker.record("reviewer", "m", 10, 5, 0.02)
        tracker.record("writer", "m", 10, 5, 0.03)
        result = tracker.spend_by_agent()
        assert result["writer"] == pytest.approx(0.04)
        assert result["reviewer"] == pytest.approx(0.02)

    def test_filtered_by_product(self):
        tracker = CostTracker()
        tracker.record("writer", "m", 10, 5, 0.01, product="alpha")
        tracker.record("writer", "m", 10, 5, 0.05, product="beta")
        tracker.record("reviewer", "m", 10, 5, 0.02, product="alpha")
        result = tracker.spend_by_agent(product="alpha")
        assert result["writer"] == pytest.approx(0.01)
        assert result["reviewer"] == pytest.approx(0.02)
        assert "beta" not in result

    def test_filter_unknown_product(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        assert tracker.spend_by_agent(product="nonexistent") == {}

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.spend_by_agent() == {}


# ── total_spend() ───────────────────────────────────────────────────────────

class TestTotalSpend:
    def test_sum_of_all(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        tracker.record("b", "m", 10, 5, 0.02)
        tracker.record("c", "m", 10, 5, 0.03)
        assert tracker.total_spend() == pytest.approx(0.06)

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.total_spend() == 0.0


# ── export_to_langfuse() ────────────────────────────────────────────────────

class TestExportToLangfuse:
    def test_returns_zero_no_tracer(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        assert tracker.export_to_langfuse() == 0

    def test_returns_record_count_with_tracer(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        tracker.record("b", "m", 10, 5, 0.02)
        # Now configure tracer and export
        mock_client = MagicMock()
        configure_tracer(mock_client)
        count = tracker.export_to_langfuse()
        assert count == 2

    def test_does_not_resend_synced_records(self):
        mock_client = MagicMock()
        configure_tracer(mock_client)
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        tracker.export_to_langfuse()
        mock_client.generation.reset_mock()

        # Second export with no new records
        count = tracker.export_to_langfuse()
        assert count == 0
        mock_client.generation.assert_not_called()

    def test_sends_only_new_records(self):
        tracker = CostTracker()
        tracker.record("a", "m", 10, 5, 0.01)
        tracker.record("b", "m", 10, 5, 0.02)

        # Configure tracer and export — both records are unsynced
        mock_client = MagicMock()
        configure_tracer(mock_client)
        tracker.export_to_langfuse()
        mock_client.generation.reset_mock()

        # Add a third record without tracer so it is unsynced
        reset_tracer()
        tracker.record("c", "m", 10, 5, 0.03)

        # Re-configure tracer and export — only the new record
        configure_tracer(mock_client)
        count = tracker.export_to_langfuse()
        assert count == 1
        mock_client.generation.assert_called_once()

    def test_empty_tracker_returns_zero(self):
        mock_client = MagicMock()
        configure_tracer(mock_client)
        tracker = CostTracker()
        assert tracker.export_to_langfuse() == 0
