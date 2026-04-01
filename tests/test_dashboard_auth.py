"""Tests for dashboard authentication — user model, password hashing, and JWT sessions."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Ensure local src is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_auth = importlib.import_module("crazypumpkin.dashboard.auth")

DashboardRole = _auth.DashboardRole
DashboardUser = _auth.DashboardUser
create_user = _auth.create_user
verify_password = _auth.verify_password
create_access_token = _auth.create_access_token
decode_access_token = _auth.decode_access_token
register_user = _auth.register_user
login = _auth.login
logout = _auth.logout
get_me = _auth.get_me
auth_required = _auth.auth_required
admin_required = _auth.admin_required
AuthError = _auth.AuthError

_api = importlib.import_module("crazypumpkin.dashboard.api")
update_config = _api.update_config
restart_agent = _api.restart_agent
get_dashboard_data_authed = _api.get_dashboard_data_authed


@pytest.fixture(autouse=True)
def _clean_auth_state():
    """Clear in-memory user store and token blacklist between tests."""
    _auth._USER_STORE.clear()
    _auth._TOKEN_BLACKLIST.clear()
    yield
    _auth._USER_STORE.clear()
    _auth._TOKEN_BLACKLIST.clear()


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


# ── JWT token creation / decoding ──


def test_create_access_token_returns_string():
    user = create_user("jwt@example.com", "pw")
    token = create_access_token(user)
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


def test_decode_access_token_roundtrip():
    user = create_user("rt@example.com", "pw", role=DashboardRole.ADMIN)
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user.id
    assert payload["email"] == "rt@example.com"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_decode_access_token_invalid():
    assert decode_access_token("not.a.token") is None
    assert decode_access_token("garbage") is None


def test_decode_access_token_tampered():
    user = create_user("t@example.com", "pw")
    token = create_access_token(user)
    parts = token.split(".")
    parts[1] = parts[1][::-1]  # corrupt payload
    assert decode_access_token(".".join(parts)) is None


def test_decode_access_token_wrong_secret():
    user = create_user("s@example.com", "pw")
    token = create_access_token(user, secret="secret-a")
    assert decode_access_token(token, secret="secret-b") is None


def test_decode_access_token_expired():
    user = create_user("exp@example.com", "pw")
    token = create_access_token(user, expiry=-1)  # already expired
    assert decode_access_token(token) is None


# ── register_user ──


def test_register_user_adds_to_store():
    user = register_user("reg@example.com", "pw123")
    assert "reg@example.com" in _auth._USER_STORE
    assert _auth._USER_STORE["reg@example.com"] is user


# ── login ──


def test_login_success():
    register_user("login@example.com", "pass123")
    result = login("login@example.com", "pass123")
    assert "token" in result
    assert "user" in result
    assert result["user"]["email"] == "login@example.com"
    # Token should be valid
    payload = decode_access_token(result["token"])
    assert payload is not None
    assert payload["email"] == "login@example.com"


def test_login_wrong_password():
    register_user("wp@example.com", "correct")
    with pytest.raises(AuthError) as exc_info:
        login("wp@example.com", "wrong")
    assert exc_info.value.status_code == 401


def test_login_unknown_user():
    with pytest.raises(AuthError) as exc_info:
        login("nobody@example.com", "any")
    assert exc_info.value.status_code == 401


def test_login_returns_role():
    register_user("admin@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("admin@example.com", "pw")
    assert result["user"]["role"] == "admin"


# ── logout ──


def test_logout_invalidates_token():
    register_user("lo@example.com", "pw")
    result = login("lo@example.com", "pw")
    token = result["token"]
    resp = logout(token)
    assert resp == {"ok": True}
    # Token should now be blacklisted
    assert token in _auth._TOKEN_BLACKLIST


def test_logout_rejects_invalid_token():
    with pytest.raises(AuthError):
        logout("invalid.token.here")


def test_logout_rejects_already_revoked():
    register_user("rev@example.com", "pw")
    result = login("rev@example.com", "pw")
    token = result["token"]
    logout(token)
    with pytest.raises(AuthError):
        logout(token)


# ── get_me ──


def test_get_me_returns_user_info():
    register_user("me@example.com", "pw", role=DashboardRole.VIEWER)
    result = login("me@example.com", "pw")
    me = get_me(result["token"])
    assert me["email"] == "me@example.com"
    assert me["role"] == "viewer"
    assert "id" in me


def test_get_me_invalid_token():
    with pytest.raises(AuthError):
        get_me("bad.token.value")


def test_get_me_after_logout():
    register_user("post@example.com", "pw")
    result = login("post@example.com", "pw")
    logout(result["token"])
    with pytest.raises(AuthError):
        get_me(result["token"])


# ── auth_required (middleware) ──


def test_auth_required_returns_user():
    register_user("mw@example.com", "pw")
    result = login("mw@example.com", "pw")
    user = auth_required(result["token"])
    assert isinstance(user, DashboardUser)
    assert user.email == "mw@example.com"


def test_auth_required_rejects_invalid():
    with pytest.raises(AuthError):
        auth_required("nope")


def test_auth_required_rejects_blacklisted():
    register_user("bl@example.com", "pw")
    result = login("bl@example.com", "pw")
    token = result["token"]
    _auth._TOKEN_BLACKLIST.add(token)
    with pytest.raises(AuthError):
        auth_required(token)


# ── admin_required (RBAC middleware) ──


def test_admin_required_returns_admin_user():
    register_user("adm@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("adm@example.com", "pw")
    user = admin_required(result["token"])
    assert isinstance(user, DashboardUser)
    assert user.role == DashboardRole.ADMIN


def test_admin_required_rejects_viewer_with_403():
    register_user("viewer@example.com", "pw", role=DashboardRole.VIEWER)
    result = login("viewer@example.com", "pw")
    with pytest.raises(AuthError) as exc_info:
        admin_required(result["token"])
    assert exc_info.value.status_code == 403


def test_admin_required_rejects_invalid_token():
    with pytest.raises(AuthError) as exc_info:
        admin_required("bad.token.here")
    assert exc_info.value.status_code == 401


def test_admin_required_rejects_blacklisted_token():
    register_user("adm2@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("adm2@example.com", "pw")
    token = result["token"]
    _auth._TOKEN_BLACKLIST.add(token)
    with pytest.raises(AuthError) as exc_info:
        admin_required(token)
    assert exc_info.value.status_code == 401


# ── Protected API endpoints (RBAC) ──


def test_update_config_allowed_for_admin():
    register_user("cfgadm@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("cfgadm@example.com", "pw")
    resp = update_config(result["token"], {"key": "value"})
    assert resp["ok"] is True
    assert resp["config"] == {"key": "value"}


def test_update_config_forbidden_for_viewer():
    register_user("cfgview@example.com", "pw", role=DashboardRole.VIEWER)
    result = login("cfgview@example.com", "pw")
    with pytest.raises(AuthError) as exc_info:
        update_config(result["token"], {"key": "value"})
    assert exc_info.value.status_code == 403


def test_update_config_rejects_invalid_token():
    with pytest.raises(AuthError) as exc_info:
        update_config("invalid.tok.en", {})
    assert exc_info.value.status_code == 401


def test_restart_agent_allowed_for_admin():
    register_user("rsadm@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("rsadm@example.com", "pw")
    resp = restart_agent(result["token"], "agent-42", None)
    assert resp["ok"] is True
    assert resp["agent_id"] == "agent-42"


def test_restart_agent_forbidden_for_viewer():
    register_user("rsview@example.com", "pw", role=DashboardRole.VIEWER)
    result = login("rsview@example.com", "pw")
    with pytest.raises(AuthError) as exc_info:
        restart_agent(result["token"], "agent-42", None)
    assert exc_info.value.status_code == 403


def test_restart_agent_rejects_invalid_token():
    with pytest.raises(AuthError) as exc_info:
        restart_agent("invalid.tok.en", "agent-42", None)
    assert exc_info.value.status_code == 401


def test_get_dashboard_data_authed_allowed_for_viewer():
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

    register_user("dashview@example.com", "pw", role=DashboardRole.VIEWER)
    result = login("dashview@example.com", "pw")
    data = get_dashboard_data_authed(result["token"], AgentRegistry(), Store())
    assert isinstance(data, dict)
    assert "agents" in data


def test_get_dashboard_data_authed_allowed_for_admin():
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

    register_user("dashadm@example.com", "pw", role=DashboardRole.ADMIN)
    result = login("dashadm@example.com", "pw")
    data = get_dashboard_data_authed(result["token"], AgentRegistry(), Store())
    assert isinstance(data, dict)
    assert "agents" in data


def test_get_dashboard_data_authed_rejects_invalid_token():
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

    with pytest.raises(AuthError) as exc_info:
        get_dashboard_data_authed("invalid.tok.en", AgentRegistry(), Store())
    assert exc_info.value.status_code == 401
