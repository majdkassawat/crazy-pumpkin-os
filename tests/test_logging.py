"""Unit tests for crazypumpkin.framework.logging."""

import json
import logging
import sys
from pathlib import Path

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.logging import (
    AgentLogContext,
    StructuredFormatter,
    configure_agent_logging,
)


def test_structured_formatter_outputs_valid_json():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello world",
        args=None,
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "timestamp" in parsed
    assert "level" in parsed
    assert "message" in parsed
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "hello world"


def test_agent_log_context_bind():
    ctx = AgentLogContext(agent_id="a1", task_id="t1", cycle_id="c1")
    logger = logging.getLogger("test_agent_log_context_bind")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    adapter = ctx.bind(logger)

    # Capture output via a custom handler
    class CaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    capture = CaptureHandler()
    capture.setFormatter(StructuredFormatter())
    logger.addHandler(capture)

    adapter.info("test message")

    assert len(capture.records) >= 1
    parsed = json.loads(capture.records[0])
    assert parsed["agent_id"] == "a1"
    assert parsed["task_id"] == "t1"
    assert parsed["cycle_id"] == "c1"


def test_configure_agent_logging_returns_logger():
    # Clean root logger state for isolation
    root = logging.getLogger()
    original_handlers = root.handlers[:]

    try:
        configure_agent_logging()
        assert isinstance(root, logging.Logger) or isinstance(
            root, logging.RootLogger
        )

        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1

        has_structured = any(
            isinstance(h.formatter, StructuredFormatter) for h in stream_handlers
        )
        assert has_structured
    finally:
        # Restore original handlers
        root.handlers = original_handlers
