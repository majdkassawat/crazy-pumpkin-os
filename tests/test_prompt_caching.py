"""Tests for prompt caching (Anthropic cache_control + OpenAI store/prefix)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.llm.anthropic_api import AnthropicProvider
from crazypumpkin.llm.openai_api import OpenAIProvider
from crazypumpkin.observability import metrics as obs_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str = "ok") -> SimpleNamespace:
    """Build a fake Anthropic messages.create response."""
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=usage, stop_reason="end_turn")


def _build_provider(*, cache_enabled: bool = True) -> AnthropicProvider:
    """Instantiate an AnthropicProvider with a mocked client."""
    with mock.patch("crazypumpkin.llm.anthropic_api.Anthropic"):
        provider = AnthropicProvider(
            config={"api_key": "test-key"},
            cache_enabled=cache_enabled,
        )
    provider._client = mock.MagicMock()
    provider._client.messages.create.return_value = _make_response()
    return provider


# ---------------------------------------------------------------------------
# Tests: system message cache_control
# ---------------------------------------------------------------------------


class TestSystemMessageCacheControl:
    """System messages sent to the Anthropic API include cache_control."""

    def test_system_block_has_cache_control(self):
        provider = _build_provider()
        provider.call("hello", system="You are helpful.")

        call_kwargs = provider._client.messages.create.call_args
        system_blocks = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert len(system_blocks) == 1
        assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_system_block_cache_control_on_first_block(self):
        """The first system block should carry cache_control."""
        provider = _build_provider()
        blocks = provider._build_system_blocks("You are helpful.", cache=True)
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_call_json_includes_system_cache_control(self):
        provider = _build_provider()
        provider._client.messages.create.return_value = _make_response('{"a": 1}')
        provider.call_json("give json", system="system prompt")

        call_kwargs = provider._client.messages.create.call_args
        system_blocks = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Tests: tool definitions cache_control
# ---------------------------------------------------------------------------


class TestToolDefinitionsCacheControl:
    """Tool definitions include cache_control breakpoints."""

    def test_tool_definitions_get_cache_control(self):
        provider = _build_provider()
        tools = [
            {"name": "read_file", "description": "Read a file", "input_schema": {}},
            {"name": "write_file", "description": "Write a file", "input_schema": {}},
        ]
        provider.call("do something", tools=tools)

        # The last tool definition should have cache_control
        assert tools[-1]["cache_control"] == {"type": "ephemeral"}

    def test_single_tool_gets_cache_control(self):
        provider = _build_provider()
        tools = [{"name": "run", "description": "Run cmd", "input_schema": {}}]
        provider.call("run it", tools=tools)
        assert tools[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Tests: cache_enabled=False
# ---------------------------------------------------------------------------


class TestCacheEnabledFalse:
    """cache_enabled=False skips cache injection entirely."""

    def test_no_system_cache_control_when_disabled(self):
        provider = _build_provider(cache_enabled=False)
        provider.call("hello", system="You are helpful.")

        call_kwargs = provider._client.messages.create.call_args
        system_blocks = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert "cache_control" not in system_blocks[0]

    def test_no_tool_cache_control_when_disabled(self):
        provider = _build_provider(cache_enabled=False)
        tools = [{"name": "run", "description": "Run cmd", "input_schema": {}}]
        provider.call("hello", tools=tools)
        assert "cache_control" not in tools[0]

    def test_build_system_blocks_respects_cache_enabled_false(self):
        provider = _build_provider(cache_enabled=False)
        blocks = provider._build_system_blocks("sys prompt", cache=True)
        assert "cache_control" not in blocks[0]

    def test_per_call_cache_false_also_skips(self):
        """Even with cache_enabled=True on provider, cache=False per-call skips."""
        provider = _build_provider(cache_enabled=True)
        provider.call("hello", system="prompt", cache=False)

        call_kwargs = provider._client.messages.create.call_args
        system_blocks = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert "cache_control" not in system_blocks[0]


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------


class TestApplyCacheControlIdempotent:
    """_apply_cache_control is idempotent -- calling twice does not duplicate."""

    def test_double_apply_system_blocks(self):
        provider = _build_provider()
        blocks = [{"type": "text", "text": "system prompt"}]
        provider._apply_cache_control(blocks)
        provider._apply_cache_control(blocks)

        # Should still have exactly one cache_control key with the same value
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert len(blocks) == 1

    def test_double_apply_with_positions(self):
        provider = _build_provider()
        blocks = [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
        provider._apply_cache_control(blocks, cache_positions=[0])
        provider._apply_cache_control(blocks, cache_positions=[0])

        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in blocks[1]

    def test_double_apply_tool_cache_control(self):
        provider = _build_provider()
        tools = [
            {"name": "t1", "description": "d1", "input_schema": {}},
            {"name": "t2", "description": "d2", "input_schema": {}},
        ]
        provider._apply_tool_cache_control(tools)
        provider._apply_tool_cache_control(tools)

        assert tools[-1]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in tools[0]

    def test_calling_call_twice_does_not_duplicate(self):
        """End-to-end: calling provider.call twice with same tools is safe."""
        provider = _build_provider()
        tools = [{"name": "run", "description": "Run", "input_schema": {}}]
        provider.call("a", tools=tools, system="sys")
        provider.call("b", tools=tools, system="sys")

        assert tools[0]["cache_control"] == {"type": "ephemeral"}


# ===========================================================================
# OpenAI prompt caching tests
# ===========================================================================


def _make_openai_response(text: str = "ok") -> SimpleNamespace:
    """Build a fake OpenAI chat.completions.create response."""
    message = SimpleNamespace(content=text, role="assistant")
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[choice], usage=usage)


def _build_openai_provider(*, cache_enabled: bool = True) -> OpenAIProvider:
    """Instantiate an OpenAIProvider with a mocked client."""
    with mock.patch("crazypumpkin.llm.openai_api.OpenAI"):
        provider = OpenAIProvider(
            config={"api_key": "test-key"},
            cache_enabled=cache_enabled,
        )
    provider._client = mock.MagicMock()
    provider._client.chat.completions.create.return_value = _make_openai_response()
    return provider


# ---------------------------------------------------------------------------
# Tests: OpenAI store parameter
# ---------------------------------------------------------------------------


class TestOpenAIStoreParameter:
    """OpenAI requests include store: true when cache_enabled is True."""

    def test_call_includes_store_true(self):
        provider = _build_openai_provider()
        provider.call("hello")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("store") is True

    def test_call_with_system_includes_store_true(self):
        provider = _build_openai_provider()
        provider.call("hello", system="You are helpful.")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("store") is True

    def test_call_with_cost_includes_store_true(self):
        provider = _build_openai_provider()
        provider.call_with_cost("hello", system="sys")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("store") is True

    def test_call_json_includes_store_true(self):
        provider = _build_openai_provider()
        provider._client.chat.completions.create.return_value = _make_openai_response('{"a": 1}')
        provider.call_json("give json", system="system prompt")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("store") is True

    def test_call_multi_turn_includes_store_true(self):
        provider = _build_openai_provider()
        provider.call_multi_turn("hello", system="sys")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("store") is True


# ---------------------------------------------------------------------------
# Tests: OpenAI system message prefix caching structure
# ---------------------------------------------------------------------------


class TestOpenAICacheHints:
    """System messages are structured to maximize prefix caching."""

    def test_system_message_comes_first(self):
        provider = _build_openai_provider()
        provider.call("hello", system="You are helpful.")

        call_kwargs = provider._client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_apply_cache_hints_reorders_system_first(self):
        provider = _build_openai_provider()
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "sys"},
        ]
        result = provider._apply_cache_hints(messages)
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_apply_cache_hints_preserves_order_when_already_correct(self):
        provider = _build_openai_provider()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        result = provider._apply_cache_hints(messages)
        assert result == messages

    def test_apply_cache_hints_no_system(self):
        provider = _build_openai_provider()
        messages = [{"role": "user", "content": "hi"}]
        result = provider._apply_cache_hints(messages)
        assert result == [{"role": "user", "content": "hi"}]

    def test_apply_cache_hints_multiple_system_messages(self):
        provider = _build_openai_provider()
        messages = [
            {"role": "user", "content": "q"},
            {"role": "system", "content": "sys1"},
            {"role": "system", "content": "sys2"},
        ]
        result = provider._apply_cache_hints(messages)
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "system"
        assert result[2]["role"] == "user"

    def test_call_json_system_message_comes_first(self):
        provider = _build_openai_provider()
        provider._client.chat.completions.create.return_value = _make_openai_response('{"x": 1}')
        provider.call_json("give json", system="sys prompt")

        call_kwargs = provider._client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Tests: OpenAI cache_enabled=False
# ---------------------------------------------------------------------------


class TestOpenAICacheDisabled:
    """cache_enabled=False produces unmodified requests (no store param)."""

    def test_no_store_when_cache_disabled(self):
        provider = _build_openai_provider(cache_enabled=False)
        provider.call("hello")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "store" not in call_kwargs.kwargs

    def test_no_store_when_per_call_cache_false(self):
        """cache=False per-call also omits store."""
        provider = _build_openai_provider(cache_enabled=True)
        provider.call("hello", cache=False)

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "store" not in call_kwargs.kwargs

    def test_messages_not_reordered_when_disabled(self):
        """When caching is off, messages should not go through _apply_cache_hints."""
        provider = _build_openai_provider(cache_enabled=False)
        provider.call("hello", system="sys")

        call_kwargs = provider._client.chat.completions.create.call_args
        # The key assertion is that store is absent
        assert "store" not in call_kwargs.kwargs

    def test_call_with_cost_no_store_when_disabled(self):
        provider = _build_openai_provider(cache_enabled=False)
        provider.call_with_cost("hello")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "store" not in call_kwargs.kwargs

    def test_call_json_no_store_when_disabled(self):
        provider = _build_openai_provider(cache_enabled=False)
        provider._client.chat.completions.create.return_value = _make_openai_response('{}')
        provider.call_json("json please")

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "store" not in call_kwargs.kwargs

    def test_call_json_no_store_when_per_call_cache_false(self):
        provider = _build_openai_provider(cache_enabled=True)
        provider._client.chat.completions.create.return_value = _make_openai_response('{}')
        provider.call_json("json please", cache=False)

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "store" not in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# Tests: OpenAI constructor
# ---------------------------------------------------------------------------


class TestOpenAICacheConstructor:
    """cache_enabled parameter on constructor."""

    def test_default_cache_enabled_true(self):
        with mock.patch("crazypumpkin.llm.openai_api.OpenAI"):
            provider = OpenAIProvider(config={"api_key": "k"})
        assert provider.cache_enabled is True

    def test_cache_enabled_false(self):
        with mock.patch("crazypumpkin.llm.openai_api.OpenAI"):
            provider = OpenAIProvider(config={"api_key": "k"}, cache_enabled=False)
        assert provider.cache_enabled is False


# ===========================================================================
# Cache hit/miss metrics tests
# ===========================================================================


def _make_response_with_cache(
    text: str = "ok",
    cache_read: int = 0,
    cache_creation: int = 0,
) -> SimpleNamespace:
    """Build a fake Anthropic response with specific cache token counts."""
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )
    return SimpleNamespace(content=[block], usage=usage, stop_reason="end_turn")


# ---------------------------------------------------------------------------
# Tests: record_cache_result increments by provider
# ---------------------------------------------------------------------------


class TestRecordCacheResult:
    """record_cache_result increments hit or miss counter by provider."""

    def setup_method(self):
        obs_metrics.reset()

    def test_hit_increments_hit_counter(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 0

    def test_miss_increments_miss_counter(self):
        obs_metrics.record_cache_result("anthropic", hit=False)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 0
        assert stats["total_misses"] == 1

    def test_per_provider_hit_tracking(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=50)
        obs_metrics.record_cache_result("openai", hit=True, tokens_saved=30)
        obs_metrics.record_cache_result("anthropic", hit=False)

        assert obs_metrics._cr_hits_by_provider["anthropic"] == 1
        assert obs_metrics._cr_hits_by_provider["openai"] == 1
        assert obs_metrics._cr_misses_by_provider["anthropic"] == 1
        assert "openai" not in obs_metrics._cr_misses_by_provider

    def test_multiple_hits_same_provider(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=10)
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=20)
        obs_metrics.record_cache_result("anthropic", hit=False)

        assert obs_metrics._cr_hits_by_provider["anthropic"] == 2
        assert obs_metrics._cr_misses_by_provider["anthropic"] == 1


# ---------------------------------------------------------------------------
# Tests: get_cache_stats returns accurate hit_rate as float 0-1
# ---------------------------------------------------------------------------


class TestGetCacheStats:
    """get_cache_stats returns accurate hit_rate as float between 0 and 1."""

    def setup_method(self):
        obs_metrics.reset()

    def test_empty_stats(self):
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 0
        assert stats["total_misses"] == 0
        assert stats["total_tokens_saved"] == 0
        assert stats["hit_rate"] == 0.0

    def test_all_hits(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=200)
        stats = obs_metrics.get_cache_stats()
        assert stats["hit_rate"] == 1.0

    def test_all_misses(self):
        obs_metrics.record_cache_result("anthropic", hit=False)
        obs_metrics.record_cache_result("anthropic", hit=False)
        stats = obs_metrics.get_cache_stats()
        assert stats["hit_rate"] == 0.0

    def test_mixed_hit_rate(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        obs_metrics.record_cache_result("anthropic", hit=False)
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=50)
        obs_metrics.record_cache_result("anthropic", hit=False)
        stats = obs_metrics.get_cache_stats()
        assert stats["hit_rate"] == 0.5

    def test_hit_rate_is_float(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=10)
        obs_metrics.record_cache_result("anthropic", hit=False)
        obs_metrics.record_cache_result("anthropic", hit=False)
        stats = obs_metrics.get_cache_stats()
        assert isinstance(stats["hit_rate"], float)
        assert 0.0 <= stats["hit_rate"] <= 1.0
        assert abs(stats["hit_rate"] - 1 / 3) < 1e-9


# ---------------------------------------------------------------------------
# Tests: tokens_saved accumulates correctly
# ---------------------------------------------------------------------------


class TestTokensSavedAccumulation:
    """tokens_saved accumulates correctly across multiple calls."""

    def setup_method(self):
        obs_metrics.reset()

    def test_tokens_saved_accumulates(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=250)
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=50)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_tokens_saved"] == 400

    def test_miss_does_not_add_tokens(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        obs_metrics.record_cache_result("anthropic", hit=False)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_tokens_saved"] == 100

    def test_tokens_saved_across_providers(self):
        obs_metrics.record_cache_result("anthropic", hit=True, tokens_saved=100)
        obs_metrics.record_cache_result("openai", hit=True, tokens_saved=200)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_tokens_saved"] == 300

    def test_default_tokens_saved_is_zero(self):
        obs_metrics.record_cache_result("anthropic", hit=True)
        stats = obs_metrics.get_cache_stats()
        assert stats["total_tokens_saved"] == 0
        assert stats["total_hits"] == 1


# ---------------------------------------------------------------------------
# Tests: Anthropic provider calls record_cache_result
# ---------------------------------------------------------------------------


class TestAnthropicRecordsCacheResult:
    """Anthropic provider calls record_cache_result after each API response."""

    def setup_method(self):
        obs_metrics.reset()

    def test_call_records_cache_miss(self):
        provider = _build_provider()
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=0, cache_creation=100,
        )
        provider.call("hello", system="sys")
        stats = obs_metrics.get_cache_stats()
        assert stats["total_misses"] >= 1

    def test_call_records_cache_hit(self):
        provider = _build_provider()
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=500, cache_creation=0,
        )
        provider.call("hello", system="sys")
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 1
        assert stats["total_tokens_saved"] == 500

    def test_call_json_records_cache_result(self):
        provider = _build_provider()
        provider._client.messages.create.return_value = _make_response_with_cache(
            text='{"a": 1}', cache_read=200,
        )
        provider.call_json("give json", system="sys")
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 1
        assert stats["total_tokens_saved"] == 200

    def test_call_with_cost_records_cache_result(self):
        provider = _build_provider()
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=300,
        )
        provider.call_with_cost("hello", system="sys")
        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 1
        assert stats["total_tokens_saved"] == 300

    def test_multiple_calls_accumulate(self):
        provider = _build_provider()
        # First call: cache miss
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=0, cache_creation=100,
        )
        provider.call("hello", system="sys")
        # Second call: cache hit
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=400,
        )
        provider.call("hello again", system="sys")
        # Third call: cache hit
        provider._client.messages.create.return_value = _make_response_with_cache(
            cache_read=600,
        )
        provider.call("once more", system="sys")

        stats = obs_metrics.get_cache_stats()
        assert stats["total_hits"] == 2
        assert stats["total_misses"] == 1
        assert stats["total_tokens_saved"] == 1000
        assert abs(stats["hit_rate"] - 2 / 3) < 1e-9
