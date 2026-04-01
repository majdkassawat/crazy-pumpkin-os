"""Tests for dashboard authentication — user model and password hashing."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Ensure local src is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_auth = importlib.import_module("crazypumpkin.dashboard.auth")

DashboardRole = _auth.DashboardRole
DashboardUser = _auth.DashboardUser
create_user = _auth.create_user
verify_password = _auth.verify_password


# ── DashboardUser model ──


def test_dashboard_user_defaults():
    user = DashboardUser()
    assert user.email == ""
    assert user.hashed_password == ""
    assert user.role == DashboardRole.VIEWER
    assert len(user.id) == 12


def test_dashboard_user_roles():
    assert DashboardRole.ADMIN.value == "admin"
    assert DashboardRole.VIEWER.value == "viewer"


# ── create_user ──


def test_create_user_hashes_password():
    user = create_user("alice@example.com", "secret123")
    assert user.email == "alice@example.com"
    assert user.role == DashboardRole.VIEWER
    assert user.hashed_password != "secret123"
    assert user.hashed_password.startswith("$2")


def test_create_user_admin_role():
    user = create_user("admin@example.com", "admin_pass", role=DashboardRole.ADMIN)
    assert user.role == DashboardRole.ADMIN


def test_create_user_unique_ids():
    u1 = create_user("a@example.com", "pw")
    u2 = create_user("b@example.com", "pw")
    assert u1.id != u2.id


# ── verify_password ──


def test_verify_password_correct():
    user = create_user("test@example.com", "my_password")
    assert verify_password("my_password", user.hashed_password) is True


def test_verify_password_wrong():
    user = create_user("test@example.com", "my_password")
    assert verify_password("wrong_password", user.hashed_password) is False


def test_verify_password_different_hashes():
    u1 = create_user("a@example.com", "same_pw")
    u2 = create_user("b@example.com", "same_pw")
    # bcrypt salts differ, so hashes differ
    assert u1.hashed_password != u2.hashed_password
    # but both verify correctly
    assert verify_password("same_pw", u1.hashed_password) is True
    assert verify_password("same_pw", u2.hashed_password) is True
