"""Unit tests for crazypumpkin.framework.metrics."""

import sys
from pathlib import Path

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.metrics import AgentMetrics


def test_record_and_summary():
    m = AgentMetrics()
    m.record_execution("a1", 1.5)
    m.record_execution("a1", 2.5, tokens={"prompt_tokens": 100, "completion_tokens": 50})
    summary = m.get_summary("a1")
    assert summary["execution_count"] == 2
    assert summary["total_duration"] == pytest.approx(4.0)
    assert summary["avg_duration"] == pytest.approx(2.0)
    assert summary["token_usage"]["prompt_tokens"] == 100
    assert summary["token_usage"]["completion_tokens"] == 50


def test_error_tracking():
    m = AgentMetrics()
    m.record_execution("a1", 1.0, error=False)
    m.record_execution("a1", 1.0, error=True)
    m.record_execution("a1", 1.0, error=False)
    summary = m.get_summary("a1")
    assert summary["error_count"] == 1
    assert summary["error_rate"] == pytest.approx(1 / 3)


def test_reset():
    m = AgentMetrics()
    m.record_execution("a1", 1.0, tokens={"prompt_tokens": 10, "completion_tokens": 5}, error=True)
    m.reset()
    summary = m.get_summary("a1")
    assert summary["execution_count"] == 0
    assert summary["total_duration"] == 0.0
    assert summary["avg_duration"] == 0.0
    assert summary["token_usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
    assert summary["error_count"] == 0
    assert summary["error_rate"] == 0.0


def test_unknown_agent_summary():
    m = AgentMetrics()
    summary = m.get_summary("nonexistent")
    assert summary["execution_count"] == 0
    assert summary["total_duration"] == 0.0
    assert summary["avg_duration"] == 0.0
    assert summary["token_usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
    assert summary["error_count"] == 0
    assert summary["error_rate"] == 0.0
