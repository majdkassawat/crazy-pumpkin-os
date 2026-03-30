"""Structured logging with correlation-ID propagation.

Every log record emitted through ``get_logger`` carries a ``correlation_id``
attribute sourced from a :class:`contextvars.ContextVar`.  This allows
tracing a single request / task execution across nested calls without
passing the ID explicitly.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

# ---------------------------------------------------------------------------
# Context variable that holds the current correlation ID.
# Any code running in the same async/sync context will inherit the value.
# ---------------------------------------------------------------------------
correlation_id_var: ContextVar[str] = ContextVar(
    "correlation_id", default=""
)


class CorrelationFilter(logging.Filter):
    """Inject ``correlation_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()  # type: ignore[attr-defined]
        return True


def get_logger(
    name: str,
    correlation_id: str | None = None,
) -> logging.Logger:
    """Return a logger that attaches a correlation ID to every record.

    If *correlation_id* is supplied it is stored in the context variable so
    that downstream loggers (and any code sharing the same context) will
    automatically pick it up.  If omitted the current context value is kept;
    if no value has been set yet a new UUID-4 is generated.

    Args:
        name: Logger name (e.g. ``"crazypumpkin.agents"``).
        correlation_id: Optional explicit correlation ID.

    Returns:
        A :class:`logging.Logger` with the correlation filter attached.
    """
    if correlation_id is not None:
        correlation_id_var.set(correlation_id)
    elif not correlation_id_var.get():
        correlation_id_var.set(uuid.uuid4().hex[:12])

    logger = logging.getLogger(name)

    # Avoid adding duplicate filters on repeated calls.
    if not any(isinstance(f, CorrelationFilter) for f in logger.filters):
        logger.addFilter(CorrelationFilter())

    return logger
