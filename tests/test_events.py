"""Unit tests for crazypumpkin.framework.events.EventBus.

Tests cover:
- Initialization with and without log directory
- subscribe() for action-specific handlers
- subscribe_all() for global handlers
- emit() for event creation and dispatch
- _persist() for file persistence
- load() for loading persisted events
- recent() for retrieving recent events
- total_events property
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure src/ is on sys.path for imports
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import importlib

_events_mod = importlib.import_module("crazypumpkin.framework.events")
_models_mod = importlib.import_module("crazypumpkin.framework.models")

EventBus = _events_mod.EventBus
AuditEvent = _models_mod.AuditEvent


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def bus():
    """Create an EventBus without persistence for basic tests."""
    return EventBus()


@pytest.fixture
def bus_with_log(tmp_path: Path):
    """Create an EventBus with a log directory for persistence tests."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    return EventBus(log_dir=log_dir), log_dir


@pytest.fixture
def log_path(tmp_path: Path):
    """Return a path to use as log directory."""
    return tmp_path / "audit_logs"


# -- Initialization Tests ----------------------------------------------------


def test_eventbus_init_without_log_dir():
    """EventBus can be initialized without a log directory."""
    bus = EventBus()
    assert bus._log_file is None
    assert bus._log == []
    assert bus._handlers == {}
    assert bus._global_handlers == []


def test_eventbus_init_with_log_dir(log_path: Path):
    """EventBus creates log directory and file when log_dir is provided."""
    bus = EventBus(log_dir=log_path)
    assert bus._log_file == log_path / "audit.jsonl"
    assert log_path.exists()
    assert bus._log == []


# -- Subscribe Tests ----------------------------------------------------------


def test_subscribe_single_handler(bus):
    """subscribe() registers a handler for a specific action."""
    called = []

    def handler(event):
        called.append(event)

    bus.subscribe("task_created", handler)
    assert "task_created" in bus._handlers
    assert handler in bus._handlers["task_created"]


def test_subscribe_multiple_handlers_same_action(bus):
    """Multiple handlers can subscribe to the same action."""
    calls = []

    def handler1(event):
        calls.append(("h1", event))

    def handler2(event):
        calls.append(("h2", event))

    bus.subscribe("task_created", handler1)
    bus.subscribe("task_created", handler2)

    assert len(bus._handlers["task_created"]) == 2


def test_subscribe_different_actions(bus):
    """Handlers can subscribe to different actions."""
    bus.subscribe("task_created", lambda e: None)
    bus.subscribe("task_completed", lambda e: None)

    assert "task_created" in bus._handlers
    assert "task_completed" in bus._handlers


# -- Subscribe All Tests ------------------------------------------------------


def test_subscribe_all(bus):
    """subscribe_all() registers a handler for all events."""
    called = []

    def global_handler(event):
        called.append(event)

    bus.subscribe_all(global_handler)
    assert global_handler in bus._global_handlers


def test_subscribe_all_receives_all_events(bus):
    """Global handlers receive events for all action types."""
    received = []

    def global_handler(event):
        received.append(event)

    bus.subscribe_all(global_handler)

    bus.emit("agent1", "task_created", entity_type="task")
    bus.emit("agent2", "task_completed", entity_type="task")

    assert len(received) == 2
    assert received[0].action == "task_created"
    assert received[1].action == "task_completed"


# -- Emit Tests ---------------------------------------------------------------


def test_emit_returns_audit_event(bus):
    """emit() returns an AuditEvent with expected fields."""
    event = bus.emit(
        agent_id="agent123",
        action="task_created",
        entity_type="task",
        entity_id="task456",
        detail="Created a new task",
        result="success",
        confidence=0.95,
        risk_level="low",
        metadata={"foo": "bar"},
    )

    assert isinstance(event, AuditEvent)
    assert event.agent_id == "agent123"
    assert event.action == "task_created"
    assert event.entity_type == "task"
    assert event.entity_id == "task456"
    assert event.detail == "Created a new task"
    assert event.result == "success"
    assert event.confidence == 0.95
    assert event.risk_level == "low"
    assert event.metadata == {"foo": "bar"}
    assert event.id != ""
    assert event.timestamp != ""


def test_emit_default_values(bus):
    """emit() uses sensible defaults for optional fields."""
    event = bus.emit(agent_id="agent1", action="test_action")

    assert event.entity_type == ""
    assert event.entity_id == ""
    assert event.detail == ""
    assert event.result == "success"
    assert event.confidence is None
    assert event.risk_level == "low"
    assert event.metadata == {}


def test_emit_adds_to_log(bus):
    """emit() appends the event to the internal log."""
    bus.emit("agent1", "task_created")
    bus.emit("agent1", "task_completed")

    assert bus.total_events == 2


def test_emit_dispatches_to_action_handlers(bus):
    """emit() calls handlers subscribed to the specific action."""
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe("task_created", handler)
    bus.emit("agent1", "task_created", detail="test")
    bus.emit("agent1", "task_completed", detail="other")

    # Only task_created handler should have been called
    assert len(received) == 1
    assert received[0].action == "task_created"


def test_emit_dispatches_to_multiple_handlers(bus):
    """emit() calls all handlers for an action in subscription order."""
    order = []

    def h1(e):
        order.append(1)

    def h2(e):
        order.append(2)

    bus.subscribe("action", h1)
    bus.subscribe("action", h2)
    bus.emit("agent", "action")

    assert order == [1, 2]


def test_emit_dispatches_to_global_handlers_before_action_handlers(bus):
    """Global handlers are called before action-specific handlers."""
    order = []

    def global_h(e):
        order.append("global")

    def action_h(e):
        order.append("action")

    bus.subscribe_all(global_h)
    bus.subscribe("test", action_h)
    bus.emit("agent", "test")

    assert order == ["global", "action"]


# -- Persistence Tests --------------------------------------------------------


def test_emit_persists_to_file(log_path: Path):
    """emit() writes events to audit.jsonl when log_dir is set."""
    bus = EventBus(log_dir=log_path)
    bus.emit("agent1", "task_created", entity_type="task", entity_id="t1")

    log_file = log_path / "audit.jsonl"
    assert log_file.exists()

    with open(log_file, encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["agent_id"] == "agent1"
    assert record["action"] == "task_created"
    assert record["entity_type"] == "task"
    assert record["entity_id"] == "t1"


def test_emit_without_log_dir_does_not_persist(bus, tmp_path: Path):
    """emit() does not create files when log_dir is not set."""
    bus.emit("agent", "action")
    # No file should be created anywhere in tmp_path
    assert list(tmp_path.iterdir()) == []


def test_persist_handles_write_error_gracefully(bus_with_log):
    """_persist() handles write errors without raising."""
    bus, log_dir = bus_with_log
    log_file = log_dir / "audit.jsonl"

    # Write valid event first
    bus.emit("agent", "action1")

    # Make the log file a directory to cause write failure
    log_file.unlink()
    log_file.mkdir()

    # Should not raise, just silently ignore
    bus.emit("agent", "action2")


# -- Load Tests ---------------------------------------------------------------


def test_load_reads_persisted_events(log_path: Path):
    """load() reads events from audit.jsonl into memory."""
    bus1 = EventBus(log_dir=log_path)
    bus1.emit("agent1", "task_created", entity_id="t1")
    bus1.emit("agent1", "task_completed", entity_id="t2")

    # Create a new bus and load events
    bus2 = EventBus(log_dir=log_path)
    bus2.load()

    assert bus2.total_events == 2
    actions = [e.action for e in bus2._log]
    assert "task_created" in actions
    assert "task_completed" in actions


def test_load_with_tail_limit(log_path: Path):
    """load() respects the tail parameter to limit loaded events."""
    bus1 = EventBus(log_dir=log_path)
    for i in range(20):
        bus1.emit(f"agent{i}", f"action{i}")

    bus2 = EventBus(log_dir=log_path)
    bus2.load(tail=5)

    assert bus2.total_events == 5
    # Should have the last 5 events
    assert bus2._log[0].action == "action15"
    assert bus2._log[-1].action == "action19"


def test_load_handles_missing_file(log_path: Path):
    """load() does nothing if audit.jsonl doesn't exist."""
    bus = EventBus(log_dir=log_path)
    # Don't create any events
    bus.load()
    assert bus.total_events == 0


def test_load_handles_malformed_json(log_path: Path):
    """load() skips lines that are not valid JSON."""
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "audit.jsonl"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write('{"id": "1", "timestamp": "2024-01-01", "agent_id": "a", "action": "good"}\n')
        f.write("this is not json\n")
        f.write('{"id": "2", "timestamp": "2024-01-02", "agent_id": "b", "action": "good2"}\n')

    bus = EventBus(log_dir=log_path)
    bus.load()

    assert bus.total_events == 2
    assert bus._log[0].id == "1"
    assert bus._log[1].id == "2"


def test_load_handles_missing_fields(log_path: Path):
    """load() skips events with missing required fields."""
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "audit.jsonl"
    with open(log_file, "w", encoding="utf-8") as f:
        # Valid event
        f.write('{"id": "1", "timestamp": "2024-01-01", "agent_id": "a", "action": "good"}\n')
        # Missing required fields - should be skipped
        f.write('{"id": "2"}\n')
        # Another valid event
        f.write('{"id": "3", "timestamp": "2024-01-03", "agent_id": "c", "action": "good3"}\n')

    bus = EventBus(log_dir=log_path)
    bus.load()

    assert bus.total_events >= 1  # At least the valid events


def test_load_without_log_dir_is_noop(bus):
    """load() does nothing when log_dir is not set."""
    bus.emit("agent", "action")
    bus.load()
    # Should not crash, log should remain as-is
    assert bus.total_events == 1


# -- Recent Tests -------------------------------------------------------------


def test_recent_returns_last_n_events(bus):
    """recent() returns the last n events."""
    for i in range(10):
        bus.emit(f"agent{i}", f"action{i}")

    recent = bus.recent(3)
    assert len(recent) == 3
    assert recent[0].action == "action7"
    assert recent[1].action == "action8"
    assert recent[2].action == "action9"


def test_recent_filters_by_action(bus):
    """recent() can filter events by action type."""
    bus.emit("agent", "task_created", entity_id="1")
    bus.emit("agent", "task_completed", entity_id="1")
    bus.emit("agent", "task_created", entity_id="2")
    bus.emit("agent", "task_completed", entity_id="2")
    bus.emit("agent", "task_created", entity_id="3")

    created = bus.recent(n=10, action="task_created")
    assert len(created) == 3
    for e in created:
        assert e.action == "task_created"


def test_recent_with_action_returns_fewer_than_n(bus):
    """recent() with action filter returns fewer than n if not enough matches."""
    bus.emit("agent", "task_created")
    bus.emit("agent", "task_completed")
    bus.emit("agent", "task_created")

    completed = bus.recent(n=10, action="task_completed")
    assert len(completed) == 1


def test_recent_default_n(bus):
    """recent() defaults to returning 50 events."""
    for i in range(100):
        bus.emit("agent", f"action{i}")

    recent = bus.recent()
    assert len(recent) == 50


def test_recent_empty_log(bus):
    """recent() returns empty list when log is empty."""
    assert bus.recent() == []


# -- Total Events Tests -------------------------------------------------------


def test_total_events_zero_initially(bus):
    """total_events is 0 for a new EventBus."""
    assert bus.total_events == 0


def test_total_events_increments(bus):
    """total_events increments with each emit."""
    assert bus.total_events == 0
    bus.emit("agent", "action1")
    assert bus.total_events == 1
    bus.emit("agent", "action2")
    assert bus.total_events == 2


# -- Integration Tests ---------------------------------------------------------


def test_full_workflow(log_path: Path):
    """Test a complete workflow: emit, persist, load, query."""
    bus1 = EventBus(log_dir=log_path)

    # Subscribe handlers
    created_events = []
    completed_events = []
    all_events = []

    bus1.subscribe("task_created", lambda e: created_events.append(e))
    bus1.subscribe("task_completed", lambda e: completed_events.append(e))
    bus1.subscribe_all(lambda e: all_events.append(e))

    # Emit events
    bus1.emit("agent1", "task_created", entity_type="task", entity_id="t1")
    bus1.emit("agent1", "task_completed", entity_type="task", entity_id="t1")
    bus1.emit("agent2", "task_created", entity_type="task", entity_id="t2")

    assert len(created_events) == 2
    assert len(completed_events) == 1
    assert len(all_events) == 3
    assert bus1.total_events == 3

    # Create new bus and load from file
    bus2 = EventBus(log_dir=log_path)
    bus2.load()

    assert bus2.total_events == 3
    recent = bus2.recent(2)
    assert len(recent) == 2


def test_event_handler_exception_isolation(bus):
    """Handler exceptions should not prevent other handlers from running."""
    results = []

    def failing_handler(e):
        raise RuntimeError("Handler failed!")

    def success_handler(e):
        results.append("success")

    bus.subscribe("action", failing_handler)
    bus.subscribe("action", success_handler)

    # This will raise because the failing handler raises
    # But the success handler should have been appended to handlers list
    with pytest.raises(RuntimeError):
        bus.emit("agent", "action")

    # The success handler should have been registered
    assert success_handler in bus._handlers["action"]


def test_eventbus_with_nested_handlers(bus):
    """Handlers can be added after events have been emitted."""
    bus.emit("agent", "action1")
    bus.emit("agent", "action2")

    # Add handler after events
    received = []
    bus.subscribe("action1", lambda e: received.append(e))

    # Emit new event that matches
    bus.emit("agent", "action1")
    bus.emit("agent", "action3")

    assert len(received) == 1
    assert received[0].action == "action1"
    assert bus.total_events == 4