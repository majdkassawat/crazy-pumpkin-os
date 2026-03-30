"""Tests for the Prometheus-compatible metrics export endpoint."""

from __future__ import annotations

import urllib.request

import pytest

from crazypumpkin.observability.export import (
    MetricsHandler,
    format_metrics,
    start_metrics_server,
)
from crazypumpkin.observability.metrics import (
    record_agent_uptime,
    record_error,
    record_task_completed,
    reset,
)


@pytest.fixture(autouse=True)
def _clean_metrics():
    """Reset metrics before each test."""
    reset()
    yield
    reset()


# ---------------------------------------------------------------------------
# format_metrics
# ---------------------------------------------------------------------------

class TestFormatMetrics:
    """Prometheus text exposition format is correct."""

    def test_contains_task_throughput(self):
        record_task_completed(7)
        text = format_metrics()
        assert "# HELP task_throughput" in text
        assert "# TYPE task_throughput gauge" in text
        assert "task_throughput 7" in text

    def test_contains_error_rate_total(self):
        record_error("timeout")
        record_error("validation")
        text = format_metrics()
        assert "# HELP error_rate_total" in text
        assert "# TYPE error_rate_total gauge" in text
        assert "error_rate_total 2" in text

    def test_contains_agent_uptime_seconds(self):
        record_agent_uptime("worker-1")
        text = format_metrics()
        assert "# HELP agent_uptime_seconds" in text
        assert "# TYPE agent_uptime_seconds gauge" in text
        assert 'agent_uptime_seconds{agent_id="worker-1"}' in text

    def test_multiple_agents(self):
        record_agent_uptime("a")
        record_agent_uptime("b")
        text = format_metrics()
        assert 'agent_uptime_seconds{agent_id="a"}' in text
        assert 'agent_uptime_seconds{agent_id="b"}' in text

    def test_default_values(self):
        text = format_metrics()
        assert "task_throughput 0" in text
        assert "error_rate_total 0" in text

    def test_accepts_snapshot(self):
        snapshot = {
            "tasks_completed": 42,
            "errors": 3,
            "agent_uptime": {"x": 1.5},
        }
        text = format_metrics(snapshot)
        assert "task_throughput 42" in text
        assert "error_rate_total 3" in text
        assert 'agent_uptime_seconds{agent_id="x"} 1.500000' in text

    def test_updates_in_real_time(self):
        text1 = format_metrics()
        assert "task_throughput 0" in text1

        record_task_completed(3)
        text2 = format_metrics()
        assert "task_throughput 3" in text2

    def test_trailing_newline(self):
        text = format_metrics()
        assert text.endswith("\n")


# ---------------------------------------------------------------------------
# /metrics HTTP endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    """The HTTP server exposes /metrics."""

    @pytest.fixture()
    def server(self):
        srv = start_metrics_server(port=0, host="127.0.0.1")
        yield srv
        srv.shutdown()

    def test_metrics_endpoint_returns_200(self, server):
        port = server.server_address[1]
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics")
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "task_throughput" in body

    def test_metrics_endpoint_content_type(self, server):
        port = server.server_address[1]
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics")
        ct = resp.headers.get("Content-Type", "")
        assert "text/plain" in ct

    def test_unknown_path_returns_404(self, server):
        port = server.server_address[1]
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
        assert exc_info.value.code == 404

    def test_endpoint_reflects_live_metrics(self, server):
        port = server.server_address[1]
        record_task_completed(5)
        record_error("crash")
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics")
        body = resp.read().decode("utf-8")
        assert "task_throughput 5" in body
        assert "error_rate_total 1" in body
