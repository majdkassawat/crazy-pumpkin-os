"""Slack webhook notification channel."""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import NotificationChannel

# Emoji mapping for alert severity levels.
_LEVEL_EMOJI = {
    "info": ":information_source:",
    "warning": ":warning:",
    "error": ":x:",
    "critical": ":rotating_light:",
}


class SlackWebhookChannel(NotificationChannel):
    """Notification channel that posts messages to a Slack incoming webhook.

    Parameters
    ----------
    webhook_url:
        The Slack incoming webhook URL.
    channel:
        Optional channel override (e.g. ``#alerts``).
    username:
        Optional bot username override.
    icon_emoji:
        Optional emoji icon for the bot (e.g. ``:robot_face:``).
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str | None = None,
        username: str | None = None,
        icon_emoji: str | None = None,
    ) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self._validate_webhook_url(webhook_url)
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self._batch: list[str] = []
        self._batching = False

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SlackWebhookChannel:
        """Create a SlackWebhookChannel from a config dict.

        Expected keys: ``webhook_url`` (required), ``channel``, ``username``,
        ``icon_emoji``.
        """
        return cls(
            webhook_url=config.get("webhook_url", ""),
            channel=config.get("channel"),
            username=config.get("username"),
            icon_emoji=config.get("icon_emoji"),
        )

    def send_message(self, message: str, **kwargs: Any) -> None:
        """Send a markdown-formatted message to Slack.

        If batching is active, the message is queued instead of sent
        immediately.
        """
        if self._batching:
            self._batch.append(message)
            return
        self._post({"text": message, "mrkdwn": True})

    def send_alert(self, message: str, *, level: str = "warning", **kwargs: Any) -> None:
        """Send an alert message to Slack with a severity-level prefix.

        The alert is formatted with an emoji indicator based on the level.
        If batching is active, the formatted alert is queued.
        """
        emoji = _LEVEL_EMOJI.get(level, ":grey_question:")
        formatted = f"{emoji} *[{level.upper()}]* {message}"
        if self._batching:
            self._batch.append(formatted)
            return
        self._post({"text": formatted, "mrkdwn": True})

    # -- Batching support -----------------------------------------------------

    def start_batch(self) -> None:
        """Begin batching messages instead of sending them immediately."""
        self._batching = True
        self._batch = []

    def flush_batch(self) -> int:
        """Send all batched messages as a single Slack message.

        Returns the number of messages that were flushed.
        """
        self._batching = False
        if not self._batch:
            return 0
        combined = "\n\n---\n\n".join(self._batch)
        count = len(self._batch)
        self._batch = []
        self._post({"text": combined, "mrkdwn": True})
        return count

    def discard_batch(self) -> int:
        """Discard all batched messages without sending.

        Returns the number of messages that were discarded.
        """
        self._batching = False
        count = len(self._batch)
        self._batch = []
        return count

    # -- Internal -------------------------------------------------------------

    @staticmethod
    def _validate_webhook_url(url: str) -> None:
        """Validate that *url* is a safe, external HTTP(S) URL.

        Rejects localhost, loopback, and private/reserved IP ranges to
        prevent SSRF attacks.
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"webhook_url must use http or https scheme, got {parsed.scheme!r}"
            )
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("webhook_url must include a hostname")
        # Reject well-known localhost aliases.
        if hostname in ("localhost",):
            raise ValueError(
                f"webhook_url must not point to localhost ({hostname})"
            )
        # If the hostname is an IP literal, check for private/reserved ranges.
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            pass  # Not an IP literal — regular hostname, allowed.
        else:
            if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_link_local:
                raise ValueError(
                    f"webhook_url must not point to a private or reserved address ({hostname})"
                )

    def _build_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build the full webhook payload with optional overrides."""
        payload = dict(data)
        if self.channel:
            payload["channel"] = self.channel
        if self.username:
            payload["username"] = self.username
        if self.icon_emoji:
            payload["icon_emoji"] = self.icon_emoji
        return payload

    def _post(self, data: dict[str, Any], *, max_retries: int = 3) -> None:
        """POST a JSON payload to the Slack webhook URL.

        Retries automatically on HTTP 429 (rate-limited) responses, up to
        *max_retries* attempts.  The delay between retries honours the
        ``Retry-After`` header when present, falling back to exponential
        back-off (1s, 2s, 4s, …).
        """
        payload = self._build_payload(data)
        body = json.dumps(payload).encode("utf-8")

        for attempt in range(max_retries):
            req = urllib.request.Request(
                self.webhook_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req)
                return
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2 ** attempt
                    time.sleep(delay)
                else:
                    raise
