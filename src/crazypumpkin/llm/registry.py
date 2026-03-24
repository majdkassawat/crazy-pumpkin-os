from __future__ import annotations

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

    def __init__(self, config: dict) -> None:
        self._config = config
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

    def call(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
    ) -> str:
        """Dispatch a text call to the provider assigned to *agent*.

        When *model* is provided it takes precedence over the model
        returned by the ``agent_models`` lookup.
        """
        provider, agent_model = self.get_provider(agent)
        effective_model = model if model is not None else agent_model
        return provider.call(prompt, model=effective_model, timeout=timeout, cwd=cwd, tools=tools)

    def call_json(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        model: str | None = None,
        **kwargs: object,
    ) -> dict | list:
        """Dispatch a JSON call to the provider assigned to *agent*.

        When *model* is provided it takes precedence over the model
        returned by the ``agent_models`` lookup.
        """
        provider, agent_model = self.get_provider(agent)
        effective_model = model if model is not None else agent_model
        if effective_model is not None:
            kwargs["model"] = effective_model
        return provider.call_json(prompt, **kwargs)
