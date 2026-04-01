"""Tests for LLM fallback chain with mocked providers."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.llm.registry import (
    AllProvidersExhaustedError,
    FallbackChain,
    RetryPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_provider(side_effect=None, return_value="ok"):
    """Create a MagicMock that behaves like an LLMProvider."""
    provider = MagicMock()
    if side_effect is not None:
        provider.call.side_effect = side_effect
    else:
        provider.call.return_value = return_value
    return provider


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_retry_policy_delay_calculation():
    """Verify delay_for_attempt returns correct exponential values and caps at max_delay."""
    policy = RetryPolicy(max_retries=5, base_delay=1.0, max_delay=30.0)
    assert policy.delay_for_attempt(0) == 1.0   # 1 * 2^0
    assert policy.delay_for_attempt(1) == 2.0   # 1 * 2^1
    assert policy.delay_for_attempt(2) == 4.0   # 1 * 2^2
    assert policy.delay_for_attempt(3) == 8.0   # 1 * 2^3
    assert policy.delay_for_attempt(4) == 16.0  # 1 * 2^4

    # Caps at max_delay
    capped = RetryPolicy(max_retries=10, base_delay=1.0, max_delay=10.0)
    assert capped.delay_for_attempt(4) == 10.0  # 16 capped to 10
    assert capped.delay_for_attempt(5) == 10.0  # 32 capped to 10


def test_fallback_chain_first_provider_succeeds():
    """Mock first provider succeeding, assert second provider never called."""
    p1 = _make_mock_provider(return_value="from-p1")
    p2 = _make_mock_provider(return_value="from-p2")
    chain = FallbackChain([p1, p2], RetryPolicy(max_retries=3))

    with patch("crazypumpkin.llm.registry.asyncio.sleep", new_callable=AsyncMock):
        result = _run(chain.call("hello"))

    assert result == "from-p1"
    p1.call.assert_called_once_with("hello")
    p2.call.assert_not_called()


def test_fallback_chain_rotates_on_failure():
    """Mock first provider raising Exception on all retries, second succeeding."""
    p1 = _make_mock_provider(side_effect=Exception("p1 down"))
    p2 = _make_mock_provider(return_value="from-p2")
    policy = RetryPolicy(max_retries=2, base_delay=1.0, max_delay=5.0)
    chain = FallbackChain([p1, p2], policy)

    with patch("crazypumpkin.llm.registry.asyncio.sleep", new_callable=AsyncMock):
        result = _run(chain.call("hello"))

    assert result == "from-p2"
    assert p1.call.call_count == 2  # exhausted retries
    assert p2.call.call_count == 1


def test_fallback_chain_all_exhausted():
    """Mock all providers failing, assert AllProvidersExhaustedError raised."""
    p1 = _make_mock_provider(side_effect=Exception("p1 down"))
    p2 = _make_mock_provider(side_effect=Exception("p2 down"))
    policy = RetryPolicy(max_retries=2, base_delay=0.1, max_delay=1.0)
    chain = FallbackChain([p1, p2], policy)

    with patch("crazypumpkin.llm.registry.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AllProvidersExhaustedError):
            _run(chain.call("hello"))


def test_fallback_chain_retry_count():
    """Mock provider failing twice then succeeding on third attempt, assert exactly 3 calls."""
    provider = _make_mock_provider(
        side_effect=[Exception("fail1"), Exception("fail2"), "success"]
    )
    policy = RetryPolicy(max_retries=3, base_delay=1.0, max_delay=10.0)
    chain = FallbackChain([provider], policy)

    with patch("crazypumpkin.llm.registry.asyncio.sleep", new_callable=AsyncMock):
        result = _run(chain.call("hello"))

    assert result == "success"
    assert provider.call.call_count == 3
