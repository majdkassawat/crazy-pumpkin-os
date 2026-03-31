"""Tests for the Slack webhook notification channel."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from crazypumpkin.notifications.base import NotificationChannel
from crazypumpkin.notifications.slack import SlackWebhookChannel


WEBHOOK_URL = "https://hooks.slack.com/services/T00/B00/xxxx"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_requires_webhook_url():
    with pytest.raises(ValueError, match="webhook_url is required"):
        SlackWebhookChannel("")


def test_implements_notification_channel():
    ch = SlackWebhookChannel(WEBHOOK_URL)
    assert isinstance(ch, NotificationChannel)


def test_from_config():
    cfg = {
        "webhook_url": WEBHOOK_URL,
        "channel": "#ops",
        "username": "bot",
        "icon_emoji": ":ghost:",
    }
    ch = SlackWebhookChannel.from_config(cfg)
    assert ch.webhook_url == WEBHOOK_URL
    assert ch.channel == "#ops"
    assert ch.username == "bot"
    assert ch.icon_emoji == ":ghost:"


def test_from_config_minimal():
    cfg = {"webhook_url": WEBHOOK_URL}
    ch = SlackWebhookChannel.from_config(cfg)
    assert ch.channel is None
    assert ch.username is None


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_message(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_message("Hello *world*")

    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["text"] == "Hello *world*"
    assert payload["mrkdwn"] is True
    assert req.get_header("Content-type") == "application/json"


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_message_with_overrides(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL, channel="#dev", username="cpbot")
    ch.send_message("hi")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert payload["channel"] == "#dev"
    assert payload["username"] == "cpbot"


# ---------------------------------------------------------------------------
# send_alert
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_default_level(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("disk full")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":warning:" in payload["text"]
    assert "*[WARNING]*" in payload["text"]
    assert "disk full" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_error_level(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("pipeline failed", level="error")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":x:" in payload["text"]
    assert "*[ERROR]*" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_info_level(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("deploy complete", level="info")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":information_source:" in payload["text"]
    assert "*[INFO]*" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_critical_level(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("outage", level="critical")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":rotating_light:" in payload["text"]
    assert "*[CRITICAL]*" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_send_alert_unknown_level(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_alert("something", level="custom")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert ":grey_question:" in payload["text"]
    assert "*[CUSTOM]*" in payload["text"]


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_batch_queues_messages(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.start_batch()
    ch.send_message("msg1")
    ch.send_message("msg2")
    ch.send_alert("alert1", level="error")

    mock_urlopen.assert_not_called()


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_flush_batch_sends_combined(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.start_batch()
    ch.send_message("one")
    ch.send_message("two")
    count = ch.flush_batch()

    assert count == 2
    mock_urlopen.assert_called_once()
    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert "one" in payload["text"]
    assert "two" in payload["text"]
    assert "---" in payload["text"]


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_flush_empty_batch(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.start_batch()
    count = ch.flush_batch()

    assert count == 0
    mock_urlopen.assert_not_called()


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_discard_batch(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.start_batch()
    ch.send_message("will be dropped")
    ch.send_message("also dropped")
    count = ch.discard_batch()

    assert count == 2
    mock_urlopen.assert_not_called()


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_messages_send_immediately_after_flush(mock_urlopen):
    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.start_batch()
    ch.send_message("batched")
    ch.flush_batch()
    ch.send_message("immediate")

    assert mock_urlopen.call_count == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_error_propagates(mock_urlopen):
    """Non-429 HTTP errors are raised to the caller."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 500, "Internal Server Error", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("boom")
    assert exc_info.value.code == 500


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_url_error_propagates(mock_urlopen):
    """Network-level errors (URLError) propagate."""
    mock_urlopen.side_effect = urllib.error.URLError("DNS lookup failed")
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.URLError):
        ch.send_message("no host")


@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_http_403_not_retried(mock_urlopen):
    """A 403 error is raised immediately without retrying."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        WEBHOOK_URL, 403, "Forbidden", {}, None
    )
    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError):
        ch.send_message("forbidden")
    assert mock_urlopen.call_count == 1


# ---------------------------------------------------------------------------
# Retry on 429
# ---------------------------------------------------------------------------

@patch("crazypumpkin.notifications.slack.time.sleep")
@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_retry_on_429_then_success(mock_urlopen, mock_sleep):
    """A 429 response triggers a retry; subsequent success completes normally."""
    headers = MagicMock()
    headers.get.return_value = None  # no Retry-After header
    err = urllib.error.HTTPError(WEBHOOK_URL, 429, "Too Many Requests", headers, None)
    mock_urlopen.side_effect = [err, None]

    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_message("retry me")

    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once_with(1)  # 2**0 = 1


@patch("crazypumpkin.notifications.slack.time.sleep")
@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_retry_on_429_respects_retry_after_header(mock_urlopen, mock_sleep):
    """When a 429 includes Retry-After, that delay is used."""
    headers = MagicMock()
    headers.get.return_value = "5"
    err = urllib.error.HTTPError(WEBHOOK_URL, 429, "Too Many Requests", headers, None)
    mock_urlopen.side_effect = [err, None]

    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_message("wait 5s")

    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once_with(5.0)


@patch("crazypumpkin.notifications.slack.time.sleep")
@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_retry_on_429_exhausts_retries(mock_urlopen, mock_sleep):
    """After max retries on 429, the error is raised."""
    headers = MagicMock()
    headers.get.return_value = None
    err = urllib.error.HTTPError(WEBHOOK_URL, 429, "Too Many Requests", headers, None)
    mock_urlopen.side_effect = err  # always 429

    ch = SlackWebhookChannel(WEBHOOK_URL)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ch.send_message("always rate-limited")
    assert exc_info.value.code == 429
    assert mock_urlopen.call_count == 3  # default max_retries=3
    assert mock_sleep.call_count == 2    # sleeps between attempts 0→1, 1→2


@patch("crazypumpkin.notifications.slack.time.sleep")
@patch("crazypumpkin.notifications.slack.urllib.request.urlopen")
def test_retry_exponential_backoff(mock_urlopen, mock_sleep):
    """Backoff delays follow 2^attempt when no Retry-After header."""
    headers = MagicMock()
    headers.get.return_value = None
    err = urllib.error.HTTPError(WEBHOOK_URL, 429, "Too Many Requests", headers, None)
    # fail twice, succeed on third
    mock_urlopen.side_effect = [err, err, None]

    ch = SlackWebhookChannel(WEBHOOK_URL)
    ch.send_message("backoff")

    assert mock_urlopen.call_count == 3
    delays = [call[0][0] for call in mock_sleep.call_args_list]
    assert delays == [1, 2]  # 2**0, 2**1


# ---------------------------------------------------------------------------
# Config validation edge cases
# ---------------------------------------------------------------------------

def test_from_config_missing_webhook_url():
    """from_config with empty dict raises ValueError."""
    with pytest.raises(ValueError, match="webhook_url is required"):
        SlackWebhookChannel.from_config({})


def test_constructor_rejects_none_webhook_url():
    """Passing None as webhook_url is rejected (falsy value)."""
    with pytest.raises((ValueError, TypeError)):
        SlackWebhookChannel(None)


def test_icon_emoji_included_in_payload():
    """icon_emoji is included in the webhook payload when set."""
    ch = SlackWebhookChannel(WEBHOOK_URL, icon_emoji=":robot_face:")
    payload = ch._build_payload({"text": "test"})
    assert payload["icon_emoji"] == ":robot_face:"


def test_payload_without_overrides():
    """Payload has no channel/username/icon_emoji when not configured."""
    ch = SlackWebhookChannel(WEBHOOK_URL)
    payload = ch._build_payload({"text": "test"})
    assert "channel" not in payload
    assert "username" not in payload
    assert "icon_emoji" not in payload


# ---------------------------------------------------------------------------
# Public API re-export
# ---------------------------------------------------------------------------

def test_importable_from_notifications_package():
    from crazypumpkin.notifications import SlackWebhookChannel as Cls
    assert Cls is SlackWebhookChannel

    from crazypumpkin.notifications import NotificationChannel as Base
    assert Base is NotificationChannel
