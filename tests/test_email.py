"""Tests for the email notification module."""

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_email_mod = importlib.import_module("crazypumpkin.notifications.email")
send_email = _email_mod.send_email
send_email_async = _email_mod.send_email_async
_get_smtp_settings = _email_mod._get_smtp_settings


# ---------------------------------------------------------------------------
# SMTP settings from config
# ---------------------------------------------------------------------------

def test_smtp_settings_from_config():
    """SMTP settings are correctly read from a config dict."""
    cfg = {
        "smtp_host": "mail.example.com",
        "smtp_port": 465,
        "smtp_user": "alice@example.com",
        "smtp_password": "s3cret",
    }
    settings = _get_smtp_settings(cfg)
    assert settings["host"] == "mail.example.com"
    assert settings["port"] == 465
    assert settings["user"] == "alice@example.com"
    assert settings["password"] == "s3cret"


def test_smtp_settings_defaults():
    """Missing config keys fall back to defaults."""
    settings = _get_smtp_settings(None)
    assert settings["host"] == "localhost"
    assert settings["port"] == 587
    assert settings["user"] == ""
    assert settings["password"] == ""


def test_smtp_settings_partial_config():
    """Partial config uses defaults for missing keys."""
    cfg = {"smtp_host": "custom.host"}
    settings = _get_smtp_settings(cfg)
    assert settings["host"] == "custom.host"
    assert settings["port"] == 587


# ---------------------------------------------------------------------------
# send_email — mock SMTP
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_basic(mock_smtp_cls):
    """send_email connects to SMTP and sends a correctly formatted message."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    config = {
        "smtp_host": "smtp.test.io",
        "smtp_port": 25,
        "smtp_user": "bot@test.io",
        "smtp_password": "pw",
    }
    send_email("dev@test.io", "Hello", "World", config=config)

    mock_smtp_cls.assert_called_once_with("smtp.test.io", 25)
    mock_server.login.assert_called_once_with("bot@test.io", "pw")
    mock_server.sendmail.assert_called_once()

    call_args = mock_server.sendmail.call_args
    from_addr = call_args[0][0]
    to_addrs = call_args[0][1]
    raw_msg = call_args[0][2]

    assert from_addr == "bot@test.io"
    assert to_addrs == ["dev@test.io"]
    assert "Subject: Hello" in raw_msg
    assert "World" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_no_credentials(mock_smtp_cls):
    """When no user/password, login is skipped."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_email("dev@test.io", "Hi", "Body", config={})

    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_message_formatting(mock_smtp_cls):
    """Verify To/From/Subject headers in the sent message."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    config = {
        "smtp_host": "smtp.test.io",
        "smtp_port": 587,
        "smtp_user": "sender@test.io",
        "smtp_password": "pw",
    }
    send_email("recipient@test.io", "Test Subject", "Test Body", config=config)

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "To: recipient@test.io" in raw_msg
    assert "From: sender@test.io" in raw_msg
    assert "Subject: Test Subject" in raw_msg
    assert "Test Body" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_default_from_when_no_user(mock_smtp_cls):
    """When no smtp_user is set, From defaults to noreply@localhost."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_email("dev@test.io", "Subj", "Body")

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "From: noreply@localhost" in raw_msg


# ---------------------------------------------------------------------------
# send_email_async
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_async(mock_smtp_cls):
    """send_email_async sends an email without blocking the event loop."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    config = {
        "smtp_host": "smtp.test.io",
        "smtp_port": 587,
        "smtp_user": "async@test.io",
        "smtp_password": "pw",
    }

    asyncio.run(send_email_async("dev@test.io", "Async Subj", "Async Body", config=config))

    mock_smtp_cls.assert_called_once_with("smtp.test.io", 587)
    mock_server.login.assert_called_once_with("async@test.io", "pw")
    mock_server.sendmail.assert_called_once()

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "Subject: Async Subj" in raw_msg
    assert "Async Body" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_async_no_credentials(mock_smtp_cls):
    """Async variant also skips login when no credentials configured."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    asyncio.run(send_email_async("dev@test.io", "Hi", "Body", config={}))

    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()
