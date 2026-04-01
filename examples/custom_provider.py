"""Example: Creating and registering a custom LLM provider.

This script demonstrates how to subclass ``LLMProvider`` to create a
custom backend and register it so the framework's ``ProviderRegistry``
can route calls to it.
"""

from __future__ import annotations

import json
from typing import Any

from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.llm.registry import PROVIDER_CLASSES, ProviderRegistry


# ---------------------------------------------------------------------------
# 1. Define a custom provider by subclassing LLMProvider
# ---------------------------------------------------------------------------

class EchoProvider(LLMProvider):
    """A minimal provider that echoes the prompt back.

    This is useful for testing pipelines without making real API calls.
    The constructor receives the provider config dict from config.yaml.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.prefix = self.config.get("prefix", "echo")

    def call(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        tools: list | None = None,
        system: str | None = None,
        cache: bool = True,
    ) -> str:
        """Return the prompt prefixed with provider info."""
        model_name = model or "default"
        return f"[{self.prefix}:{model_name}] {prompt}"

    def call_json(self, prompt: str, **kwargs: object) -> dict | list:
        """Return a JSON dict wrapping the prompt."""
        return {"provider": self.prefix, "response": prompt}

    def call_multi_turn(
        self,
        prompt: str,
        *,
        max_turns: int = 10,
        tools: list | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
        system: str | None = None,
        cache: bool = True,
    ) -> str:
        """Simulate a multi-turn conversation by echoing once."""
        return self.call(prompt, tools=tools, timeout=timeout, cwd=cwd, system=system)


# ---------------------------------------------------------------------------
# 2. Register the custom provider
# ---------------------------------------------------------------------------

PROVIDER_CLASSES["echo"] = EchoProvider


# ---------------------------------------------------------------------------
# 3. Use it through the ProviderRegistry
# ---------------------------------------------------------------------------

def main() -> None:
    # Build a config that references our custom provider.
    config = {
        "default_provider": "echo",
        "providers": {
            "echo": {"prefix": "my-custom-llm"},
        },
        "agent_models": {
            "developer": {"model": "large", "provider": "echo"},
            "reviewer": {"model": "small"},
        },
    }

    registry = ProviderRegistry(config)

    # --- text call ---
    result = registry.call("Hello, world!")
    print("Text call (default):", result)

    # --- text call with agent override ---
    result = registry.call("Review this code.", agent="developer")
    print("Text call (developer):", result)

    # --- JSON call ---
    data = registry.call_json("Give me JSON.", agent="reviewer")
    print("JSON call (reviewer):", json.dumps(data, indent=2))

    # --- Direct instantiation ---
    provider = EchoProvider({"prefix": "standalone"})
    print("Direct call:", provider.call("ping"))


if __name__ == "__main__":
    main()
