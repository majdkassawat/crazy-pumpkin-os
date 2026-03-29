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

    def call_multi_turn(
        self,
        prompt: str,
        *,
        max_turns: int = 10,
        tools: list | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> str:
        self.last_prompt = prompt
        return f"mock-multi-turn:{prompt}"


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

    def test_call_multi_turn_returns_str(self):
        """MockLLMProvider.call_multi_turn satisfies the LLMProvider contract."""
        provider = MockLLMProvider()
        result = provider.call_multi_turn("hello")
        assert isinstance(result, str)
        assert result == "mock-multi-turn:hello"

    def test_call_multi_turn_accepts_all_kwargs(self):
        """MockLLMProvider.call_multi_turn accepts every kwarg from the base class."""
        provider = MockLLMProvider()
        tools = [{"name": "Read", "description": "Read"}]
        result = provider.call_multi_turn(
            "prompt",
            max_turns=5,
            tools=tools,
            timeout=30.0,
            cwd="/tmp",
        )
        assert isinstance(result, str)
        assert provider.last_prompt == "prompt"

    def test_call_multi_turn_ignores_max_turns(self):
        """MockLLMProvider always returns immediately regardless of max_turns."""
        provider = MockLLMProvider()
        for turns in (1, 5, 100):
            result = provider.call_multi_turn("go", max_turns=turns)
            assert result == "mock-multi-turn:go"


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

    def test_call_model_override_takes_precedence(self):
        """When model is supplied to call(), it overrides agent_models lookup."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "claude-opus-4-6"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call = mock.MagicMock(return_value="overridden")

        result = registry.call("prompt", agent="developer", model="custom-model")

        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["model"] == "custom-model"
        assert result == "overridden"

    def test_call_json_model_override_takes_precedence(self):
        """When model is supplied to call_json(), it overrides agent_models lookup."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "claude-opus-4-6"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call_json = mock.MagicMock(return_value={"overridden": True})

        result = registry.call_json("prompt", agent="developer", model="custom-model")

        provider.call_json.assert_called_once_with("prompt", model="custom-model")
        assert result == {"overridden": True}

    def test_call_model_none_uses_agent_models(self):
        """When model is None, the agent_models lookup model is used."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "claude-opus-4-6"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call = mock.MagicMock(return_value="agent-model")

        registry.call("prompt", agent="developer")

        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"

    def test_call_json_model_none_uses_agent_models(self):
        """When model kwarg is omitted for call_json(), agent_models model is used."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "claude-opus-4-6"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call_json = mock.MagicMock(return_value={"agent": True})

        registry.call_json("prompt", agent="developer")

        provider.call_json.assert_called_once_with("prompt", model="claude-opus-4-6")

    def test_call_explicit_model_overrides_agent_models_opus(self):
        """call() with explicit model kwarg overrides agent_models opus entry."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "opus"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call = mock.MagicMock(return_value="explicit-win")

        result = registry.call("prompt", agent="developer", model="my-override-model")

        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["model"] == "my-override-model", (
            "Explicit model kwarg must override agent_models opus entry"
        )
        assert result == "explicit-win"

    def test_call_json_explicit_model_overrides_agent_models_opus(self):
        """call_json() with explicit model kwarg overrides agent_models opus entry."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "opus"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call_json = mock.MagicMock(return_value={"explicit": True})

        result = registry.call_json("prompt", agent="developer", model="my-override-model")

        provider.call_json.assert_called_once_with("prompt", model="my-override-model")
        assert result == {"explicit": True}

    def test_call_no_model_kwarg_falls_back_to_agent_models_opus(self):
        """Omitting model kwarg resolves from agent_models opus entry."""
        registry = _make_registry(
            {"developer": {"provider": "mock_a", "model": "opus"}}
        )
        provider, _ = registry.get_provider("developer")
        provider.call = mock.MagicMock(return_value="fallback-opus")

        result = registry.call("prompt", agent="developer")

        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["model"] == "opus", (
            "Without explicit model kwarg, agent_models opus must be used"
        )
        assert result == "fallback-opus"

    def test_get_provider_developer_returns_claude_opus_4_6(self):
        registry = _make_registry(
            {"developer": {"model": "claude-opus-4-6"}}
        )
        _provider, model = registry.get_provider("developer")
        assert model == "claude-opus-4-6"

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

    # -- call() timeout forwarding ---------------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_forwards_timeout(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response("ok")

        provider.call("hello", timeout=42.0)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["timeout"] == 42.0

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_omits_timeout_when_none(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response("ok")

        provider.call("hello")

        call_kwargs = mock_create.call_args.kwargs
        assert "timeout" not in call_kwargs

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

    # -- call_json() timeout forwarding ----------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_json_forwards_timeout(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response('{"ok": true}')

        provider.call_json("give me json", timeout=30.0)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["timeout"] == 30.0

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_call_json_omits_timeout_when_none(self, mock_cls):
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response('{"ok": true}')

        provider.call_json("give me json")

        call_kwargs = mock_create.call_args.kwargs
        assert "timeout" not in call_kwargs

    # -- call_multi_turn() -----------------------------------------------------

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_no_tools_falls_back_to_call(self, mock_cls):
        """When tools is None, call_multi_turn delegates to single-turn call()."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response("single turn answer")

        result = provider.call_multi_turn("hello")

        assert result == "single turn answer"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_single_text_response(self, mock_cls):
        """Model responds with text only (stop_reason='end_turn') → returns immediately."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
        )
        mock_create.return_value = resp

        tools = [{"name": "Read", "description": "Read a file", "input_schema": {"type": "object", "properties": {}}}]
        result = provider.call_multi_turn("do something", tools=tools)

        assert result == "done"
        assert mock_create.call_count == 1

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_tool_use_loop(self, mock_cls):
        """Model issues a tool_use, gets result, then responds with text."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        # Turn 1: model requests tool use
        tool_block = SimpleNamespace(
            type="tool_use", id="tu_1", name="Read",
            input={"file_path": "/tmp/test.txt"},
        )
        turn1 = SimpleNamespace(
            content=[tool_block],
            stop_reason="tool_use",
        )
        # Turn 2: model responds with text
        turn2 = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="file contents are xyz")],
            stop_reason="end_turn",
        )
        mock_create.side_effect = [turn1, turn2]

        tools = [{"name": "Read", "description": "Read", "input_schema": {"type": "object", "properties": {}}}]
        result = provider.call_multi_turn("read the file", tools=tools)

        assert "file contents are xyz" in result
        assert mock_create.call_count == 2

        # Verify tool_result was sent back (index 2 = tool_result message,
        # since messages is [user, assistant(turn1), user(tool_results), ...])
        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        tool_result_msg = second_call_messages[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "tu_1"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_max_turns_terminates(self, mock_cls):
        """Loop stops after max_turns even if model keeps requesting tools."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        tool_block = SimpleNamespace(
            type="tool_use", id="tu_loop", name="Bash",
            input={"command": "echo hi"},
        )
        # Every turn requests more tools
        mock_create.return_value = SimpleNamespace(
            content=[tool_block],
            stop_reason="tool_use",
        )

        tools = [{"name": "Bash", "description": "Run", "input_schema": {"type": "object", "properties": {}}}]
        result = provider.call_multi_turn("loop", tools=tools, max_turns=3)

        assert isinstance(result, str)
        assert mock_create.call_count == 3

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_custom_tool_executor(self, mock_cls):
        """tool_executor callback receives tool name and input, returns result."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        tool_block = SimpleNamespace(
            type="tool_use", id="tu_exec", name="Read",
            input={"file_path": "/etc/hosts"},
        )
        turn1 = SimpleNamespace(content=[tool_block], stop_reason="tool_use")
        turn2 = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="got it")],
            stop_reason="end_turn",
        )
        mock_create.side_effect = [turn1, turn2]

        executor_calls = []

        def executor(name, inp):
            executor_calls.append((name, inp))
            return "127.0.0.1 localhost"

        tools = [{"name": "Read", "description": "Read", "input_schema": {"type": "object", "properties": {}}}]
        result = provider.call_multi_turn("read hosts", tools=tools, tool_executor=executor)

        assert result == "got it"
        assert len(executor_calls) == 1
        assert executor_calls[0] == ("Read", {"file_path": "/etc/hosts"})

        # Verify the executor result was sent back as tool_result content
        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        tool_result_content = second_call_messages[2]["content"][0]["content"]
        assert tool_result_content == "127.0.0.1 localhost"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_empty_tools_list_falls_back(self, mock_cls):
        """Empty tools list behaves the same as None — single-turn fallback."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = _make_anthropic_response("fallback")

        result = provider.call_multi_turn("hello", tools=[])

        assert result == "fallback"

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_forwards_timeout(self, mock_cls):
        """timeout kwarg is forwarded to every Anthropic messages.create call in the loop."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        tool_block = SimpleNamespace(
            type="tool_use", id="tu_t", name="Bash",
            input={"command": "ls"},
        )
        turn1 = SimpleNamespace(content=[tool_block], stop_reason="tool_use")
        turn2 = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
        )
        mock_create.side_effect = [turn1, turn2]

        tools = [{"name": "Bash", "description": "Run", "input_schema": {"type": "object", "properties": {}}}]
        provider.call_multi_turn("go", tools=tools, timeout=99.0)

        assert mock_create.call_count == 2
        for call_args in mock_create.call_args_list:
            assert call_args.kwargs["timeout"] == 99.0

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_multiple_tool_blocks_dispatched(self, mock_cls):
        """When a single response contains multiple tool_use blocks, all are dispatched."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        block_a = SimpleNamespace(type="tool_use", id="tu_a", name="Read", input={"file_path": "a.txt"})
        block_b = SimpleNamespace(type="tool_use", id="tu_b", name="Grep", input={"pattern": "foo"})
        turn1 = SimpleNamespace(content=[block_a, block_b], stop_reason="tool_use")
        turn2 = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="both done")],
            stop_reason="end_turn",
        )
        mock_create.side_effect = [turn1, turn2]

        dispatched = []

        def executor(name, inp):
            dispatched.append(name)
            return f"result-{name}"

        tools = [
            {"name": "Read", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
            {"name": "Grep", "description": "Grep", "input_schema": {"type": "object", "properties": {}}},
        ]
        result = provider.call_multi_turn("go", tools=tools, tool_executor=executor)

        assert result == "both done"
        assert dispatched == ["Read", "Grep"]

        # Both tool_result messages sent back
        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        tool_results_msg = second_call_messages[2]  # user message with tool_results
        assert tool_results_msg["role"] == "user"
        result_ids = {r["tool_use_id"] for r in tool_results_msg["content"]}
        assert result_ids == {"tu_a", "tu_b"}
        result_contents = {r["content"] for r in tool_results_msg["content"]}
        assert result_contents == {"result-Read", "result-Grep"}

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_end_turn_exits_immediately(self, mock_cls):
        """stop_reason='end_turn' on first response exits the loop with one API call."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create
        mock_create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="immediate answer")],
            stop_reason="end_turn",
        )

        tools = [{"name": "Read", "description": "Read", "input_schema": {"type": "object", "properties": {}}}]
        result = provider.call_multi_turn("question", tools=tools, max_turns=10)

        assert result == "immediate answer"
        assert mock_create.call_count == 1

    @mock.patch("crazypumpkin.llm.anthropic_api.Anthropic")
    def test_multi_turn_max_turns_exact_count(self, mock_cls):
        """Anthropic client is called exactly max_turns times when model always requests tools."""
        from crazypumpkin.llm.anthropic_api import AnthropicProvider

        provider = AnthropicProvider()
        mock_create = provider._client.messages.create

        tool_block = SimpleNamespace(
            type="tool_use", id="tu_x", name="Bash",
            input={"command": "echo"},
        )
        mock_create.return_value = SimpleNamespace(
            content=[tool_block],
            stop_reason="tool_use",
        )

        tools = [{"name": "Bash", "description": "Run", "input_schema": {"type": "object", "properties": {}}}]

        for max_t in (1, 2, 5):
            mock_create.reset_mock()
            provider.call_multi_turn("loop", tools=tools, max_turns=max_t)
            assert mock_create.call_count == max_t, (
                f"Expected exactly {max_t} API calls, got {mock_create.call_count}"
            )


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
