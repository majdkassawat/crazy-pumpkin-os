"""SessionStore — high-level multi-turn session management backed by Store."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from typing import Any, Optional

from crazypumpkin.framework.models import Session, SessionMessage, SessionRecord, _now
from crazypumpkin.framework.store import Store


def _session_to_record(session: Session) -> SessionRecord:
    """Serialize a Session into a SessionRecord for Store persistence."""
    messages = [dataclasses.asdict(m) for m in session.messages]
    metadata = {
        "agent_name": session.agent_name,
        "context": session.context,
        "max_turns": session.max_turns,
        "status": session.status,
    }
    return SessionRecord(
        session_id=session.session_id,
        agent_id=session.agent_name,
        messages=messages,
        created_at=session.created_at,
        updated_at=session.updated_at,
        metadata=metadata,
    )


def _record_to_session(rec: SessionRecord) -> Session:
    """Deserialize a SessionRecord back into a Session."""
    meta = rec.metadata or {}
    messages = [
        SessionMessage(
            role=m.get("role", ""),
            content=m.get("content", ""),
            timestamp=m.get("timestamp", ""),
            metadata=m.get("metadata", {}),
        )
        for m in rec.messages
    ]
    return Session(
        session_id=rec.session_id,
        agent_name=meta.get("agent_name", rec.agent_id),
        messages=messages,
        context=meta.get("context", {}),
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        max_turns=meta.get("max_turns", 50),
        status=meta.get("status", "active"),
    )


class SessionStore:
    """Persists and retrieves multi-turn sessions."""

    def __init__(self, store: Store, namespace: str = "sessions") -> None:
        self._store = store
        self._namespace = namespace

    async def create(self, agent_name: str, max_turns: int = 50) -> Session:
        """Create a new active session for the given agent."""
        session = Session(agent_name=agent_name, max_turns=max_turns)
        self._store.save_session(_session_to_record(session))
        return session

    async def get(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID, or return None if not found."""
        rec = self._store.load_session(session_id)
        if rec is None:
            return None
        return _record_to_session(rec)

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Add a message to an existing session and update its timestamp."""
        rec = self._store.load_session(session_id)
        if rec is None:
            raise KeyError(f"Session {session_id} not found")
        session = _record_to_session(rec)
        msg = SessionMessage(role=role, content=content, metadata=metadata or {})
        session.messages.append(msg)
        session.updated_at = _now()
        self._store.save_session(_session_to_record(session))
        return session

    async def list_sessions(
        self,
        agent_name: str | None = None,
        status: str | None = None,
    ) -> list[Session]:
        """List sessions, optionally filtered by agent_name and/or status."""
        records = self._store.list_sessions(agent_id=agent_name or "")
        sessions = [_record_to_session(r) for r in records]
        # If agent_name was None, we got all sessions (empty string = no filter)
        # But if agent_name was explicitly None, list_sessions("") returns all
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        return sessions

    async def close(self, session_id: str) -> Session:
        """Close a session by setting its status to 'completed'."""
        rec = self._store.load_session(session_id)
        if rec is None:
            raise KeyError(f"Session {session_id} not found")
        session = _record_to_session(rec)
        session.status = "completed"
        session.updated_at = _now()
        self._store.save_session(_session_to_record(session))
        return session
