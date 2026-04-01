"""Tests for agent consultation request/response protocol."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from crazypumpkin.framework.consultation import (
    ConsultationManager,
    ConsultationRequest,
    ConsultationResponse,
    ConsultationStatus,
)


class TestRequestConsultation:
    def test_returns_consultation_request(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "Is this code safe?")
        assert isinstance(req, ConsultationRequest)
        assert req.from_agent == "agent-1"
        assert req.to_role == "reviewer"
        assert req.question == "Is this code safe?"
        assert req.status == ConsultationStatus.PENDING
        assert req.id
        assert req.created_at

    def test_request_stored(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "question?")
        assert mgr.get_request(req.id) is req

    def test_multiple_requests(self):
        mgr = ConsultationManager()
        r1 = mgr.request_consultation("a", "reviewer", "q1")
        r2 = mgr.request_consultation("b", "strategy", "q2")
        assert r1.id != r2.id
        assert mgr.get_request(r1.id) is r1
        assert mgr.get_request(r2.id) is r2


class TestRespondToConsultation:
    def test_returns_consultation_response(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "Is this safe?")
        resp = mgr.respond_to_consultation(req.id, "Yes, it looks safe.", responder="reviewer-1")
        assert isinstance(resp, ConsultationResponse)
        assert resp.request_id == req.id
        assert resp.response == "Yes, it looks safe."
        assert resp.responder == "reviewer-1"
        assert resp.id
        assert resp.created_at

    def test_marks_request_as_responded(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "question?")
        mgr.respond_to_consultation(req.id, "answer")
        assert req.status == ConsultationStatus.RESPONDED

    def test_response_retrievable(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "q?")
        resp = mgr.respond_to_consultation(req.id, "a")
        assert mgr.get_response(req.id) is resp

    def test_unknown_request_raises_key_error(self):
        mgr = ConsultationManager()
        with pytest.raises(KeyError):
            mgr.respond_to_consultation("nonexistent", "answer")

    def test_double_response_raises_value_error(self):
        mgr = ConsultationManager()
        req = mgr.request_consultation("agent-1", "reviewer", "q?")
        mgr.respond_to_consultation(req.id, "first answer")
        with pytest.raises(ValueError):
            mgr.respond_to_consultation(req.id, "second answer")


class TestGetPendingRequests:
    def test_empty(self):
        mgr = ConsultationManager()
        assert mgr.get_pending_requests() == []

    def test_returns_only_pending(self):
        mgr = ConsultationManager()
        r1 = mgr.request_consultation("a", "reviewer", "q1")
        r2 = mgr.request_consultation("b", "strategy", "q2")
        mgr.respond_to_consultation(r1.id, "done")
        pending = mgr.get_pending_requests()
        assert len(pending) == 1
        assert pending[0].id == r2.id

    def test_filter_by_role(self):
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
