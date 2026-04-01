"""Dashboard authentication — user model and password utilities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

import bcrypt


class DashboardRole(str, Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


@dataclass
class DashboardUser:
    """A dashboard user with hashed credentials."""

    email: str = ""
    hashed_password: str = ""
    role: DashboardRole = DashboardRole.VIEWER
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


def create_user(
    email: str,
    password: str,
    role: DashboardRole = DashboardRole.VIEWER,
) -> DashboardUser:
    """Create a new DashboardUser with a bcrypt-hashed password."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return DashboardUser(
        email=email,
        hashed_password=hashed.decode("utf-8"),
        role=role,
    )


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )
