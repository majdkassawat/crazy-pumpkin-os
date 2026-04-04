"""Retry decorator and backoff logic for async operations."""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, Type


@dataclass
class RetryPolicy:
    """Configuration for retry behaviour."""

    max_attempts: int = 3
    base_delay: float = 1.0
    factor: float = 2.0
    max_delay: float = 60.0
    retryable_exceptions: Sequence[Type[BaseException]] = field(
        default_factory=lambda: [TimeoutError, ConnectionError, OSError]
    )


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    """Call *fn* with retry/backoff governed by *policy*."""
    if policy is None:
        policy = RetryPolicy()

    last_exc: BaseException | None = None
    delay = policy.base_delay

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except tuple(policy.retryable_exceptions) as exc:
            last_exc = exc
            if attempt == policy.max_attempts:
                raise
            await asyncio.sleep(min(delay, policy.max_delay))
            delay *= policy.factor
        except BaseException:
            raise

    # Should not be reached, but satisfy type checkers.
    raise last_exc  # type: ignore[misc]


def with_retry(policy: RetryPolicy | None = None) -> Callable:
    """Decorator that wraps an async function with retry logic."""
    if policy is None:
        policy = RetryPolicy()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(fn, *args, policy=policy, **kwargs)
        return wrapper

    return decorator
