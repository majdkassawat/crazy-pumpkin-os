"""Unit tests for email notification provider — covers success, SMTP failure,
recipient validation, and agent context in message body."""

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from crazypumpkin.notifications.email import send_email, send_email_async, _get_smtp_settings


# ---------------------------------------------------------------------------
# Helper: build a mock SMTP context manager
# ---------------------------------------------------------------------------

def _mock_smtp_cm(mock_smtp_cls):
    """Wire up __enter__/__exit__ on the mock SMTP class and return the server."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
    return mock_server


SMTP_CONFIG = {
    "smtp_host": "smtp.test.io",
    "smtp_port": 587,
    "smtp_user": "bot@test.io",
    "smtp_password": "pw",
}


# ---------------------------------------------------------------------------
# 1. Successful email send
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_success(mock_smtp_cls):
    """A well-formed send_email call connects, logs in, and sends."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("dev@test.io", "Deploy OK", "Agent Nova finished deploy", config=SMTP_CONFIG)

    mock_smtp_cls.assert_called_once_with("smtp.test.io", 587)
    mock_server.login.assert_called_once_with("bot@test.io", "pw")
    mock_server.sendmail.assert_called_once()

    from_addr, to_addrs, raw_msg = mock_server.sendmail.call_args[0]
    assert from_addr == "bot@test.io"
    assert to_addrs == ["dev@test.io"]
    assert "Subject: Deploy OK" in raw_msg
    assert "Agent Nova finished deploy" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_send_email_success_no_credentials(mock_smtp_cls):
    """When no credentials are configured, login is skipped but send succeeds."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("dev@test.io", "Info", "no-auth email", config={})

    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# 2. SMTP connection failure handling
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_smtp_connection_refused(mock_smtp_cls):
    """A ConnectionRefusedError from SMTP propagates to the caller."""
    mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

    with pytest.raises(ConnectionRefusedError):
        send_email("dev@test.io", "Hi", "body", config=SMTP_CONFIG)


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_smtp_auth_error(mock_smtp_cls):
    """An SMTP authentication error propagates to the caller."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

    with pytest.raises(smtplib.SMTPAuthenticationError):
        send_email("dev@test.io", "Subj", "Body", config=SMTP_CONFIG)


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_smtp_sendmail_failure(mock_smtp_cls):
    """An SMTPException during sendmail propagates to the caller."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)
    mock_server.sendmail.side_effect = smtplib.SMTPException("Sending failed")

    with pytest.raises(smtplib.SMTPException, match="Sending failed"):
        send_email("dev@test.io", "Subj", "Body", config=SMTP_CONFIG)


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_smtp_timeout(mock_smtp_cls):
    """A socket timeout during SMTP connect propagates to the caller."""
    import socket
    mock_smtp_cls.side_effect = socket.timeout("Connection timed out")

    with pytest.raises(socket.timeout):
        send_email("dev@test.io", "Hi", "body", config=SMTP_CONFIG)


# ---------------------------------------------------------------------------
# 3. Recipient validation — the recipient appears in headers/envelope
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_recipient_in_to_header(mock_smtp_cls):
    """The To header of the sent message matches the recipient argument."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("alice@example.com", "Subj", "Body", config=SMTP_CONFIG)

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "To: alice@example.com" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_recipient_in_envelope(mock_smtp_cls):
    """The SMTP envelope passes the recipient as a list."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("bob@example.com", "Subj", "Body", config=SMTP_CONFIG)

    to_addrs = mock_server.sendmail.call_args[0][1]
    assert to_addrs == ["bob@example.com"]


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_from_defaults_when_no_user(mock_smtp_cls):
    """When smtp_user is empty, From defaults to noreply@localhost."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("dev@test.io", "Subj", "Body", config={})

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "From: noreply@localhost" in raw_msg


# ---------------------------------------------------------------------------
# 4. Message body contains agent context
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_body_contains_agent_context(mock_smtp_cls):
    """The email body preserves agent name and task details passed by the caller."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    body = "Agent: Nova | Task: code-review | Status: complete"
    send_email("team@test.io", "Agent Report", body, config=SMTP_CONFIG)

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "Agent: Nova" in raw_msg
    assert "Task: code-review" in raw_msg
    assert "Status: complete" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_body_contains_multiline_agent_output(mock_smtp_cls):
    """Multi-line agent output is preserved intact in the email body."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    body = "Agent Reaper encountered an error:\nTimeoutError: request timed out\nRetries exhausted"
    send_email("ops@test.io", "Agent Failure", body, config=SMTP_CONFIG)

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "Agent Reaper encountered an error" in raw_msg
    assert "TimeoutError" in raw_msg
    assert "Retries exhausted" in raw_msg


@patch("crazypumpkin.notifications.email.smtplib.SMTP")
def test_subject_carries_agent_context(mock_smtp_cls):
    """The subject line carries agent context when the caller provides it."""
    mock_server = _mock_smtp_cm(mock_smtp_cls)

    send_email("dev@test.io", "[CrazyPumpkin] Agent Nova - deploy complete", "details", config=SMTP_CONFIG)

    raw_msg = mock_server.sendmail.call_args[0][2]
    assert "Subject: [CrazyPumpkin] Agent Nova - deploy complete" in raw_msg
