"""Unit tests for crazypumpkin.framework.metrics."""

import sys
from pathlib import Path

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.metrics import AgentMetrics, default_metrics


@pytest.fixture
def metrics():
    return AgentMetrics()


class TestRecordExecution:
    def test_increments_count_and_accumulates_duration(self, metrics):
        metrics.record_execution("a1", 1.5)
        metrics.record_execution("a1", 2.5)
        assert metrics.execution_count["a1"] == 2
        assert metrics.total_duration["a1"] == pytest.approx(4.0)

    def test_error_increments_error_count(self, metrics):
        metrics.record_execution("a1", 1.0, error=True)
        metrics.record_execution("a1", 1.0, error=False)
        assert metrics.error_count["a1"] == 1

    def test_tokens_accumulate(self, metrics):
        metrics.record_execution("a1", 1.0, tokens={"prompt_tokens": 10, "completion_tokens": 20})
        metrics.record_execution("a1", 1.0, tokens={"prompt_tokens": 5, "completion_tokens": 15})
        assert metrics.token_usage["a1"]["prompt_tokens"] == 15
        assert metrics.token_usage["a1"]["completion_tokens"] == 35


class TestGetSummary:
    def test_avg_duration_and_error_rate(self, metrics):
        metrics.record_execution("a1", 2.0, error=True)
        metrics.record_execution("a1", 4.0, error=False)
        summary = metrics.get_summary("a1")
        assert summary["execution_count"] == 2
        assert summary["total_duration"] == pytest.approx(6.0)
        assert summary["avg_duration"] == pytest.approx(3.0)
        assert summary["error_count"] == 1
        assert summary["error_rate"] == pytest.approx(0.5)

    def test_summary_for_unknown_agent(self, metrics):
        summary = metrics.get_summary("unknown")
        assert summary["execution_count"] == 0
        assert summary["avg_duration"] == 0.0
        assert summary["error_rate"] == 0.0


class TestReset:
    def test_clears_all_counters(self, metrics):
        metrics.record_execution("a1", 1.0, tokens={"prompt_tokens": 5, "completion_tokens": 5}, error=True)
        metrics.reset()
        assert metrics.execution_count == {}
        assert metrics.total_duration == {}
        assert metrics.token_usage == {}
        assert metrics.error_count == {}


class TestDefaultMetrics:
    def test_default_metrics_is_agent_metrics_instance(self):
        assert isinstance(default_metrics, AgentMetrics)
