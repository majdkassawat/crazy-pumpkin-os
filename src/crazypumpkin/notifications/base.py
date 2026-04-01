"""Base notification channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send_alert(self, message: str, level: str = "info") -> None:
        """Send an alert message at the given severity level."""
