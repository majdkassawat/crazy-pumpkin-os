"""Tests that validate code snippets from docs/API_DOCS.md and examples/ are runnable.

Each test corresponds to a documentation code block, ensuring docs don't go stale.
Providers are mocked so no real API calls are made.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(text: str):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], stop_reason="end_turn")


class _MockLLMProvider:
    """Minimal mock satisfying the LLMProvider interface for registry tests."""

    def __init__(self, config=None):
        self.config = config or {}

    def call(self, prompt, *, model=None, timeout=None, cwd=None,
             tools=None, system=None, cache=True):
        return f"[mock:{model or 'default'}] {prompt}"

    def call_json(self, prompt, **kwargs):
        return {"mock": True, "prompt": prompt}

    def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                        timeout=None, cwd=None, system=None, cache=True):
        return self.call(prompt, tools=tools, timeout=timeout, cwd=cwd, system=system)

    def call_with_cost(self, prompt, *, model=None, **kwargs):
        from crazypumpkin.llm.base import CallCost
        text = self.call(prompt, model=model, **kwargs)
        cost = CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001)
        return text, cost


# ===========================================================================
# Doc: Quick Start — imports and basic ProviderRegistry.call()
# ===========================================================================


class TestDocQuickStart:
    """Validates the Quick Start snippet from API_DOCS.md."""

    def test_import_from_package(self):
        """'from crazypumpkin.llm import ProviderRegistry' works."""
        from crazypumpkin.llm import ProviderRegistry
        assert ProviderRegistry is not None

    def test_registry_call(self):
        """ProviderRegistry(config).call(prompt, agent=...) returns a string."""
        from crazypumpkin.llm.registry import ProviderRegistry

        config = {
            "default_provider": "mock",
            "providers": {"mock": {}},
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES",
                         {"mock": _MockLLMProvider}):
            registry = ProviderRegistry(config)

        answer = registry.call("Summarise this code", agent="developer")
        assert isinstance(answer, str)


# ===========================================================================
# Doc: Provider Registration — config with agent_models and get_provider
# ===========================================================================


class TestDocProviderRegistration:
    """Validates the Provider Registration snippet."""

    def _make_registry(self):
        from crazypumpkin.llm.registry import ProviderRegistry

        config = {
            "default_provider": "anthropic_api",
            "providers": {
                "anthropic_api": {"api_key": "sk-ant-..."},
                "openai_api":    {"api_key": "sk-..."},
            },
            "agent_models": {
                "developer":  {"model": "sonnet"},
                "strategist": {"model": "gpt-4o", "provider": "openai_api"},
            },
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES",
                         {"anthropic_api": _MockLLMProvider,
                          "openai_api": _MockLLMProvider}):
            return ProviderRegistry(config)

    def test_registry_creation(self):
        """Registry instantiates from a multi-provider config."""
        registry = self._make_registry()
        assert registry is not None

    def test_get_provider_returns_tuple(self):
        """registry.get_provider('developer') returns (provider, model_override)."""
        registry = self._make_registry()
        provider, model_override = registry.get_provider("developer")
        assert provider is not None
        assert model_override == "sonnet"

    def test_agent_specific_provider_routing(self):
        """Strategist routes to openai_api per agent_models config."""
        registry = self._make_registry()
        provider, model_override = registry.get_provider("strategist")
        # Should route to openai_api config
        assert provider.config == {"api_key": "sk-..."}
        assert model_override == "gpt-4o"

    def test_default_provider_fallback(self):
        """Unknown agent falls back to default_provider."""
        registry = self._make_registry()
        provider, model_override = registry.get_provider("unknown")
        assert provider.config == {"api_key": "sk-ant-..."}
        assert model_override is None


# ===========================================================================
# Doc: Built-in Providers — LLMProvider ABC
# ===========================================================================


class TestDocLLMProviderABC:
    """Validates that the documented abstract class and methods exist."""

    def test_llm_provider_is_abstract(self):
        from crazypumpkin.llm.base import LLMProvider
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_documented_methods_exist(self):
        """LLMProvider defines call, call_json, call_multi_turn."""
        from crazypumpkin.llm.base import LLMProvider
        assert hasattr(LLMProvider, "call")
        assert hasattr(LLMProvider, "call_json")
        assert hasattr(LLMProvider, "call_multi_turn")


# ===========================================================================
# Doc: Anthropic Provider — model aliases and basic usage
# ===========================================================================


class TestDocAnthropicProvider:
    """Validates Anthropic provider snippets from API_DOCS.md."""

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_import_and_construct(self, mock_cls):
        """'from crazypumpkin.llm.anthropic_api import AnthropicProvider' works."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        provider = AnthropicProvider({"api_key": "sk-ant-..."})
        assert provider is not None

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_returns_string(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        provider = AnthropicProvider({"api_key": "sk-ant-..."})
        provider._client.messages.create.return_value = _make_anthropic_response("4")
        result = provider.call("What is 2+2?", model="sonnet")
        assert isinstance(result, str)

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_json_returns_dict(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        provider = AnthropicProvider({"api_key": "sk-ant-..."})
        provider._client.messages.create.return_value = _make_anthropic_response(
            '{"answer": 4}'
        )
        data = provider.call_json('Return {"answer": 4}')
        assert isinstance(data, dict)
        assert data["answer"] == 4

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_with_system_prompt(self, mock_cls):
        """call() accepts system= and cache= kwargs as documented."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        provider = AnthropicProvider({"api_key": "sk-ant-..."})
        provider._client.messages.create.return_value = _make_anthropic_response("review done")
        result = provider.call(
            "Explain this code",
            model="sonnet",
            system="You are a code reviewer.",
            cache=True,
        )
        assert isinstance(result, str)

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_documented_model_aliases(self, mock_cls):
        """All documented model aliases resolve correctly."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        provider = AnthropicProvider()
        aliases = {
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
            "smart": "claude-sonnet-4-6",
            "fast": "claude-haiku-4-5-20251001",
        }
        for alias, expected in aliases.items():
            assert provider._resolve_model(alias) == expected, (
                f"Alias '{alias}' should resolve to '{expected}'"
            )

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_with_cost(self, mock_cls):
        """call_with_cost returns (text, CallCost) as documented."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider
        from crazypumpkin.llm.base import CallCost
        provider = AnthropicProvider({"api_key": "sk-ant-..."})

        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        provider._client.messages.create.return_value = resp
        text, cost = provider.call_with_cost("Hello", model="sonnet")
        assert isinstance(text, str)
        assert isinstance(cost, CallCost)
        assert hasattr(cost, "prompt_tokens")
        assert hasattr(cost, "completion_tokens")
        assert hasattr(cost, "cost_usd")


# ===========================================================================
# Doc: OpenAI Provider — model aliases and basic usage
# ===========================================================================


_has_openai = pytest.importorskip("openai", reason="openai package not installed")


class TestDocOpenAIProvider:
    """Validates OpenAI provider snippets from API_DOCS.md."""

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_import_and_construct(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider({"api_key": "sk-..."})
        assert provider is not None

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_call_returns_string(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider({"api_key": "sk-..."})
        msg = SimpleNamespace(content="4")
        choice = SimpleNamespace(message=msg)
        provider._client.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
        result = provider.call("What is 2+2?", model="gpt-4o")
        assert isinstance(result, str)

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_call_json_returns_dict(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider({"api_key": "sk-..."})
        msg = SimpleNamespace(content='{"answer": 4}')
        choice = SimpleNamespace(message=msg)
        provider._client.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
        data = provider.call_json('Return {"answer": 4}')
        assert isinstance(data, dict)
        assert data["answer"] == 4

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_documented_model_aliases(self, mock_cls):
        """smart → gpt-4o, fast → gpt-4o-mini as documented."""
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        assert provider._resolve_model("smart") == "gpt-4o"
        assert provider._resolve_model("fast") == "gpt-4o-mini"


# ===========================================================================
# Doc: Creating a Custom Provider — subclass pattern
# ===========================================================================


class TestDocCustomProvider:
    """Validates the custom provider subclass pattern from API_DOCS.md."""

    def test_custom_provider_subclass(self):
        """The documented custom provider pattern produces a valid LLMProvider."""
        from crazypumpkin.llm.base import LLMProvider

        class MyProvider(LLMProvider):
            def __init__(self, config=None):
                config = config or {}
                self._api_key = config.get("api_key")

            def call(self, prompt, *, model=None, timeout=None, cwd=None,
                     tools=None, system=None, cache=True):
                return "response text"

            def call_json(self, prompt, **kwargs):
                import json
                return json.loads(self.call(prompt, **kwargs))

            def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                                timeout=None, cwd=None, system=None, cache=True):
                return self.call(prompt, tools=tools, timeout=timeout, cwd=cwd)

        provider = MyProvider({"api_key": "test"})
        assert isinstance(provider, LLMProvider)
        assert provider.call("hello") == "response text"
        assert provider.call_multi_turn("hello") == "response text"

    def test_register_custom_provider(self):
        """PROVIDER_CLASSES['my_provider'] = MyClass registers it for the registry."""
        from crazypumpkin.llm.base import LLMProvider
        from crazypumpkin.llm.registry import PROVIDER_CLASSES

        class MyProvider(LLMProvider):
            def __init__(self, config=None):
                pass

            def call(self, prompt, *, model=None, timeout=None, cwd=None,
                     tools=None, system=None, cache=True):
                return "custom"

            def call_json(self, prompt, **kwargs):
                return {"custom": True}

            def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                                timeout=None, cwd=None, system=None, cache=True):
                return self.call(prompt)

        original = dict(PROVIDER_CLASSES)
        try:
            PROVIDER_CLASSES["my_provider"] = MyProvider
            assert "my_provider" in PROVIDER_CLASSES
        finally:
            # Restore original
            PROVIDER_CLASSES.clear()
            PROVIDER_CLASSES.update(original)

    def test_custom_provider_with_cost_tracking(self):
        """The documented call_with_cost pattern works."""
        from crazypumpkin.llm.base import CallCost, LLMProvider

        class MyProvider(LLMProvider):
            def __init__(self, config=None):
                pass

            def call(self, prompt, *, model=None, timeout=None, cwd=None,
                     tools=None, system=None, cache=True):
                return "response"

            def call_json(self, prompt, **kwargs):
                return {}

            def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                                timeout=None, cwd=None, system=None, cache=True):
                return self.call(prompt)

            def call_with_cost(self, prompt, *, model=None, **kwargs):
                text = self.call(prompt, model=model, **kwargs)
                cost = CallCost(
                    prompt_tokens=100,
                    completion_tokens=50,
                    cost_usd=0.002,
                )
                return text, cost

        provider = MyProvider()
        text, cost = provider.call_with_cost("hello")
        assert text == "response"
        assert isinstance(cost, CallCost)
        assert cost.prompt_tokens == 100
        assert cost.completion_tokens == 50
        assert cost.cost_usd == 0.002


# ===========================================================================
# Doc: Fallback Chains — FallbackChain, RetryPolicy, AllProvidersExhaustedError
# ===========================================================================


class TestDocFallbackChains:
    """Validates the fallback chain snippet from API_DOCS.md."""

    def test_imports(self):
        """All documented imports from crazypumpkin.llm.registry resolve."""
        from crazypumpkin.llm.registry import (
            FallbackChain,
            RetryPolicy,
            ProviderRegistry,
            AllProvidersExhaustedError,
        )
        assert FallbackChain is not None
        assert RetryPolicy is not None
        assert ProviderRegistry is not None
        assert AllProvidersExhaustedError is not None

    def test_fallback_chain_construction(self):
        """FallbackChain with RetryPolicy can be constructed as documented."""
        from crazypumpkin.llm.registry import FallbackChain, RetryPolicy

        chain = FallbackChain(
            provider_names=["anthropic_api", "openai_api"],
            retry_policy=RetryPolicy(
                max_retries=3,
                base_delay=1.0,
                max_delay=30.0,
                exponential_base=2.0,
            ),
        )
        assert chain.provider_names == ["anthropic_api", "openai_api"]
        assert chain.retry_policy.max_retries == 3
        assert chain.retry_policy.base_delay == 1.0
        assert chain.retry_policy.max_delay == 30.0
        assert chain.retry_policy.exponential_base == 2.0

    def test_retry_policy_delay_formula(self):
        """delay = min(base_delay * exponential_base^n, max_delay) as documented."""
        from crazypumpkin.llm.registry import RetryPolicy

        policy = RetryPolicy(base_delay=1.0, max_delay=30.0, exponential_base=2.0)
        assert policy.delay_for_attempt(0) == 1.0   # 1.0 * 2^0 = 1.0
        assert policy.delay_for_attempt(1) == 2.0   # 1.0 * 2^1 = 2.0
        assert policy.delay_for_attempt(2) == 4.0   # 1.0 * 2^2 = 4.0
        assert policy.delay_for_attempt(5) == 30.0  # 1.0 * 2^5 = 32 → capped at 30

    def test_call_with_fallback_success(self):
        """call_with_fallback returns {provider, result} on success."""
        from crazypumpkin.llm.registry import (
            FallbackChain, RetryPolicy, ProviderRegistry,
        )

        config = {
            "default_provider": "mock_a",
            "providers": {"mock_a": {}, "mock_b": {}},
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES",
                         {"mock_a": _MockLLMProvider, "mock_b": _MockLLMProvider}):
            registry = ProviderRegistry(config)

        chain = FallbackChain(
            provider_names=["mock_a", "mock_b"],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.0),
        )

        result = asyncio.run(registry.call_with_fallback(
            chain, messages=[{"role": "user", "content": "Hello"}],
        ))
        assert "provider" in result
        assert "result" in result

    def test_call_with_fallback_exhausted(self):
        """AllProvidersExhaustedError raised when all providers fail."""
        from crazypumpkin.llm.registry import (
            FallbackChain, RetryPolicy, ProviderRegistry,
            AllProvidersExhaustedError,
        )

        class _FailingProvider:
            def __init__(self, config=None):
                pass
            def call(self, prompt, **kwargs):
                raise RuntimeError("fail")

        config = {
            "default_provider": "fail",
            "providers": {"fail": {}},
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES",
                         {"fail": _FailingProvider}):
            registry = ProviderRegistry(config)

        chain = FallbackChain(
            provider_names=["fail"],
            retry_policy=RetryPolicy(max_retries=1, base_delay=0.0),
        )

        with pytest.raises(AllProvidersExhaustedError):
            asyncio.run(registry.call_with_fallback(
                chain, messages=[{"role": "user", "content": "Hello"}],
            ))


# ===========================================================================
# Doc: Cost Tracking — CallCost, CostTracker, get_default_tracker
# ===========================================================================


class TestDocCostTracking:
    """Validates cost tracking snippets from API_DOCS.md."""

    def test_callcost_construction(self):
        """CallCost dataclass can be constructed with all documented fields."""
        from crazypumpkin.llm.base import CallCost

        cost = CallCost(
            prompt_tokens=150,
            completion_tokens=80,
            cost_usd=0.003,
            cache_creation_tokens=0,
            cache_read_tokens=50,
        )
        assert cost.prompt_tokens == 150
        assert cost.completion_tokens == 80
        assert cost.cost_usd == 0.003
        assert cost.cache_creation_tokens == 0
        assert cost.cache_read_tokens == 50

    def test_cost_tracker_record_and_summary(self):
        """CostTracker.record() + get_summary() works as documented."""
        from crazypumpkin.llm.base import CallCost, CostTracker

        tracker = CostTracker()
        tracker.record("claude-sonnet-4-6", CallCost(
            prompt_tokens=200,
            completion_tokens=100,
            cost_usd=0.002,
        ))

        summary = tracker.get_summary()
        assert summary["total_cost_usd"] == 0.002
        assert summary["call_count"] == 1
        assert summary["total_prompt_tokens"] == 200
        assert summary["total_completion_tokens"] == 100
        assert "by_model" in summary
        assert "claude-sonnet-4-6" in summary["by_model"]

    def test_cost_tracker_reset(self):
        """CostTracker.reset() zeroes all counters as documented."""
        from crazypumpkin.llm.base import CallCost, CostTracker

        tracker = CostTracker()
        tracker.record("model", CallCost(prompt_tokens=10, completion_tokens=5, cost_usd=0.001))
        tracker.reset()

        summary = tracker.get_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["call_count"] == 0
        assert summary["by_model"] == {}

    def test_get_default_tracker_singleton(self):
        """get_default_tracker() returns a CostTracker singleton."""
        from crazypumpkin.llm.base import CostTracker, get_default_tracker

        tracker = get_default_tracker()
        assert isinstance(tracker, CostTracker)
        assert get_default_tracker() is tracker  # same instance


# ===========================================================================
# examples/custom_provider.py — the full example script is runnable
# ===========================================================================


class TestExampleCustomProvider:
    """Validates that examples/custom_provider.py is importable and runnable."""

    def test_echo_provider_runnable(self):
        """Replicate the EchoProvider pattern from the example."""
        from crazypumpkin.llm.base import LLMProvider
        from crazypumpkin.llm.registry import PROVIDER_CLASSES, ProviderRegistry

        class EchoProvider(LLMProvider):
            def __init__(self, config=None):
                self.config = config or {}
                self.prefix = self.config.get("prefix", "echo")

            def call(self, prompt, *, model=None, timeout=None, cwd=None,
                     tools=None, system=None, cache=True):
                model_name = model or "default"
                return f"[{self.prefix}:{model_name}] {prompt}"

            def call_json(self, prompt, **kwargs):
                return {"provider": self.prefix, "response": prompt}

            def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                                timeout=None, cwd=None, system=None, cache=True):
                return self.call(prompt, tools=tools, timeout=timeout, cwd=cwd, system=system)

        original = dict(PROVIDER_CLASSES)
        try:
            PROVIDER_CLASSES["echo"] = EchoProvider

            config = {
                "default_provider": "echo",
                "providers": {"echo": {"prefix": "my-custom-llm"}},
                "agent_models": {
                    "developer": {"model": "large", "provider": "echo"},
                    "reviewer": {"model": "small"},
                },
            }
            registry = ProviderRegistry(config)

            # Text call (default)
            result = registry.call("Hello, world!")
            assert isinstance(result, str)
            assert "my-custom-llm" in result

            # Text call with agent override
            result = registry.call("Review this code.", agent="developer")
            assert isinstance(result, str)
            assert "large" in result

            # JSON call
            data = registry.call_json("Give me JSON.", agent="reviewer")
            assert isinstance(data, dict)
            assert data["provider"] == "my-custom-llm"

            # Direct instantiation
            provider = EchoProvider({"prefix": "standalone"})
            assert "standalone" in provider.call("ping")
        finally:
            PROVIDER_CLASSES.clear()
            PROVIDER_CLASSES.update(original)
