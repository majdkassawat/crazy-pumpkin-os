"""Abstract base class for notification channels."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """Base class that all notification channels must implement."""

    @abstractmethod
    def send_alert(self, message: str, *, level: str = "info") -> None:
        """Send an alert message at the given severity level."""
