"""Unit tests for Slack notification provider — focused on the five required scenarios."""

import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from crazypumpkin.notifications.slack import SlackWebhookChannel

WEBHOOK_URL = "https://hooks.slack.com/services/T00/B00/xxxx"


# ---------------------------------------------------------------------------
# 1. Successful message send returns ok
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_message_success(mock_urlopen):
    """Sending a message succeeds when the webhook returns 200."""
    mock_urlopen.return_value = MagicMock(status=200)
    ch = SlackWebhookChannel(WEBHOOK_URL)
    # Should not raise
    ch.send_message("deploy finished")
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["text"] == "deploy finished"


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_success(mock_urlopen):
    """Sending an alert succeeds and includes the correct severity prefix."""
    mock_urlopen.return_value = MagicMock(status=200)
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("all clear", level="info")
    mock_urlopen.assert_called_once()
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert "all clear" in payload["text"]
    assert ":information_source:" in payload["text"]


# ---------------------------------------------------------------------------
# 2. Webhook URL validation rejects invalid URLs
# ---------------------------------------------------------------------------

def test_empty_webhook_url_rejected():
    """An empty webhook URL raises ValueError."""
    with pytest.raises(ValueError, match="webhook_url is required"):
        SlackWebhookChannel("")


def test_none_webhook_url_rejected():
    """None as webhook URL is rejected."""
    with pytest.raises((ValueError, TypeError)):
        SlackWebhookChannel(None)


def test_from_config_empty_webhook_rejected():
    """from_config with no webhook_url raises ValueError."""
    with pytest.raises(ValueError, match="webhook_url is required"):
        SlackWebhookChannel.from_config({})


# ---------------------------------------------------------------------------
# 3. Message formatting includes agent name and status
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_alert_formatting_includes_level_and_message(mock_urlopen):
    """Alert text contains the level label and the original message."""
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("Agent Nova completed task", level="info")
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert "*[INFO]*" in payload["text"]
    assert "Agent Nova completed task" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_alert_formatting_error_level(mock_urlopen):
    """Error-level alerts carry the :x: emoji and ERROR label."""
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("Agent Reaper failed: timeout", level="error")
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":x:" in payload["text"]
    assert "*[ERROR]*" in payload["text"]
    assert "Agent Reaper failed: timeout" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_message_payload_includes_channel_and_username(mock_urlopen):
    """Channel and username overrides appear in the posted payload."""
    ch = SlackWebhookChannel(WEBHOOK_URL, channel="#agents", username="CrazyPumpkin")
    ch.send_message("Agent Nova is running")
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert payload["channel"] == "#agents"
    assert payload["username"] == "CrazyPumpkin"
    assert "Agent Nova is running" in payload["text"]


# ---------------------------------------------------------------------------
# 4. HTTP 4xx/5xx responses raise appropriate exceptions
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_400_raises(mock_urlopen):
    """A 400 Bad Request is raised to the caller."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 400, "Bad Request", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("bad payload")
    assert exc_info.value.code == 400


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_403_raises(mock_urlopen):
    """A 403 Forbidden is raised without retrying."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 403, "Forbidden", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("not allowed")
    assert exc_info.value.code == 403
    assert mock_urlopen.call_count == 1


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_404_raises(mock_urlopen):
    """A 404 Not Found is raised to the caller."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 404, "Not Found", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("missing")
    assert exc_info.value.code == 404


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_500_raises(mock_urlopen):
    """A 500 Internal Server Error is raised to the caller."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 500, "Internal Server Error", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("server error")
    assert exc_info.value.code == 500


# ---------------------------------------------------------------------------
# 5. Timeout handling
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_socket_timeout_raises_urlerror(mock_urlopen):
    """A socket timeout is surfaced as a URLError."""
    mock_urlopen.side_effect = urllib.error.URLError(socket.timeout("timed out"))
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.URLError) as exc_info:
        ch.send_message("will timeout")
    assert "timed out" in str(exc_info.value)


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_connection_timeout_raises_urlerror(mock_urlopen):
    """A connection-refused/timeout scenario raises URLError."""
    mock_urlopen.side_effect = urllib.error.URLError("Connection timed out")
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.URLError):
        ch.send_message("connection timeout")


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_timeout_error_raises(mock_urlopen):
    """A raw TimeoutError propagates to the caller."""
    mock_urlopen.side_effect = TimeoutError("request timed out")
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(TimeoutError):
        ch.send_message("raw timeout")
