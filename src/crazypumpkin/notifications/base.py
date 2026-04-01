"""Base notification channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send_message(self, message: str, **kwargs: Any) -> None:
        """Send a plain message through the channel.

        Parameters
        ----------
        message:
            The message text to send.
        **kwargs:
            Channel-specific options.
        """

    @abstractmethod
    def send_alert(self, message: str, *, level: str = "warning", **kwargs: Any) -> None:
        """Send an alert/notification through the channel.

        Parameters
        ----------
        message:
            The alert message text.
        level:
            Severity level (e.g. "info", "warning", "error", "critical").
        **kwargs:
            Channel-specific options.
        """
