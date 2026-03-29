from __future__ import annotations

from crazypumpkin.framework.models import AgentConfig, BudgetExceededError
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.anthropic_api import AnthropicProvider
from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.llm.openai_api import OpenAIProvider

PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "anthropic_api": AnthropicProvider,
    "openai_api": OpenAIProvider,
}


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
        return provider.call(prompt, model=effective_model, timeout=timeout, cwd=cwd, tools=tools)

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
