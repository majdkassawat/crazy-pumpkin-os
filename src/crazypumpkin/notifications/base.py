"""Abstract base class for notification channels."""

from __future__ import annotations

import abc
from typing import Any


class NotificationChannel(abc.ABC):
    """Base class that all notification channels must implement.

    Subclasses must override :meth:`send_message` and :meth:`send_alert`.
    """

    @abc.abstractmethod
    def send_message(self, message: str, **kwargs: Any) -> None:
        """Send a plain message through this channel.

        Parameters
        ----------
        message:
            The message text.
        """

    @abc.abstractmethod
    def send_alert(self, message: str, *, level: str = "warning", **kwargs: Any) -> None:
        """Send an alert with a severity level through this channel.

        Parameters
        ----------
        message:
            The alert message text.
        level:
            Severity level — one of ``"info"``, ``"warning"``,
            ``"error"``, or ``"critical"``.
        """
