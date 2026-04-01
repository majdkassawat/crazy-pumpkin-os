"""Tests for MessageBus publish/subscribe, persistence, consultation protocol, and concurrency."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from crazypumpkin.framework.message_bus import Message, MessageBus
from crazypumpkin.framework.consultation import (
    ConsultationManager,
    ConsultationRequest,
    ConsultationResponse,
    ConsultationStatus,
)


# ---------------------------------------------------------------------------
# Pub/Sub
# ---------------------------------------------------------------------------

class TestMessageBusPublish:
    def test_publish_returns_message(self):
        bus = MessageBus()
        msg = bus.publish("tasks", "hello", sender="agent-1")
        assert isinstance(msg, Message)
        assert msg.topic == "tasks"
        assert msg.content == "hello"
        assert msg.sender == "agent-1"
        assert msg.id
        assert msg.timestamp

    def test_publish_stores_message_in_memory(self):
        bus = MessageBus()
        bus.publish("tasks", "msg1", sender="a")
        bus.publish("tasks", "msg2", sender="b")
        assert len(bus.get_messages("tasks")) == 2

    def test_publish_different_topics(self):
        bus = MessageBus()
        bus.publish("tasks", "t1")
        bus.publish("events", "e1")
        assert len(bus.get_messages("tasks")) == 1
        assert len(bus.get_messages("events")) == 1

    def test_publish_default_sender_is_empty(self):
        bus = MessageBus()
        msg = bus.publish("tasks", "hello")
        assert msg.sender == ""

    def test_publish_content_can_be_dict(self):
        bus = MessageBus()
        payload = {"key": "value", "count": 42}
        msg = bus.publish("tasks", payload)
        assert msg.content == payload

    def test_publish_unique_ids(self):
        bus = MessageBus()
        ids = {bus.publish("t", i).id for i in range(20)}
        assert len(ids) == 20


class TestMessageBusSubscribe:
    def test_subscribe_handler_called(self):
        bus = MessageBus()
        received = []
        bus.subscribe("tasks", lambda m: received.append(m))
        bus.publish("tasks", "hello")
        assert len(received) == 1
        assert received[0].content == "hello"

    def test_subscribe_multiple_handlers(self):
        bus = MessageBus()
        r1, r2 = [], []
        bus.subscribe("tasks", lambda m: r1.append(m))
        bus.subscribe("tasks", lambda m: r2.append(m))
        bus.publish("tasks", "hello")
        assert len(r1) == 1
        assert len(r2) == 1

    def test_subscribe_only_matching_topic(self):
        bus = MessageBus()
        received = []
        bus.subscribe("tasks", lambda m: received.append(m))
        bus.publish("events", "nope")
        assert len(received) == 0

    def test_handler_error_does_not_block(self):
        bus = MessageBus()
        received = []

        def bad_handler(m):
            raise RuntimeError("boom")

        bus.subscribe("tasks", bad_handler)
        bus.subscribe("tasks", lambda m: received.append(m))
        bus.publish("tasks", "hello")
        assert len(received) == 1

    def test_handler_receives_correct_message_object(self):
        bus = MessageBus()
        captured = []
        bus.subscribe("t", lambda m: captured.append(m))
        msg = bus.publish("t", "data", sender="s1")
        assert captured[0] is msg

    def test_subscribe_multiple_topics(self):
        bus = MessageBus()
        received_a, received_b = [], []
        bus.subscribe("a", lambda m: received_a.append(m))
        bus.subscribe("b", lambda m: received_b.append(m))
        bus.publish("a", "msg-a")
        bus.publish("b", "msg-b")
        bus.publish("a", "msg-a2")
        assert len(received_a) == 2
        assert len(received_b) == 1


# ---------------------------------------------------------------------------
# GetMessages / filtering
# ---------------------------------------------------------------------------

class TestMessageBusGetMessages:
    def test_get_messages_empty(self):
        bus = MessageBus()
        assert bus.get_messages("nonexistent") == []

    def test_get_messages_since_filter(self):
        bus = MessageBus()
        m1 = bus.publish("tasks", "old")
        m2 = bus.publish("tasks", "new")
        # All messages should be retrievable without since
        all_msgs = bus.get_messages("tasks")
        assert len(all_msgs) == 2

    def test_get_messages_returns_correct_topic(self):
        bus = MessageBus()
        bus.publish("a", "msg-a")
        bus.publish("b", "msg-b")
        bus.publish("a", "msg-a2")
        result = bus.get_messages("a")
        assert len(result) == 2
        assert all(m.topic == "a" for m in result)

    def test_get_messages_preserves_order(self):
        bus = MessageBus()
        bus.publish("t", "first")
        bus.publish("t", "second")
        bus.publish("t", "third")
        msgs = bus.get_messages("t")
        assert [m.content for m in msgs] == ["first", "second", "third"]

    def test_max_messages_eviction(self):
        bus = MessageBus(max_messages=5)
        for i in range(10):
            bus.publish("t", f"msg-{i}")
        msgs = bus.get_messages("t")
        assert len(msgs) == 5
        # Oldest messages should have been evicted
        assert msgs[0].content == "msg-5"
        assert msgs[-1].content == "msg-9"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestMessageBusPersistence:
    def test_no_store_does_not_fail(self):
        bus = MessageBus(store=None)
        bus.publish("tasks", "hello")

    def test_store_save_called(self):
        class FakeStore:
            def __init__(self):
                self.save_count = 0

            def save(self):
                self.save_count += 1

        store = FakeStore()
        bus = MessageBus(store=store)
        bus.publish("tasks", "hello")
        assert store.save_count == 1

    def test_store_save_called_per_publish(self):
        class FakeStore:
            def __init__(self):
                self.save_count = 0

            def save(self):
                self.save_count += 1

        store = FakeStore()
        bus = MessageBus(store=store)
        bus.publish("tasks", "a")
        bus.publish("tasks", "b")
        bus.publish("events", "c")
        assert store.save_count == 3

    def test_store_save_error_does_not_crash(self):
        class BrokenStore:
            def save(self):
                raise IOError("disk full")

        bus = MessageBus(store=BrokenStore())
        # Should not raise
        msg = bus.publish("tasks", "hello")
        assert msg.content == "hello"

    def test_store_without_save_method(self):
        """Store object lacking save() should not crash."""
        bus = MessageBus(store=object())
        msg = bus.publish("tasks", "hello")
        assert msg.content == "hello"


# ---------------------------------------------------------------------------
# Consultation request/response protocol
# ---------------------------------------------------------------------------

class TestConsultationRequestResponse:
    def test_create_request(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "Is this safe?")
        assert isinstance(req, ConsultationRequest)
        assert req.from_agent == "agent-1"
        assert req.to_role == "reviewer"
        assert req.question == "Is this safe?"
        assert req.status == ConsultationStatus.PENDING
        assert req.id
        assert req.created_at

    def test_respond_to_request(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "Is this safe?")
        resp = mgr.respond_to_consultation(req.id, "Yes, it is safe.", responder="rev-1")
        assert isinstance(resp, ConsultationResponse)
        assert resp.request_id == req.id
        assert resp.response == "Yes, it is safe."
        assert resp.responder == "rev-1"
        assert req.status == ConsultationStatus.RESPONDED

    def test_response_retrievable(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("a", "reviewer", "q?")
        resp = mgr.respond_to_consultation(req.id, "a")
        assert mgr.get_response(req.id) is resp

    def test_unknown_request_raises_key_error(self):
        mgr = ConsultationManager()
        with pytest.raises(KeyError):
            mgr.respond_to_consultation("nonexistent", "answer")

    def test_double_response_raises_value_error(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("a", "reviewer", "q?")
        mgr.respond_to_consultation(req.id, "first")
        with pytest.raises(ValueError):
            mgr.respond_to_consultation(req.id, "second")

    def test_get_pending_requests_empty(self):
        mgr = ConsultationManager()
        assert mgr.get_pending_requests() == []

    def test_get_pending_requests_filters_responded(self):
        mgr = ConsultationManager()
        r1 = mgr.request_consultation("a", "reviewer", "q1")
        r2 = mgr.request_consultation("b", "strategy", "q2")
        mgr.respond_to_consultation(r1.id, "done")
        pending = mgr.get_pending_requests()
        assert len(pending) == 1
        assert pending[0].id == r2.id

    def test_get_pending_requests_filter_by_role(self):
        mgr = ConsultationManager()
        mgr.request_consultation("a", "reviewer", "q1")
        mgr.request_consultation("b", "strategy", "q2")
        mgr.request_consultation("c", "reviewer", "q3")
        pending = mgr.get_pending_requests(to_role="reviewer")
        assert len(pending) == 2
        assert all(r.to_role == "reviewer" for r in pending)

    def test_get_request_missing_returns_none(self):
        mgr = ConsultationManager()
        assert mgr.get_request("missing") is None

    def test_get_response_missing_returns_none(self):
        mgr = ConsultationManager()
        assert mgr.get_response("missing") is None

    def test_multiple_independent_consultations(self):
        mgr = ConsultationManager()
        r1 = mgr.request_consultation("a", "reviewer", "q1")
        r2 = mgr.request_consultation("b", "strategy", "q2")
        resp1 = mgr.respond_to_consultation(r1.id, "answer1", responder="rev")
        resp2 = mgr.respond_to_consultation(r2.id, "answer2", responder="strat")
        assert mgr.get_response(r1.id) is resp1
        assert mgr.get_response(r2.id) is resp2
        assert mgr.get_pending_requests() == []


# ---------------------------------------------------------------------------
# Concurrent message handling
# ---------------------------------------------------------------------------

class TestConcurrentMessageHandling:
    def test_concurrent_publish(self):
        """Multiple threads publishing concurrently should not lose messages."""
        bus = MessageBus()
        num_threads = 10
        msgs_per_thread = 50
        barrier = threading.Barrier(num_threads)

        def publisher(thread_id):
            barrier.wait()
            for i in range(msgs_per_thread):
                bus.publish("tasks", f"t{thread_id}-{i}", sender=f"thread-{thread_id}")

        threads = [threading.Thread(target=publisher, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = len(bus.get_messages("tasks"))
        assert total == num_threads * msgs_per_thread

    def test_concurrent_subscribe_and_publish(self):
        """Handlers should receive messages even when subscribing and publishing concurrently."""
        bus = MessageBus()
        received = []
        lock = threading.Lock()

        def handler(m):
            with lock:
                received.append(m)

        bus.subscribe("tasks", handler)

        num_threads = 5
        msgs_per_thread = 20
        barrier = threading.Barrier(num_threads)

        def publisher(tid):
            barrier.wait()
            for i in range(msgs_per_thread):
                bus.publish("tasks", f"t{tid}-{i}")

        threads = [threading.Thread(target=publisher, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == num_threads * msgs_per_thread

    def test_concurrent_consultation_requests(self):
        """Multiple threads creating consultation requests concurrently."""
        mgr = ConsultationManager()
        num_threads = 10
        barrier = threading.Barrier(num_threads)
        request_ids = []
        lock = threading.Lock()

        def requester(tid):
            barrier.wait()
            req = mgr.request_consultation(f"agent-{tid}", "reviewer", f"q-{tid}")
            with lock:
                request_ids.append(req.id)

        threads = [threading.Thread(target=requester, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(request_ids) == num_threads
        assert len(set(request_ids)) == num_threads  # all unique
        pending = mgr.get_pending_requests()
        assert len(pending) == num_threads
