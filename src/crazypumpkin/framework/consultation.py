"""
Consultation protocol — request/response pattern for inter-agent consultation.

Allows agents to request expertise from other agents by role, and receive
structured responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from crazypumpkin.framework.models import _now, _uid

logger = logging.getLogger("crazypumpkin.consultation")


class ConsultationStatus(str, Enum):
    PENDING = "pending"
    RESPONDED = "responded"


@dataclass
class ConsultationRequest:
    """A request from one agent to consult another by role."""
    id: str = field(default_factory=_uid)
    from_agent: str = ""
    to_role: str = ""
    question: str = ""
    status: ConsultationStatus = ConsultationStatus.PENDING
    created_at: str = field(default_factory=_now)


@dataclass
class ConsultationResponse:
    """A response to a consultation request."""
    id: str = field(default_factory=_uid)
    request_id: str = ""
    responder: str = ""
    response: str = ""
    created_at: str = field(default_factory=_now)


class ConsultationManager:
    """Manages consultation requests and responses between agents."""

    def __init__(self) -> None:
        self._requests: dict[str, ConsultationRequest] = {}
        self._responses: dict[str, ConsultationResponse] = {}

    def request_consultation(
        self, from_agent: str, to_role: str, question: str,
    ) -> ConsultationRequest:
        """Create a consultation request from an agent to a role.

        Args:
            from_agent: ID or name of the requesting agent.
            to_role: Role being consulted (e.g. "reviewer", "strategy").
            question: The question or topic to consult on.

        Returns:
            The created ConsultationRequest.
        """
        req = ConsultationRequest(
            from_agent=from_agent,
            to_role=to_role,
            question=question,
        )
        self._requests[req.id] = req
        logger.debug(
            "Consultation request %s from '%s' to role '%s'",
            req.id, from_agent, to_role,
        )
        return req

    def respond_to_consultation(
        self, request_id: str, response: str, responder: str = "",
    ) -> ConsultationResponse:
        """Respond to a consultation request.

        Args:
            request_id: ID of the consultation request to respond to.
            response: The response content.
            responder: ID or name of the responding agent.

        Returns:
            The created ConsultationResponse.

        Raises:
            KeyError: If the request_id does not exist.
            ValueError: If the request has already been responded to.
        """
        if request_id not in self._requests:
            raise KeyError(f"Consultation request '{request_id}' not found")

        req = self._requests[request_id]
        if req.status == ConsultationStatus.RESPONDED:
            raise ValueError(
                f"Consultation request '{request_id}' already responded to"
            )

        resp = ConsultationResponse(
            request_id=request_id,
            responder=responder,
            response=response,
        )
        self._responses[request_id] = resp
        req.status = ConsultationStatus.RESPONDED
        logger.debug(
            "Consultation response %s for request %s by '%s'",
            resp.id, request_id, responder,
        )
        return resp

    def get_request(self, request_id: str) -> ConsultationRequest | None:
        """Get a consultation request by ID."""
        return self._requests.get(request_id)

    def get_response(self, request_id: str) -> ConsultationResponse | None:
        """Get the response for a consultation request."""
        return self._responses.get(request_id)

    def get_pending_requests(self, to_role: str = "") -> list[ConsultationRequest]:
        """Get pending consultation requests, optionally filtered by role."""
        pending = [
            r for r in self._requests.values()
            if r.status == ConsultationStatus.PENDING
        ]
        if to_role:
            pending = [r for r in pending if r.to_role == to_role]
        return pending
