"""Tests for the console notifier."""

from crazypumpkin.notifications import notify


def test_notify_task_start(capsys):
    notify({"action": "task_start", "timestamp": "2026-01-01T00:00:00Z", "agent_id": "a1", "entity_id": "t1", "detail": "begin"})
    out = capsys.readouterr().out
    assert "[NOTIFY]" in out
    assert "task_start" in out
    assert "2026-01-01T00:00:00Z" in out
    assert "t1" in out
    assert "begin" in out


def test_notify_task_complete(capsys):
    notify({"action": "task_complete", "timestamp": "2026-01-01T00:00:01Z", "entity_id": "t2"})
    out = capsys.readouterr().out
    assert "task_complete" in out
    assert "t2" in out


def test_notify_task_fail(capsys):
    notify({"action": "task_fail", "timestamp": "2026-01-01T00:00:02Z", "agent_id": "a1"})
    out = capsys.readouterr().out
    assert "task_fail" in out
    assert "a1" in out


def test_notify_ignores_non_lifecycle(capsys):
    notify({"action": "some_other_action", "timestamp": "2026-01-01T00:00:00Z"})
    assert capsys.readouterr().out == ""


def test_notify_agent_lifecycle(capsys):
    for action in ("agent_start", "agent_complete", "agent_fail"):
        notify({"action": action, "timestamp": "2026-01-01T00:00:00Z", "agent_id": "ag1"})
        out = capsys.readouterr().out
        assert action in out


def test_notify_default_timestamp(capsys):
    """When no timestamp provided, notify still produces output."""
    notify({"action": "task_start", "entity_id": "t1"})
    out = capsys.readouterr().out
    assert "[NOTIFY]" in out
    assert "task_start" in out


def test_event_bus_emits_notification(capsys):
    """EventBus.emit for lifecycle actions triggers console notification."""
    from crazypumpkin.framework.events import EventBus

    bus = EventBus()
    bus.emit(agent_id="a1", action="task_start", entity_id="t1", detail="go")
    out = capsys.readouterr().out
    assert "task_start" in out
    assert "t1" in out
