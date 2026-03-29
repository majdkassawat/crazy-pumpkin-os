from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from crazypumpkin.framework.models import AgentConfig, BudgetExceededError
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.anthropic_api import AnthropicProvider
from crazypumpkin.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class AllProvidersExhaustedError(Exception):
    """Raised when all providers in a fallback chain have been exhausted."""


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Return delay in seconds for the given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)


@dataclass
class FallbackChain:
    provider_names: list[str] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "anthropic_api": AnthropicProvider,
}

try:
    from crazypumpkin.llm.openai_api import OpenAIProvider

    PROVIDER_CLASSES["openai_api"] = OpenAIProvider
except ImportError:
    pass

try:
    from crazypumpkin.llm.litellm_provider import LiteLLMProvider

    PROVIDER_CLASSES["litellm"] = LiteLLMProvider
except ImportError:
    pass


class ProviderRegistry:
    """Routes LLM calls to the correct provider/model based on config.

    Expected config structure (the ``llm`` section of config.yaml)::

        {
            "default_provider": "anthropic_api",
            "providers": {
                "anthropic_api": {"api_key": "..."},
                "openai_api":    {"api_key": "..."},
            },
            "agent_models": {
                "developer":  {"model": "opus"},
                "strategist": {"model": "sonnet", "provider": "openai_api"},
            },
        }
    """

    def __init__(self, config: dict, store: Store | None = None) -> None:
        self._config = config
        self._store = store
        self._default_provider_name: str = config["default_provider"]
        self._agent_models: dict[str, dict] = config.get("agent_models", {})

        # Instantiate each declared provider once.
        self._providers: dict[str, LLMProvider] = {}
        for name, provider_cfg in config.get("providers", {}).items():
            cls = PROVIDER_CLASSES.get(name)
            if cls is not None:
                self._providers[name] = cls(provider_cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_provider(self, agent: str | None = None) -> tuple[LLMProvider, str | None]:
        """Return ``(provider_instance, model_override)`` for *agent*.

        Falls back to the default provider when the agent key is absent
        from ``agent_models``.
        """
        override = self._agent_models.get(agent) if agent else None

        if override:
            provider_name = override.get("provider", self._default_provider_name)
            model = override.get("model")
        else:
            provider_name = self._default_provider_name
            model = None

        provider = self._providers.get(provider_name)
        if provider is None:
            raise KeyError(
                f"Provider '{provider_name}' not found in registry. "
                f"Available: {list(self._providers)}"
            )
        return provider, model

    def _check_budget(self, agent: str | None, agent_config: AgentConfig | None = None) -> None:
        """Raise ``BudgetExceededError`` if the agent has exceeded its budget.

        When *agent_config* is not provided the check is skipped (callers
        that don't track budgets can omit it).
        """
        if agent is None or self._store is None or agent_config is None:
            return
        if self._store.is_budget_exceeded(agent, agent_config):
            m = self._store._agent_metrics.get(agent)
            spent = m.budget_spent_usd if m else 0.0
            raise BudgetExceededError(agent, spent, agent_config.monthly_budget_usd)

    def call(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        agent_config: AgentConfig | None = None,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
        system: str | None = None,
    ) -> str:
        """Dispatch a text call to the provider assigned to *agent*.

        When *model* is provided it takes precedence over the model
        returned by the ``agent_models`` lookup.

        Raises ``BudgetExceededError`` if the agent has exceeded its
        monthly budget cap.
        """
        self._check_budget(agent, agent_config)
        provider, agent_model = self.get_provider(agent)
        effective_model = model if model is not None else agent_model

        # Use call_with_cost if available to track spend
        if hasattr(provider, "call_with_cost") and not tools:
            text, cost = provider.call_with_cost(prompt, model=effective_model, timeout=timeout, system=system)
            if agent and self._store is not None:
                self._store.record_llm_spend(agent, cost.cost_usd)
            return text

        return provider.call(prompt, model=effective_model, timeout=timeout, cwd=cwd, tools=tools, system=system)

    def call_multi_turn(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        agent_config: AgentConfig | None = None,
        model: str | None = None,
        max_turns: int = 10,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
    ) -> str:
        """Dispatch a multi-turn agentic call to the provider assigned to *agent*.

        When *model* is provided it takes precedence over the model
        returned by the ``agent_models`` lookup.

        Raises ``BudgetExceededError`` if the agent has exceeded its
        monthly budget cap.
        """
        self._check_budget(agent, agent_config)
        provider, agent_model = self.get_provider(agent)
        effective_model = model if model is not None else agent_model
        return provider.call_multi_turn(
            prompt,
            max_turns=max_turns,
            tools=tools,
            timeout=timeout,
            cwd=cwd,
        )

    def call_json(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        agent_config: AgentConfig | None = None,
        model: str | None = None,
        **kwargs: object,
    ) -> dict | list:
        """Dispatch a JSON call to the provider assigned to *agent*.

        When *model* is provided it takes precedence over the model
        returned by the ``agent_models`` lookup.

        Raises ``BudgetExceededError`` if the agent has exceeded its
        monthly budget cap.
        """
        self._check_budget(agent, agent_config)
        provider, agent_model = self.get_provider(agent)
        effective_model = model if model is not None else agent_model
        if effective_model is not None:
            kwargs["model"] = effective_model
        return provider.call_json(prompt, **kwargs)

    async def call_with_fallback(
        self, chain: FallbackChain, messages: list[dict], **kwargs: Any
    ) -> dict:
        """Try each provider in *chain* with retries and exponential backoff.

        Raises ``AllProvidersExhaustedError`` if every provider has been
        exhausted after all retry attempts.
        """
        all_errors: list[tuple[str, Exception]] = []
        for provider_name in chain.provider_names:
            provider = self._providers.get(provider_name)
            if provider is None:
                logger.warning("Provider '%s' not found in registry, skipping.", provider_name)
                continue
            for attempt in range(chain.retry_policy.max_retries):
                try:
                    result = provider.call(messages[0].get("content", ""), **kwargs)
                    return {"provider": provider_name, "result": result}
                except Exception as exc:
                    all_errors.append((provider_name, exc))
                    delay = chain.retry_policy.delay_for_attempt(attempt)
                    logger.warning(
                        "Provider '%s' attempt %d failed: %s. Retrying in %.1fs.",
                        provider_name, attempt + 1, exc, delay,
                    )
                    await asyncio.sleep(delay)
            logger.error("Provider '%s' exhausted after %d retries.", provider_name, chain.retry_policy.max_retries)
        error_summary = "; ".join(
            f"{name}: {exc}" for name, exc in all_errors
        )
        raise AllProvidersExhaustedError(
            f"All providers exhausted. Errors: {error_summary}"
        )
