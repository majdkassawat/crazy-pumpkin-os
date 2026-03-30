"""Tests for the observability package (structured logging + metrics)."""

from __future__ import annotations

import logging
from contextvars import copy_context

import pytest

from crazypumpkin.observability.logging import (
    CorrelationFilter,
    correlation_id_var,
    get_logger,
)
from crazypumpkin.observability.metrics import (
    get_metrics_snapshot,
    record_agent_uptime,
    record_error,
    record_task_completed,
    reset,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestGetLogger:
    """get_logger returns a logger with correlation ID in every record."""

    def setup_method(self):
        correlation_id_var.set("")

    def test_explicit_correlation_id(self):
        logger = get_logger("test.explicit", correlation_id="abc-123")
        assert correlation_id_var.get() == "abc-123"
        assert any(isinstance(f, CorrelationFilter) for f in logger.filters)

    def test_auto_generated_correlation_id(self):
        get_logger("test.auto")
        cid = correlation_id_var.get()
        assert cid  # non-empty
        assert len(cid) == 12  # uuid4 hex[:12]

    def test_preserves_existing_correlation_id(self):
        correlation_id_var.set("existing-id")
        get_logger("test.preserve")
        assert correlation_id_var.get() == "existing-id"

    def test_correlation_id_in_log_record(self, caplog):
        logger = get_logger("test.record", correlation_id="req-42")
        with caplog.at_level(logging.DEBUG, logger="test.record"):
            logger.info("hello")
        assert len(caplog.records) == 1
        assert caplog.records[0].correlation_id == "req-42"  # type: ignore[attr-defined]

    def test_no_duplicate_filters(self):
        logger = get_logger("test.dup", correlation_id="a")
        get_logger("test.dup", correlation_id="b")
        count = sum(1 for f in logger.filters if isinstance(f, CorrelationFilter))
        assert count == 1


class TestCorrelationPropagation:
    """Correlation ID propagates across nested calls via contextvars."""

    def setup_method(self):
        correlation_id_var.set("")

    def test_nested_loggers_share_correlation_id(self):
        get_logger("outer", correlation_id="shared-id")
        inner_logger = get_logger("inner")  # should inherit
        assert correlation_id_var.get() == "shared-id"
        # Inner logger also has the filter
        assert any(isinstance(f, CorrelationFilter) for f in inner_logger.filters)

    def test_context_copy_isolation(self):
        """A copied context should see the correlation ID set before the copy."""
        get_logger("parent", correlation_id="parent-id")

        def _child():
            assert correlation_id_var.get() == "parent-id"
            correlation_id_var.set("child-id")
            assert correlation_id_var.get() == "child-id"

        ctx = copy_context()
        ctx.run(_child)
        # Parent context unchanged
        assert correlation_id_var.get() == "parent-id"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    """Counters and gauges update correctly."""

    def setup_method(self):
        reset()

    def test_record_task_completed(self):
        record_task_completed()
        record_task_completed(count=5)
        snap = get_metrics_snapshot()
        assert snap["tasks_completed"] == 6

    def test_record_error(self):
        record_error("timeout")
        record_error("timeout")
        record_error("validation")
        snap = get_metrics_snapshot()
        assert snap["errors"] == 3
        assert snap["errors_by_type"] == {"timeout": 2, "validation": 1}

    def test_record_agent_uptime(self):
        record_agent_uptime("agent-1")
        snap = get_metrics_snapshot()
        assert "agent-1" in snap["agent_uptime"]
        assert snap["agent_uptime"]["agent-1"] >= 0

    def test_get_metrics_snapshot_returns_dict(self):
        snap = get_metrics_snapshot()
        assert isinstance(snap, dict)
        assert "tasks_completed" in snap
        assert "errors" in snap
        assert "errors_by_type" in snap
        assert "agent_uptime" in snap

    def test_reset_clears_all(self):
        record_task_completed(10)
        record_error("x")
        record_agent_uptime("a")
        reset()
        snap = get_metrics_snapshot()
        assert snap["tasks_completed"] == 0
        assert snap["errors"] == 0
        assert snap["errors_by_type"] == {}
        assert snap["agent_uptime"] == {}
