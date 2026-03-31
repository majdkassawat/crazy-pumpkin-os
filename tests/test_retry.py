"""Tests for retry decorator and backoff logic."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.retry import RetryPolicy, retry_async, with_retry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_retry_succeeds_first_attempt():
    """Function succeeds on first call — no retry."""
    fn = AsyncMock(return_value="ok")
    policy = RetryPolicy(max_attempts=3)

    result = asyncio.run(retry_async(fn, policy=policy))

    assert result == "ok"
    assert fn.call_count == 1


def test_retry_succeeds_after_transient_failure():
    """Mock raises TimeoutError twice then succeeds; called 3 times."""
    fn = AsyncMock(side_effect=[TimeoutError, TimeoutError, "ok"])
    policy = RetryPolicy(max_attempts=3, base_delay=0)

    async def _run():
        with patch("crazypumpkin.framework.retry.asyncio.sleep", new_callable=AsyncMock):
            return await retry_async(fn, policy=policy)

    result = asyncio.run(_run())

    assert result == "ok"
    assert fn.call_count == 3


def test_retry_exhausted_raises():
    """Mock always raises TimeoutError with max_attempts=2; raises after 2."""
    fn = AsyncMock(side_effect=TimeoutError)
    policy = RetryPolicy(max_attempts=2, base_delay=0)

    async def _run():
        with patch("crazypumpkin.framework.retry.asyncio.sleep", new_callable=AsyncMock):
            await retry_async(fn, policy=policy)

    with pytest.raises(TimeoutError):
        asyncio.run(_run())

    assert fn.call_count == 2


def test_non_retryable_exception_propagates():
    """ValueError is not retryable — raises immediately, called once."""
    fn = AsyncMock(side_effect=ValueError("bad"))
    policy = RetryPolicy(max_attempts=3)

    with pytest.raises(ValueError, match="bad"):
        asyncio.run(retry_async(fn, policy=policy))

    assert fn.call_count == 1


def test_backoff_delays():
    """Verify delays are 1.0, 2.0 for base_delay=1, factor=2."""
    fn = AsyncMock(side_effect=[TimeoutError, TimeoutError, "ok"])
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, factor=2.0, max_delay=60.0)

    async def _run():
        with patch("crazypumpkin.framework.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await retry_async(fn, policy=policy)
            return result, mock_sleep

    result, mock_sleep = asyncio.run(_run())

    assert result == "ok"
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0].args[0] == 1.0
    assert mock_sleep.call_args_list[1].args[0] == 2.0


def test_max_delay_cap():
    """With max_delay=3, sleep never exceeds 3."""
    fn = AsyncMock(side_effect=[TimeoutError, TimeoutError, TimeoutError, "ok"])
    policy = RetryPolicy(max_attempts=4, base_delay=2.0, factor=2.0, max_delay=3.0)

    async def _run():
        with patch("crazypumpkin.framework.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await retry_async(fn, policy=policy)
            return result, mock_sleep

    result, mock_sleep = asyncio.run(_run())

    assert result == "ok"
    for call in mock_sleep.call_args_list:
        assert call.args[0] <= 3.0


def test_with_retry_decorator():
    """Decorate an async fn, verify retry behavior."""
    call_count = 0

    @with_retry(policy=RetryPolicy(max_attempts=3, base_delay=0))
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError
        return "done"

    async def _run():
        with patch("crazypumpkin.framework.retry.asyncio.sleep", new_callable=AsyncMock):
            return await flaky()

    result = asyncio.run(_run())

    assert result == "done"
    assert call_count == 3
