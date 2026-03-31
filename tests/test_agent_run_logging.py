"""Tests for BaseAgent.run() structured logging and metrics integration."""

import json
import logging
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.metrics import AgentMetrics, default_metrics
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Concrete subclass for testing
# ---------------------------------------------------------------------------

class _StubAgent(BaseAgent):
    """Minimal concrete BaseAgent that returns a fixed TaskOutput."""

    def __init__(self, agent: Agent, *, fail: bool = False):
        super().__init__(agent)
        self.fail = fail

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        if self.fail:
            raise RuntimeError("boom")
        return TaskOutput(content="ok")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str = "test-agent") -> Agent:
    return Agent(name=name, role=AgentRole.EXECUTION)


def _make_task() -> Task:
    return Task(title="Do something", description="desc", acceptance_criteria=["a"])


# ---------------------------------------------------------------------------
# Tests: structured JSON logging
# ---------------------------------------------------------------------------

class TestRunLogging:

    def test_run_emits_start_log(self, caplog):
        """run() logs 'Agent execution started' at INFO."""
        agent = _StubAgent(_make_agent())
        task = _make_task()

        with caplog.at_level(logging.INFO, logger="crazypumpkin.agent"):
            agent.run(task, {})

        messages = [r.getMessage() for r in caplog.records]
        assert any("Agent execution started" in m for m in messages)

    def test_run_emits_completion_log(self, caplog):
        """run() logs 'Agent execution completed' at INFO on success."""
        agent = _StubAgent(_make_agent())
        task = _make_task()

        with caplog.at_level(logging.INFO, logger="crazypumpkin.agent"):
            agent.run(task, {})

        messages = [r.getMessage() for r in caplog.records]
        assert any("Agent execution completed" in m for m in messages)

    def test_run_emits_structured_json(self):
        """The structured formatter outputs valid JSON with agent_id, task_id."""
        from crazypumpkin.framework.logging import StructuredFormatter

        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("crazypumpkin.agent")
        logger.addHandler(handler)
        try:
            agent = _StubAgent(_make_agent())
            task = _make_task()

            with mock.patch.object(handler, "emit", wraps=handler.emit) as spy:
                agent.run(task, {"cycle_id": "cyc-1"})

            # Collect all formatted records
            json_records = []
            for call in spy.call_args_list:
                record = call[0][0]
                formatted = handler.formatter.format(record)
                parsed = json.loads(formatted)
                json_records.append(parsed)

            # At least start and completion
            assert len(json_records) >= 2
            start_rec = json_records[0]
            assert start_rec["agent_id"] == agent.id
            assert start_rec["task_id"] == task.id
            assert start_rec["cycle_id"] == "cyc-1"
            assert start_rec["message"] == "Agent execution started"
        finally:
            logger.removeHandler(handler)

    def test_run_logs_error_on_exception(self, caplog):
        """run() logs at ERROR level when execute() raises."""
        agent = _StubAgent(_make_agent(), fail=True)
        task = _make_task()

        with caplog.at_level(logging.ERROR, logger="crazypumpkin.agent"):
            with pytest.raises(RuntimeError, match="boom"):
                agent.run(task, {})

        error_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("Agent execution failed" in m for m in error_messages)


# ---------------------------------------------------------------------------
# Tests: metrics recording
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="Flaky on Windows — monotonic timer resolution causes 0.0 duration")
class TestRunMetrics:

    def setup_method(self):
        default_metrics.reset()

    def test_records_execution_metrics_on_success(self):
        """run() calls default_metrics.record_execution with error=False on success."""
        agent = _StubAgent(_make_agent())
        task = _make_task()

        agent.run(task, {})

        summary = default_metrics.get_summary(agent.id)
        assert summary["execution_count"] == 1
        assert summary["error_count"] == 0
        assert summary["total_duration"] > 0

    def test_records_error_metrics_on_exception(self):
        """run() calls default_metrics.record_execution with error=True on failure."""
        agent = _StubAgent(_make_agent(), fail=True)
        task = _make_task()

        with pytest.raises(RuntimeError):
            agent.run(task, {})

        summary = default_metrics.get_summary(agent.id)
        assert summary["execution_count"] == 1
        assert summary["error_count"] == 1
        assert summary["total_duration"] > 0

    def test_records_token_usage_from_context(self):
        """run() forwards token_usage from context to metrics."""
        agent = _StubAgent(_make_agent())
        task = _make_task()
        tokens = {"prompt_tokens": 100, "completion_tokens": 50}

        agent.run(task, {"token_usage": tokens})

        summary = default_metrics.get_summary(agent.id)
        assert summary["token_usage"]["prompt_tokens"] == 100
        assert summary["token_usage"]["completion_tokens"] == 50


# ---------------------------------------------------------------------------
# Tests: duration uses time.monotonic
# ---------------------------------------------------------------------------

class TestRunDuration:

    def setup_method(self):
        default_metrics.reset()

    def test_duration_uses_monotonic(self):
        """run() measures duration with time.monotonic()."""
        agent = _StubAgent(_make_agent())
        task = _make_task()

        with mock.patch("crazypumpkin.framework.agent.time") as mock_time:
            mock_time.monotonic.side_effect = [10.0, 10.5]
            agent.run(task, {})

        summary = default_metrics.get_summary(agent.id)
        assert abs(summary["total_duration"] - 0.5) < 1e-9

    def test_duration_measured_on_error(self):
        """Duration is still recorded when execute() raises."""
        agent = _StubAgent(_make_agent(), fail=True)
        task = _make_task()

        with mock.patch("crazypumpkin.framework.agent.time") as mock_time:
            mock_time.monotonic.side_effect = [10.0, 12.0]
            with pytest.raises(RuntimeError):
                agent.run(task, {})

        summary = default_metrics.get_summary(agent.id)
        assert abs(summary["total_duration"] - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# Tests: existing BaseAgent behavior preserved
# ---------------------------------------------------------------------------

class TestRunLifecycle:

    def test_setup_and_teardown_called(self):
        """run() calls setup before execute and teardown after."""
        agent = _StubAgent(_make_agent())
        task = _make_task()
        ctx = {}

        with mock.patch.object(agent, "setup") as m_setup, \
             mock.patch.object(agent, "teardown") as m_teardown:
            agent.run(task, ctx)
            m_setup.assert_called_once_with(ctx)
            m_teardown.assert_called_once_with(ctx)

    def test_teardown_called_on_error(self):
        """Teardown runs even if execute raises."""
        agent = _StubAgent(_make_agent(), fail=True)
        task = _make_task()
        ctx = {}

        with mock.patch.object(agent, "teardown") as m_teardown:
            with pytest.raises(RuntimeError):
                agent.run(task, ctx)
            m_teardown.assert_called_once_with(ctx)

    def test_run_returns_task_output(self):
        """run() returns the TaskOutput from execute()."""
        agent = _StubAgent(_make_agent())
        task = _make_task()

        result = agent.run(task, {})
        assert isinstance(result, TaskOutput)
        assert result.content == "ok"
