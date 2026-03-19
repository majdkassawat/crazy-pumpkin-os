"""Tests for LLM providers and ProviderRegistry routing."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.llm.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# MockLLMProvider — deterministic, no network calls
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """A mock LLM provider that returns canned responses."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.last_prompt: str | None = None

    def call(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
    ) -> str:
        self.last_prompt = prompt
        return f"mock-response:{prompt}"

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        self.last_prompt = prompt
        return {"mock": True, "prompt": prompt}


# ---------------------------------------------------------------------------
# MockLLMProvider tests
# ---------------------------------------------------------------------------


class TestMockLLMProvider:
    def test_implements_llm_provider(self):
        provider = MockLLMProvider()
        assert isinstance(provider, LLMProvider)

    def test_call_returns_str(self):
        provider = MockLLMProvider()
        result = provider.call("hello")
        assert isinstance(result, str)
        assert result == "mock-response:hello"

    def test_call_json_returns_dict(self):
        provider = MockLLMProvider()
        result = provider.call_json("hello")
        assert isinstance(result, dict)
        assert result == {"mock": True, "prompt": "hello"}

    def test_call_accepts_keyword_args(self):
        provider = MockLLMProvider()
        result = provider.call("hi", model="test-model", timeout=5.0, cwd="/tmp")
        assert isinstance(result, str)

    def test_call_json_accepts_keyword_args(self):
        provider = MockLLMProvider()
        result = provider.call_json("hi", model="test-model")
        assert isinstance(result, (dict, list))


# ---------------------------------------------------------------------------
# ProviderRegistry tests (using patched PROVIDER_CLASSES)
# ---------------------------------------------------------------------------


def _make_registry(agent_models: dict | None = None) -> ProviderRegistry:
    """Build a ProviderRegistry backed by MockLLMProviders."""
    config = {
        "default_provider": "mock_a",
        "providers": {
            "mock_a": {"label": "A"},
            "mock_b": {"label": "B"},
        },
        "agent_models": agent_models or {},
    }
    patched_classes = {
        "mock_a": MockLLMProvider,
        "mock_b": MockLLMProvider,
    }
    with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES", patched_classes):
        return ProviderRegistry(config)


class TestProviderRegistryRouting:
    def test_routes_to_agent_specific_provider(self):
        registry = _make_registry(
            {"developer": {"provider": "mock_b", "model": "opus"}}
        )
        provider, model = registry.get_provider("developer")
        assert isinstance(provider, MockLLMProvider)
        assert provider.config == {"label": "B"}
        assert model == "opus"

    def test_falls_back_to_default_provider(self):
        registry = _make_registry(
            {"developer": {"provider": "mock_b", "model": "opus"}}
        )
        provider, model = registry.get_provider("unknown_agent")
        assert isinstance(provider, MockLLMProvider)
        assert provider.config == {"label": "A"}
        assert model is None

    def test_falls_back_when_agent_is_none(self):
        registry = _make_registry()
        provider, model = registry.get_provider(None)
        assert provider.config == {"label": "A"}
        assert model is None

    def test_call_dispatches_to_correct_provider(self):
        registry = _make_registry(
            {"strategist": {"provider": "mock_b", "model": "sonnet"}}
        )
        result = registry.call("test prompt", agent="strategist")
        assert isinstance(result, str)
        assert "test prompt" in result

    def test_call_json_dispatches_to_correct_provider(self):
        registry = _make_registry(
            {"strategist": {"provider": "mock_b", "model": "sonnet"}}
        )
        result = registry.call_json("test prompt", agent="strategist")
        assert isinstance(result, dict)
        assert result["prompt"] == "test prompt"

    def test_call_falls_back_to_default(self):
        registry = _make_registry()
        result = registry.call("fallback prompt")
        assert isinstance(result, str)
        assert "fallback prompt" in result

    def test_raises_for_missing_provider(self):
        config = {
            "default_provider": "nonexistent",
            "providers": {},
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES", {}):
            reg = ProviderRegistry(config)
        with pytest.raises(KeyError, match="nonexistent"):
            reg.get_provider()
