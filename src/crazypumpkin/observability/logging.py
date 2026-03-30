"""Structured logging with correlation-ID propagation.

Every log record emitted through ``get_logger`` carries a ``correlation_id``
attribute sourced from a :class:`contextvars.ContextVar`.  This allows
tracing a single request / task execution across nested calls without
passing the ID explicitly.

Use :func:`start_pipeline_run` at the beginning of a pipeline to generate a
unique correlation ID that is automatically shared by all downstream loggers.
Use :func:`agent_call_context` when one agent invokes another to propagate
the current correlation ID into the child context while keeping it isolated.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

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


def start_pipeline_run(correlation_id: str | None = None) -> str:
    """Begin a new pipeline run by setting a unique correlation ID.

    This should be called once at the top of a pipeline execution.  All
    loggers obtained via :func:`get_logger` within the same context will
    automatically include the generated correlation ID.

    Args:
        correlation_id: Optional explicit ID.  When *None* a new UUID-4
            based identifier is generated.

    Returns:
        The correlation ID that was set.
    """
    cid = correlation_id if correlation_id is not None else uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


@contextmanager
def agent_call_context() -> Generator[str, None, None]:
    """Context manager that propagates the correlation ID into a child call.

    Use this when one agent calls another to ensure the callee inherits the
    caller's correlation ID.  Any changes the callee makes to the correlation
    ID are rolled back when the context manager exits, keeping the caller's
    value intact.

    Yields:
        The correlation ID inherited from the parent context.

    Example::

        with agent_call_context() as cid:
            child_agent.execute(task, context)
    """
    parent_cid = correlation_id_var.get()
    try:
        yield parent_cid
    finally:
        # Restore parent's correlation ID so child mutations don't leak.
        correlation_id_var.set(parent_cid)


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
