"""Dashboard authentication — user model, password utilities, and JWT sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
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


# ---------------------------------------------------------------------------
# JWT helpers (HMAC-SHA256, stdlib only — no PyJWT dependency)
# ---------------------------------------------------------------------------

def _get_jwt_secret() -> str:
    """Return the JWT signing secret from the environment.

    Falls back to a per-process random secret when the env var is unset
    (suitable for development; production deployments MUST set
    ``CP_JWT_SECRET``).
    """
    return os.environ.get("CP_JWT_SECRET") or secrets.token_hex(32)


# Materialise once per process so all calls within the same process share the
# same secret (important when the fallback random secret is used).
JWT_SECRET: str = _get_jwt_secret()
JWT_EXPIRY_SECONDS: int = 3600  # 1 hour


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_access_token(user: DashboardUser, secret: str = JWT_SECRET, expiry: int = JWT_EXPIRY_SECONDS) -> str:
    """Create an HMAC-SHA256 JWT for *user*."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user.id,
        "email": user.email,
        "role": user.role.value,
        "exp": int(time.time()) + expiry,
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def decode_access_token(token: str, secret: str = JWT_SECRET) -> dict | None:
    """Decode and validate an HMAC-SHA256 JWT. Returns payload dict or ``None``."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    signing_input = f"{parts[0]}.{parts[1]}"
    expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(parts[2])
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ---------------------------------------------------------------------------
# In-memory user store & token blacklist
# ---------------------------------------------------------------------------

_USER_STORE: dict[str, DashboardUser] = {}  # keyed by email
_TOKEN_BLACKLIST: set[str] = set()


def register_user(
    email: str,
    password: str,
    role: DashboardRole = DashboardRole.VIEWER,
) -> DashboardUser:
    """Register a user in the in-memory store and return it."""
    user = create_user(email, password, role=role)
    _USER_STORE[email] = user
    return user


# ---------------------------------------------------------------------------
# API endpoints (pure functions, JSON-serializable return values)
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised when an auth operation fails."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def login(email: str, password: str) -> dict:
    """POST /api/auth/login — authenticate and return a JWT token.

    Returns ``{"token": "<jwt>", "user": {...}}`` on success.
    Raises :class:`AuthError` on failure.
    """
    user = _USER_STORE.get(email)
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password", status_code=401)
    token = create_access_token(user)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "role": user.role.value},
    }


def logout(token: str) -> dict:
    """POST /api/auth/logout — invalidate the given token.

    Returns ``{"ok": True}`` on success.
    Raises :class:`AuthError` if the token is already invalid.
    """
    payload = decode_access_token(token)
    if payload is None or token in _TOKEN_BLACKLIST:
        raise AuthError("Invalid or expired token", status_code=401)
    _TOKEN_BLACKLIST.add(token)
    return {"ok": True}


def get_me(token: str) -> dict:
    """GET /api/auth/me — return the current user's profile.

    Returns ``{"id": ..., "email": ..., "role": ...}``.
    Raises :class:`AuthError` if the token is invalid.
    """
    user = auth_required(token)
    return {"id": user.id, "email": user.email, "role": user.role.value}


def auth_required(token: str) -> DashboardUser:
    """Auth middleware — validate JWT and return the associated user.

    Raises :class:`AuthError` if the token is invalid, expired, or blacklisted.
    """
    if token in _TOKEN_BLACKLIST:
        raise AuthError("Token has been revoked", status_code=401)
    payload = decode_access_token(token)
    if payload is None:
        raise AuthError("Invalid or expired token", status_code=401)
    email = payload.get("email", "")
    user = _USER_STORE.get(email)
    if user is None:
        raise AuthError("User not found", status_code=401)
    return user
