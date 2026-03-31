"""Tests for RetryPolicy, FallbackChain, and call_with_fallback."""

import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.llm.registry import (
    AllProvidersExhaustedError,
    FallbackChain,
    ProviderRegistry,
    RetryPolicy,
)


# ---------------------------------------------------------------------------
# RetryPolicy tests
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_default_values(self):
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 30.0
        assert policy.exponential_base == 2.0

    def test_delay_for_attempt_zero_returns_base_delay(self):
        policy = RetryPolicy(base_delay=1.0)
        assert policy.delay_for_attempt(0) == 1.0

    def test_delay_for_attempt_exponential(self):
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        assert policy.delay_for_attempt(0) == 1.0
        assert policy.delay_for_attempt(1) == 2.0
        assert policy.delay_for_attempt(2) == 4.0

    def test_delay_for_attempt_capped_at_max_delay(self):
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0, max_delay=5.0)
        # attempt 3 -> 1.0 * 2^3 = 8.0, but capped at 5.0
        assert policy.delay_for_attempt(3) == 5.0

    def test_delay_for_attempt_3_does_not_exceed_max_delay(self):
        policy = RetryPolicy()
        delay = policy.delay_for_attempt(3)
        assert delay <= policy.max_delay

    def test_custom_base_delay(self):
        policy = RetryPolicy(base_delay=0.5)
        assert policy.delay_for_attempt(0) == 0.5


# ---------------------------------------------------------------------------
# FallbackChain tests
# ---------------------------------------------------------------------------


class TestFallbackChain:
    def test_default_empty_providers(self):
        chain = FallbackChain()
        assert chain.provider_names == []
        assert isinstance(chain.retry_policy, RetryPolicy)

    def test_stores_ordered_provider_names(self):
        chain = FallbackChain(provider_names=["anthropic", "openai", "local"])
        assert chain.provider_names == ["anthropic", "openai", "local"]

    def test_stores_custom_retry_policy(self):
        policy = RetryPolicy(max_retries=5, base_delay=0.1)
        chain = FallbackChain(provider_names=["a", "b"], retry_policy=policy)
        assert chain.retry_policy.max_retries == 5
        assert chain.retry_policy.base_delay == 0.1

    def test_default_retry_policy(self):
        chain = FallbackChain(provider_names=["a"])
        assert chain.retry_policy.max_retries == 3


# ---------------------------------------------------------------------------
# Mock provider for fallback tests
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    def __init__(self, config=None):
        self.config = config or {}
        self.call_count = 0
        self.should_fail = False
        self.fail_error = RuntimeError("provider error")

    def call(self, prompt, *, model=None, timeout=None, cwd=None, tools=None, **kwargs):
        self.call_count += 1
        if self.should_fail:
            raise self.fail_error
        return f"response:{prompt}"

    def call_json(self, prompt, **kwargs):
        return {"mock": True}

    def call_multi_turn(self, prompt, *, max_turns=10, tools=None, timeout=None, cwd=None):
        return f"multi:{prompt}"


def _make_registry_with_mocks(provider_names, failing=None):
    """Build a ProviderRegistry with mock providers.

    failing: set of provider names that should raise on call().
    """
    failing = failing or set()
    config = {
        "default_provider": provider_names[0],
        "providers": {name: {"label": name} for name in provider_names},
        "agent_models": {},
    }
    mock_classes = {name: MockLLMProvider for name in provider_names}
    with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES", mock_classes):
        registry = ProviderRegistry(config)

    # Mark failing providers
    for name in failing:
        if name in registry._providers:
            registry._providers[name].should_fail = True

    return registry


# ---------------------------------------------------------------------------
# call_with_fallback tests
# ---------------------------------------------------------------------------


class TestCallWithFallback:
    def test_first_provider_succeeds(self):
        registry = _make_registry_with_mocks(["primary", "secondary"])
        chain = FallbackChain(
            provider_names=["primary", "secondary"],
            retry_policy=RetryPolicy(max_retries=2, base_delay=0.01),
        )
        result = asyncio.new_event_loop().run_until_complete(
            registry.call_with_fallback(chain, [{"content": "hello"}])
        )
        assert result["provider"] == "primary"
        assert "hello" in result["result"]

    def test_falls_back_to_second_provider(self):
        registry = _make_registry_with_mocks(
            ["primary", "secondary"], failing={"primary"}
        )
        chain = FallbackChain(
            provider_names=["primary", "secondary"],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.01),
        )
        result = asyncio.new_event_loop().run_until_complete(
            registry.call_with_fallback(chain, [{"content": "test"}])
        )
        assert result["provider"] == "secondary"

    def test_all_providers_exhausted_raises(self):
        registry = _make_registry_with_mocks(
            ["a", "b"], failing={"a", "b"}
        )
        chain = FallbackChain(
            provider_names=["a", "b"],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.01),
        )
        with pytest.raises(AllProvidersExhaustedError):
            asyncio.new_event_loop().run_until_complete(
                registry.call_with_fallback(chain, [{"content": "fail"}])
            )

    def test_retries_before_falling_back(self):
        registry = _make_registry_with_mocks(
            ["primary", "secondary"], failing={"primary"}
        )
        chain = FallbackChain(
            provider_names=["primary", "secondary"],
            retry_policy=RetryPolicy(max_retries=3, base_delay=0.01),
        )
        asyncio.new_event_loop().run_until_complete(
            registry.call_with_fallback(chain, [{"content": "test"}])
        )
        # primary should have been called max_retries times
        assert registry._providers["primary"].call_count == 3

    def test_skips_unknown_provider(self):
        registry = _make_registry_with_mocks(["real"])
        chain = FallbackChain(
            provider_names=["nonexistent", "real"],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.01),
        )
        result = asyncio.new_event_loop().run_until_complete(
            registry.call_with_fallback(chain, [{"content": "hello"}])
        )
        assert result["provider"] == "real"

    def test_empty_chain_raises(self):
        registry = _make_registry_with_mocks(["a"])
        chain = FallbackChain(
            provider_names=[],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.01),
        )
        with pytest.raises(AllProvidersExhaustedError):
            asyncio.new_event_loop().run_until_complete(
                registry.call_with_fallback(chain, [{"content": "hello"}])
            )

    def test_exponential_backoff_delays(self):
        """asyncio.sleep is called with delays matching RetryPolicy for each attempt."""
        registry = _make_registry_with_mocks(["a"], failing={"a"})
        policy = RetryPolicy(max_retries=3, base_delay=1.0, exponential_base=2.0, max_delay=30.0)
        chain = FallbackChain(provider_names=["a"], retry_policy=policy)

        sleep_delays = []

        async def fake_sleep(delay):
            sleep_delays.append(delay)

        with mock.patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(AllProvidersExhaustedError):
                asyncio.new_event_loop().run_until_complete(
                    registry.call_with_fallback(chain, [{"content": "test"}])
                )
            # Expect delays: attempt 0 -> 1.0, attempt 1 -> 2.0, attempt 2 -> 4.0
            assert sleep_delays == [1.0, 2.0, 4.0]

    def test_logs_provider_name_and_attempt_on_retry(self, caplog):
        """Warning logs include provider name and attempt number."""
        registry = _make_registry_with_mocks(["failing"], failing={"failing"})
        policy = RetryPolicy(max_retries=2, base_delay=0.01)
        chain = FallbackChain(provider_names=["failing"], retry_policy=policy)

        async def fake_sleep(delay):
            pass

        with mock.patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(AllProvidersExhaustedError):
                import logging
                with caplog.at_level(logging.WARNING):
                    asyncio.new_event_loop().run_until_complete(
                        registry.call_with_fallback(chain, [{"content": "x"}])
                    )

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("failing" in m and "attempt 1" in m for m in warning_messages)
        assert any("failing" in m and "attempt 2" in m for m in warning_messages)

    def test_exhausted_error_contains_all_provider_errors(self):
        """AllProvidersExhaustedError message includes errors from every provider."""
        registry = _make_registry_with_mocks(["a", "b"], failing={"a", "b"})
        registry._providers["a"].fail_error = RuntimeError("error-from-a")
        registry._providers["b"].fail_error = RuntimeError("error-from-b")
        policy = RetryPolicy(max_retries=1, base_delay=0.01)
        chain = FallbackChain(provider_names=["a", "b"], retry_policy=policy)

        async def fake_sleep(delay):
            pass

        with mock.patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(AllProvidersExhaustedError, match="error-from-a") as exc_info:
                asyncio.new_event_loop().run_until_complete(
                    registry.call_with_fallback(chain, [{"content": "fail"}])
                )
            assert "error-from-b" in str(exc_info.value)
            assert "a:" in str(exc_info.value)
            assert "b:" in str(exc_info.value)

    def test_first_provider_success_skips_fallback(self):
        """When first provider succeeds, second provider is never called."""
        registry = _make_registry_with_mocks(["primary", "secondary"])
        chain = FallbackChain(
            provider_names=["primary", "secondary"],
            retry_policy=RetryPolicy(max_retries=2, base_delay=0.01),
        )
        result = asyncio.new_event_loop().run_until_complete(
            registry.call_with_fallback(chain, [{"content": "hello"}])
        )
        assert result["provider"] == "primary"
        assert registry._providers["secondary"].call_count == 0
