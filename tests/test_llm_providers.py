"""Tests for LLM providers and ProviderRegistry routing."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
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

    def test_call_json_forwards_model_override(self):
        """call_json injects model='opus' into kwargs when the agent override specifies it."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "opus"}}
        )
        # Wrap the underlying provider's call_json with a MagicMock so we can
        # inspect the exact arguments the registry dispatches.
        provider, _ = registry.get_provider("developer")
        provider.call_json = mock.MagicMock(return_value={"forwarded": True})

        result = registry.call_json("test prompt", agent="developer")

        # The registry must inject model='opus' from the agent config.
        provider.call_json.assert_called_once_with("test prompt", model="opus")
        assert isinstance(result, dict)
        assert result == {"forwarded": True}

    def test_call_json_omits_model_when_no_override(self):
        """call_json does NOT pass a model kwarg when the agent has no override."""
        registry = _make_registry()
        provider, _ = registry.get_provider(None)
        provider.call_json = mock.MagicMock(return_value={"no_model": True})

        result = registry.call_json("test prompt")

        # No agent model configured → model kwarg must be absent.
        provider.call_json.assert_called_once_with("test prompt")
        call_kwargs = provider.call_json.call_args.kwargs
        assert "model" not in call_kwargs
        assert isinstance(result, dict)
        assert result == {"no_model": True}

    def test_raises_for_missing_provider(self):
        config = {
            "default_provider": "nonexistent",
            "providers": {},
        }
        with mock.patch("crazypumpkin.llm.registry.PROVIDER_CLASSES", {}):
            reg = ProviderRegistry(config)
        with pytest.raises(KeyError, match="nonexistent"):
            reg.get_provider()


# ---------------------------------------------------------------------------
# AnthropicProvider tests (patched client — no real API calls)
# ---------------------------------------------------------------------------


def _make_anthropic_response(text: str):
    """Build a fake Anthropic messages.create() response."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


@mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
def _build_provider(mock_anthropic_cls, config=None):
    """Create an AnthropicProvider with a mocked Anthropic client."""
    from crazypumpkin.llm.anthropic_api import AnthropicProvider

    provider = AnthropicProvider(config)
    return provider, mock_anthropic_cls


class TestAnthropicProvider:
    """Unit tests for AnthropicProvider with mocked Anthropic client."""

    # -- model alias resolution ------------------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_alias_opus(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        assert provider._resolve_model("opus") == "claude-opus-4-6"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_alias_sonnet(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        assert provider._resolve_model("sonnet") == "claude-sonnet-4-6"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_alias_haiku(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        assert provider._resolve_model("haiku") == "claude-haiku-4-5-20251001"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_unknown_alias_passes_through(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        assert provider._resolve_model("my-custom-model") == "my-custom-model"

    # -- call() ----------------------------------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_passes_tools(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response("ok")

        tools = [{"name": "get_weather", "description": "Get weather"}]
        provider.call("hello", tools=tools)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
        passed_tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
        assert passed_tools is tools

    # -- call_json() -----------------------------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_json_returns_parsed_dict(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        payload = {"result": 42, "status": "ok"}
        mock_create.return_value = _make_anthropic_response(json.dumps(payload))

        result = provider.call_json("give me json")

        assert isinstance(result, dict)
        assert result == payload


# ---------------------------------------------------------------------------
# OpenAIProvider tests (patched client — no real API calls)
# ---------------------------------------------------------------------------


def _make_openai_response(text: str):
    """Build a fake OpenAI chat.completions.create() response."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class TestOpenAIProvider:
    """Unit tests for OpenAIProvider with mocked OpenAI client."""

    # -- helper import ---------------------------------------------------------

    @staticmethod
    def _tool_converter():
        from crazypumpkin.llm.openai_api import _anthropic_tool_to_openai
        return _anthropic_tool_to_openai

    # -- model alias resolution ------------------------------------------------

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_alias_smart(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        assert provider._resolve_model("smart") == "gpt-4o"

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_alias_fast(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        assert provider._resolve_model("fast") == "gpt-4o-mini"

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_unknown_alias_passes_through(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        assert provider._resolve_model("my-custom-model") == "my-custom-model"

    # -- _anthropic_tool_to_openai ---------------------------------------------

    def test_anthropic_tool_to_openai_shape(self):
        convert = self._tool_converter()
        tool = {
            "name": "get_weather",
            "description": "Get the weather",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
        }
        result = convert(tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "get_weather"
        assert result["function"]["description"] == "Get the weather"
        assert result["function"]["parameters"] == tool["input_schema"]

    def test_anthropic_tool_to_openai_missing_optional_fields(self):
        convert = self._tool_converter()
        tool = {"name": "bare_tool"}
        result = convert(tool)
        assert result == {
            "type": "function",
            "function": {"name": "bare_tool", "description": "", "parameters": {}},
        }

    # -- call() ----------------------------------------------------------------

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_call_passes_converted_tools(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        mock_create = provider._client.chat.completions.create
        mock_create.return_value = _make_openai_response("ok")

        tools = [
            {"name": "get_weather", "description": "Weather", "input_schema": {"type": "object"}},
        ]
        provider.call("hello", tools=tools)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs if mock_create.call_args.kwargs else mock_create.call_args[1]
        passed_tools = call_kwargs.get("tools")
        assert passed_tools is not None
        assert len(passed_tools) == 1
        assert passed_tools[0]["type"] == "function"
        assert passed_tools[0]["function"]["name"] == "get_weather"

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_call_without_tools(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        mock_create = provider._client.chat.completions.create
        mock_create.return_value = _make_openai_response("response")

        result = provider.call("hi")

        assert result == "response"
        call_kwargs = mock_create.call_args.kwargs if mock_create.call_args.kwargs else mock_create.call_args[1]
        assert "tools" not in call_kwargs

    # -- call_json() -----------------------------------------------------------

    @mock.patch("crazypumpkin.llm.openai_api.OpenAI")
    def test_call_json_requests_json_format(self, mock_cls):
        from crazypumpkin.llm.openai_api import OpenAIProvider
        provider = OpenAIProvider()
        mock_create = provider._client.chat.completions.create
        mock_create.return_value = _make_openai_response('{"key": "value"}')

        result = provider.call_json("give me json")

        assert result == {"key": "value"}
        call_kwargs = mock_create.call_args.kwargs if mock_create.call_args.kwargs else mock_create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}
