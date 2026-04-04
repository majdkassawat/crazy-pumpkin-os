"""Tests for cost tracking integration in the LiteLLM provider."""

import sys
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

# Ensure litellm is available as a mock module so litellm_provider can be imported
# even when the real package isn't installed.
if "litellm" not in sys.modules:
    _mock_litellm = mock.MagicMock()
    _mock_litellm.success_callback = []
    sys.modules["litellm"] = _mock_litellm

from crazypumpkin.observability.cost import CostTracker, get_cost_tracker
from crazypumpkin.observability.tracing import reset_tracer


@pytest.fixture(autouse=True)
def _clean_tracer():
    """Ensure no global tracer leaks between tests."""
    reset_tracer()
    yield
    reset_tracer()


# ---------------------------------------------------------------------------
# Helpers — fake LiteLLM response objects
# ---------------------------------------------------------------------------


def _litellm_response(prompt_tokens=10, completion_tokens=20, cached_tokens=5, cost_usd=0.001):
    """Build a fake LiteLLM/OpenAI-style response."""
    details = SimpleNamespace(cached_tokens=cached_tokens)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_tokens_details=details,
        cost_usd=cost_usd,
    )
    message = SimpleNamespace(content="hello")
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(usage=usage, choices=[choice])


# ---------------------------------------------------------------------------
# get_cost_tracker() singleton
# ---------------------------------------------------------------------------


class TestGetCostTracker:
    """get_cost_tracker() returns a lazy singleton CostTracker."""

    def test_returns_cost_tracker_instance(self):
        tracker = get_cost_tracker()
        assert isinstance(tracker, CostTracker)

    def test_returns_same_instance_across_calls(self):
        a = get_cost_tracker()
        b = get_cost_tracker()
        assert a is b


# ---------------------------------------------------------------------------
# LiteLLMProvider cost integration
# ---------------------------------------------------------------------------


class TestLiteLLMProviderCostTracking:
    """LiteLLMProvider records cost after each successful completion."""

    @pytest.fixture()
    def tracker(self):
        return CostTracker()

    @pytest.fixture()
    def provider(self, tracker):
        from crazypumpkin.llm.litellm_provider import LiteLLMProvider

        return LiteLLMProvider(config={"api_key": "fake"}, cost_tracker=tracker)

    def test_call_records_usage(self, provider, tracker):
        resp = _litellm_response(prompt_tokens=100, completion_tokens=50)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.005
            m_litellm.success_callback = []
            provider.call("hi")

        assert tracker.total_spend() == pytest.approx(0.005)
        assert len(tracker._records) == 1
        rec = tracker._records[0]
        assert rec.prompt_tokens == 100
        assert rec.completion_tokens == 50

    def test_call_json_records_usage(self, provider, tracker):
        resp = _litellm_response(prompt_tokens=80, completion_tokens=40)
        resp.choices[0].message.content = '{"a": 1}'
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.003
            m_litellm.success_callback = []
            provider.call_json("give json")

        assert len(tracker._records) == 1
        rec = tracker._records[0]
        assert rec.prompt_tokens == 80
        assert rec.completion_tokens == 40

    def test_call_multi_turn_records_usage(self, provider, tracker):
        resp = _litellm_response(prompt_tokens=60, completion_tokens=25)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.002
            m_litellm.success_callback = []
            provider.call_multi_turn("hi")

        assert len(tracker._records) == 1

    def test_token_counts_extracted_from_response(self, provider, tracker):
        resp = _litellm_response(prompt_tokens=111, completion_tokens=222)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.01
            m_litellm.success_callback = []
            provider.call("test")

        rec = tracker._records[0]
        assert rec.prompt_tokens == 111
        assert rec.completion_tokens == 222

    def test_cost_extracted_via_completion_cost(self, provider, tracker):
        resp = _litellm_response(prompt_tokens=50, completion_tokens=25)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.042
            m_litellm.success_callback = []
            provider.call("test")

        assert tracker.total_spend() == pytest.approx(0.042)

    def test_cost_fallback_on_completion_cost_error(self, provider, tracker):
        """When litellm.completion_cost() raises, cost defaults to 0.0."""
        resp = _litellm_response(prompt_tokens=50, completion_tokens=25)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.side_effect = Exception("no pricing")
            m_litellm.success_callback = []
            provider.call("test")

        assert tracker.total_spend() == pytest.approx(0.0)
        assert len(tracker._records) == 1

    def test_model_name_recorded(self, provider, tracker):
        resp = _litellm_response()
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call("hi", model="gpt-4o-mini")

        rec = tracker._records[0]
        assert rec.model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Agent name pass-through
# ---------------------------------------------------------------------------


class TestAgentNamePassThrough:
    """Agent name is passed through to cost recording when available."""

    @pytest.fixture()
    def tracker(self):
        return CostTracker()

    @pytest.fixture()
    def provider(self, tracker):
        from crazypumpkin.llm.litellm_provider import LiteLLMProvider

        return LiteLLMProvider(config={"api_key": "fake"}, cost_tracker=tracker)

    def test_agent_name_from_call_parameter(self, provider, tracker):
        resp = _litellm_response()
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call("hi", agent_name="writer-agent")

        rec = tracker._records[0]
        assert rec.agent_name == "writer-agent"

    def test_agent_param_used_as_agent_name(self, provider, tracker):
        """The existing 'agent' kwarg is used as agent_name when set."""
        resp = _litellm_response()
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call("hi", agent="reviewer")

        rec = tracker._records[0]
        assert rec.agent_name == "reviewer"

    def test_default_agent_name_is_unknown(self, provider, tracker):
        resp = _litellm_response()
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call("hi")

        rec = tracker._records[0]
        assert rec.agent_name == "unknown"

    def test_agent_name_in_call_json(self, provider, tracker):
        resp = _litellm_response()
        resp.choices[0].message.content = '{"ok": true}'
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call_json("give json", agent="planner")

        rec = tracker._records[0]
        assert rec.agent_name == "planner"

    def test_agent_name_in_call_multi_turn(self, provider, tracker):
        resp = _litellm_response()
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            provider.call_multi_turn("hi", agent_name="coder")

        rec = tracker._records[0]
        assert rec.agent_name == "coder"


# ---------------------------------------------------------------------------
# Fallback to global tracker
# ---------------------------------------------------------------------------


class TestFallbackToGlobalTracker:
    """When no cost_tracker is provided, the provider falls back to the global singleton."""

    def test_uses_global_tracker_when_none(self):
        from crazypumpkin.llm.litellm_provider import LiteLLMProvider

        p = LiteLLMProvider(config={"api_key": "fake"})
        assert p.cost_tracker is None

        fake_tracker = CostTracker()
        resp = _litellm_response(prompt_tokens=10, completion_tokens=5)
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.completion_cost.return_value = 0.001
            m_litellm.success_callback = []
            with mock.patch("crazypumpkin.llm.litellm_provider.get_cost_tracker", return_value=fake_tracker):
                p.call("hi")

        assert len(fake_tracker._records) == 1


# ---------------------------------------------------------------------------
# No usage in response
# ---------------------------------------------------------------------------


class TestNoUsageInResponse:
    """When the response has no usage data, no cost is recorded."""

    def test_no_usage_no_record(self):
        from crazypumpkin.llm.litellm_provider import LiteLLMProvider

        tracker = CostTracker()
        p = LiteLLMProvider(config={"api_key": "fake"}, cost_tracker=tracker)
        message = SimpleNamespace(content="hello")
        choice = SimpleNamespace(message=message)
        resp = SimpleNamespace(usage=None, choices=[choice])
        with mock.patch("crazypumpkin.llm.litellm_provider.litellm") as m_litellm:
            m_litellm.completion.return_value = resp
            m_litellm.success_callback = []
            p.call("hi")

        assert len(tracker._records) == 0


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------


class TestCostTrackerThreadSafety:
    """CostTracker.record() is safe under concurrent access."""

    def test_concurrent_records_no_lost_updates(self):
        tracker = CostTracker()
        n_threads = 10
        n_per_thread = 100
        barrier = threading.Barrier(n_threads)

        def worker(tid: int) -> None:
            barrier.wait()
            for i in range(n_per_thread):
                tracker.record(
                    agent_name=f"agent-{tid}",
                    model="gpt-4o",
                    prompt_tokens=10,
                    completion_tokens=5,
                    cost_usd=0.001,
                )

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = n_threads * n_per_thread
        assert len(tracker._records) == expected
        assert tracker.total_spend() == pytest.approx(expected * 0.001)
