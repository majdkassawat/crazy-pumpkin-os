"""Tests for the observability cost tracking module."""

from __future__ import annotations

import json
import os

import pytest

from crazypumpkin.observability.cost import CostRecord, CostTracker


# ---------------------------------------------------------------------------
# CostRecord dataclass
# ---------------------------------------------------------------------------

class TestCostRecord:
    """CostRecord dataclass has all specified fields with correct types."""

    def test_required_fields(self):
        rec = CostRecord(
            agent_name="dev",
            product="chat",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.005,
        )
        assert rec.agent_name == "dev"
        assert rec.product == "chat"
        assert rec.model == "gpt-4"
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50
        assert rec.cost_usd == 0.005

    def test_default_cached_tokens(self):
        rec = CostRecord(
            agent_name="a", product="p", model="m",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
        assert rec.cached_tokens == 0

    def test_default_timestamp_is_iso(self):
        rec = CostRecord(
            agent_name="a", product="p", model="m",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
        assert rec.timestamp  # non-empty
        # Should be parseable as ISO
        from datetime import datetime
        datetime.fromisoformat(rec.timestamp)

    def test_default_metadata_is_none(self):
        rec = CostRecord(
            agent_name="a", product="p", model="m",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
        assert rec.metadata is None

    def test_custom_metadata(self):
        rec = CostRecord(
            agent_name="a", product="p", model="m",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            metadata={"run_id": "abc"},
        )
        assert rec.metadata == {"run_id": "abc"}


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------

class TestCostTrackerRecord:
    """CostTracker.record() appends a JSON line to the JSONL file."""

    def test_record_creates_file_and_appends(self, tmp_path):
        tracker = CostTracker(store_path="costs.jsonl", base_dir=str(tmp_path))

        rec = CostRecord(
            agent_name="dev", product="chat", model="gpt-4",
            input_tokens=100, output_tokens=50, cost_usd=0.005,
        )
        tracker.record(rec)

        store = str(tmp_path / "costs.jsonl")
        assert os.path.exists(store)
        with open(store) as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_name"] == "dev"
        assert data["cost_usd"] == 0.005

    def test_record_appends_multiple(self, tmp_path):
        tracker = CostTracker(store_path="costs.jsonl", base_dir=str(tmp_path))

        for i in range(3):
            tracker.record(CostRecord(
                agent_name=f"agent-{i}", product="p", model="m",
                input_tokens=i, output_tokens=i, cost_usd=float(i),
            ))

        with open(tmp_path / "costs.jsonl") as f:
            lines = f.readlines()
        assert len(lines) == 3

    def test_record_creates_parent_dirs(self, tmp_path):
        tracker = CostTracker(
            store_path="sub/dir/costs.jsonl", base_dir=str(tmp_path),
        )
        tracker.record(CostRecord(
            agent_name="a", product="p", model="m",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        ))
        assert os.path.exists(tmp_path / "sub" / "dir" / "costs.jsonl")


class TestCostTrackerQuery:
    """CostTracker.query() returns filtered list of CostRecord objects."""

    @pytest.fixture()
    def tracker(self, tmp_path):
        t = CostTracker(store_path="costs.jsonl", base_dir=str(tmp_path))
        t.record(CostRecord(
            agent_name="dev", product="chat", model="gpt-4",
            input_tokens=100, output_tokens=50, cost_usd=0.01,
            timestamp="2026-01-01T00:00:00+00:00",
        ))
        t.record(CostRecord(
            agent_name="dev", product="code", model="gpt-4",
            input_tokens=200, output_tokens=100, cost_usd=0.02,
            timestamp="2026-02-01T00:00:00+00:00",
        ))
        t.record(CostRecord(
            agent_name="qa", product="chat", model="claude-3",
            input_tokens=50, output_tokens=25, cost_usd=0.005,
            timestamp="2026-03-01T00:00:00+00:00",
        ))
        return t

    def test_query_all(self, tracker):
        results = tracker.query()
        assert len(results) == 3
        assert all(isinstance(r, CostRecord) for r in results)

    def test_query_by_agent_name(self, tracker):
        results = tracker.query(agent_name="dev")
        assert len(results) == 2
        assert all(r.agent_name == "dev" for r in results)

    def test_query_by_product(self, tracker):
        results = tracker.query(product="chat")
        assert len(results) == 2
        assert all(r.product == "chat" for r in results)

    def test_query_by_since(self, tracker):
        results = tracker.query(since="2026-02-01T00:00:00+00:00")
        assert len(results) == 2

    def test_query_combined_filters(self, tracker):
        results = tracker.query(agent_name="dev", product="chat")
        assert len(results) == 1
        assert results[0].cost_usd == 0.01

    def test_query_no_match(self, tracker):
        results = tracker.query(agent_name="nonexistent")
        assert results == []


class TestCostTrackerSummary:
    """CostTracker.summary() returns correct aggregated totals."""

    @pytest.fixture()
    def tracker(self, tmp_path):
        t = CostTracker(store_path="costs.jsonl", base_dir=str(tmp_path))
        t.record(CostRecord(
            agent_name="dev", product="chat", model="gpt-4",
            input_tokens=100, output_tokens=50, cost_usd=0.01,
        ))
        t.record(CostRecord(
            agent_name="dev", product="code", model="gpt-4",
            input_tokens=200, output_tokens=100, cost_usd=0.02,
        ))
        t.record(CostRecord(
            agent_name="qa", product="chat", model="claude-3",
            input_tokens=50, output_tokens=25, cost_usd=0.005,
        ))
        return t

    def test_summary_by_agent_name(self, tracker):
        result = tracker.summary(group_by="agent_name")
        assert pytest.approx(result["dev"]) == 0.03
        assert pytest.approx(result["qa"]) == 0.005

    def test_summary_by_product(self, tracker):
        result = tracker.summary(group_by="product")
        assert pytest.approx(result["chat"]) == 0.015
        assert pytest.approx(result["code"]) == 0.02

    def test_summary_by_model(self, tracker):
        result = tracker.summary(group_by="model")
        assert pytest.approx(result["gpt-4"]) == 0.03
        assert pytest.approx(result["claude-3"]) == 0.005


class TestCostTrackerEmptyStore:
    """CostTracker works with an empty/nonexistent store file."""

    def test_query_nonexistent_file(self, tmp_path):
        tracker = CostTracker(store_path="nope.jsonl", base_dir=str(tmp_path))
        assert tracker.query() == []

    def test_summary_nonexistent_file(self, tmp_path):
        tracker = CostTracker(store_path="nope.jsonl", base_dir=str(tmp_path))
        assert tracker.summary() == {}

    def test_query_empty_file(self, tmp_path):
        (tmp_path / "empty.jsonl").write_text("")
        tracker = CostTracker(store_path="empty.jsonl", base_dir=str(tmp_path))
        assert tracker.query() == []


class TestCostTrackerPathTraversal:
    """CostTracker rejects store_path values that escape base_dir."""

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="escapes base directory"):
            CostTracker(store_path="../evil.jsonl", base_dir=str(tmp_path))

    def test_rejects_deep_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="escapes base directory"):
            CostTracker(
                store_path="sub/../../etc/passwd", base_dir=str(tmp_path),
            )

    def test_allows_subdirectory(self, tmp_path):
        tracker = CostTracker(
            store_path="sub/costs.jsonl", base_dir=str(tmp_path),
        )
        assert tracker.store_path == os.path.join(str(tmp_path), "sub", "costs.jsonl")
