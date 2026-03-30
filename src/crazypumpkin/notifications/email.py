"""Email notification module — sends email via SMTP."""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText
from typing import Any


def _get_smtp_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract SMTP settings from config dict.

    Expected config structure::

        {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password": "secret",
        }

    Falls back to sensible defaults when keys are missing.
    """
    if config is None:
        config = {}
    return {
        "host": config.get("smtp_host", "localhost"),
        "port": int(config.get("smtp_port", 587)),
        "user": config.get("smtp_user", ""),
        "password": config.get("smtp_password", ""),
    }


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    config: dict[str, Any] | None = None,
) -> None:
    """Send an email via the configured SMTP server.

    Parameters
    ----------
    to:
        Recipient email address.
    subject:
        Email subject line.
    body:
        Plain-text email body.
    config:
        Optional dict with SMTP settings (smtp_host, smtp_port,
        smtp_user, smtp_password).  When *None*, defaults are used.
    """
    settings = _get_smtp_settings(config)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings["user"] or "noreply@localhost"
    msg["To"] = to

    with smtplib.SMTP(settings["host"], settings["port"]) as server:
        if settings["user"] and settings["password"]:
            server.login(settings["user"], settings["password"])
        server.sendmail(msg["From"], [to], msg.as_string())


async def send_email_async(
    to: str,
    subject: str,
    body: str,
    *,
    config: dict[str, Any] | None = None,
) -> None:
    """Async wrapper around :func:`send_email`.

    Runs the blocking SMTP send in a thread-pool executor so it does
    not block the event loop.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: send_email(to, subject, body, config=config))
