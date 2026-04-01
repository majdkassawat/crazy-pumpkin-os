# LLM Provider Registry API

The `crazypumpkin.llm` package provides a unified interface for calling large
language models from multiple backends.  All providers implement the same
`LLMProvider` abstract base class so they can be swapped without changing
application code.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Provider Registration](#provider-registration)
3. [Built-in Providers](#built-in-providers)
   - [Anthropic](#anthropic-provider)
   - [OpenAI](#openai-provider)
   - [Ollama (local models)](#ollama-provider)
4. [Creating a Custom Provider](#creating-a-custom-provider)
5. [Fallback Chains](#fallback-chains)
6. [Cost Tracking](#cost-tracking)
7. [Configuration Reference](#configuration-reference)

---

## Quick Start

```python
from crazypumpkin.llm import ProviderRegistry

config = {
    "default_provider": "anthropic_api",
    "providers": {
        "anthropic_api": {"api_key": "sk-ant-..."},
    },
}

registry = ProviderRegistry(config)
answer = registry.call("Summarise this code", agent="developer")
print(answer)
```

---

## Provider Registration

`ProviderRegistry` is the central router.  It reads a config dict, instantiates
each declared provider once, and dispatches calls to the correct backend based
on agent role.

```python
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

registry = ProviderRegistry(config)
```

### How provider lookup works

1. `registry.call(prompt, agent="developer")` looks up `agent_models["developer"]`.
2. If the agent entry specifies a `"provider"` key, that backend is used;
   otherwise the `"default_provider"` is used.
3. If the agent entry specifies a `"model"` key, it is passed to the provider;
   otherwise the provider uses its own default model.
4. A `model` keyword passed directly to `call()` takes precedence over the
   agent model mapping.

### Getting a provider instance directly

```python
provider, model_override = registry.get_provider("developer")
# provider is the LLMProvider instance
# model_override is the model string from agent_models (or None)
```

---

## Built-in Providers

All providers implement the `LLMProvider` abstract class which exposes three
methods:

| Method            | Returns      | Description                                      |
|-------------------|--------------|--------------------------------------------------|
| `call()`          | `str`        | Single-turn text completion                      |
| `call_json()`     | `dict\|list` | Single-turn completion parsed as JSON             |
| `call_multi_turn()` | `str`     | Agentic loop with tool use until model stops      |

### Anthropic Provider

Backend: Anthropic Messages API (`anthropic` package).

```python
from crazypumpkin.llm.anthropic_api import AnthropicProvider

provider = AnthropicProvider({"api_key": "sk-ant-..."})

# Simple text call
result = provider.call("What is 2+2?", model="sonnet")

# JSON response
data = provider.call_json("Return {\"answer\": 4}")

# With system prompt and prompt caching
result = provider.call(
    "Explain this code",
    model="sonnet",
    system="You are a code reviewer.",
    cache=True,   # enables Anthropic prompt caching (default)
)

# Cost-tracked call
text, cost = provider.call_with_cost("Hello", model="sonnet")
print(cost.prompt_tokens, cost.completion_tokens, cost.cost_usd)
```

**Model aliases:**

| Alias    | Resolves to                    |
|----------|--------------------------------|
| `opus`   | `claude-opus-4-6`              |
| `sonnet` | `claude-sonnet-4-6`            |
| `haiku`  | `claude-haiku-4-5-20251001`    |
| `smart`  | `claude-sonnet-4-6`            |
| `fast`   | `claude-haiku-4-5-20251001`    |

**Multi-turn with tools:**

```python
from crazypumpkin.llm.tools import STANDARD_TOOLS

def executor(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return a string result."""
    if tool_name == "Bash":
        import subprocess
        return subprocess.check_output(
            tool_input["command"], shell=True, text=True
        )
    return "ok"

result = provider.call_multi_turn(
    "List Python files in the current directory",
    tools=STANDARD_TOOLS,
    tool_executor=executor,
    max_turns=5,
)
```

### OpenAI Provider

Backend: OpenAI Chat Completions API (`openai` package).  This is an optional
dependency — import is conditional.

```python
from crazypumpkin.llm.openai_api import OpenAIProvider

provider = OpenAIProvider({"api_key": "sk-..."})

# Simple text call
result = provider.call("What is 2+2?", model="gpt-4o")

# JSON response (uses response_format=json_object)
data = provider.call_json("Return {\"answer\": 4}")

# Cost-tracked call
text, cost = provider.call_with_cost("Hello", model="gpt-4o")
print(cost.prompt_tokens, cost.completion_tokens, cost.cost_usd)
```

**Model aliases:**

| Alias   | Resolves to    |
|---------|----------------|
| `smart` | `gpt-4o`       |
| `fast`  | `gpt-4o-mini`  |

**Tool-use note:** Anthropic-format tool schemas are automatically converted to
OpenAI function-calling format, so you can use the same `STANDARD_TOOLS` list
with both providers.

### Ollama Provider

Ollama support uses the OpenAI-compatible API that Ollama exposes locally.
Point the OpenAI provider at the Ollama base URL:

```python
from crazypumpkin.llm.openai_api import OpenAIProvider

provider = OpenAIProvider({
    "api_key": "ollama",            # Ollama ignores the key
    "model": "llama3",
})
# The underlying OpenAI client will use OPENAI_BASE_URL if set,
# or you can configure it at the environment level:
#   export OPENAI_BASE_URL=http://localhost:11434/v1

result = provider.call("Summarise this file")
```

In `config.yaml`:

```yaml
llm:
  default_provider: ollama
  providers:
    ollama:
      api_key: "ollama"
      model: "llama3"
```

> **Note:** Register an Ollama provider in `PROVIDER_CLASSES` under the key
> `"ollama"` by subclassing or reusing `OpenAIProvider` with the appropriate
> base URL.  The registry looks up provider classes by name from
> `crazypumpkin.llm.registry.PROVIDER_CLASSES`.

---

## Creating a Custom Provider

Subclass `LLMProvider` and implement the three abstract methods:

```python
from crazypumpkin.llm.base import LLMProvider

class MyProvider(LLMProvider):
    def __init__(self, config: dict | None = None) -> None:
        config = config or {}
        self._api_key = config.get("api_key")

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
        # Implement your API call here
        return "response text"

    def call_json(self, prompt: str, **kwargs) -> dict | list:
        import json
        return json.loads(self.call(prompt, **kwargs))

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
        # Implement agentic loop or fall back to single-turn
        return self.call(prompt, tools=tools, timeout=timeout, cwd=cwd)
```

### Registering the custom provider

Add the class to `PROVIDER_CLASSES` so the registry can instantiate it:

```python
from crazypumpkin.llm.registry import PROVIDER_CLASSES

PROVIDER_CLASSES["my_provider"] = MyProvider
```

Then reference it in config:

```yaml
llm:
  default_provider: my_provider
  providers:
    my_provider:
      api_key: "..."
```

### Adding cost tracking (optional)

Implement `call_with_cost` to let the registry track spend per agent:

```python
from crazypumpkin.llm.base import CallCost

class MyProvider(LLMProvider):
    # ... (other methods) ...

    def call_with_cost(
        self, prompt: str, *, model: str | None = None, **kwargs
    ) -> tuple[str, CallCost]:
        text = self.call(prompt, model=model, **kwargs)
        cost = CallCost(
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.002,
        )
        return text, cost
```

When `call_with_cost` exists on a provider, `ProviderRegistry.call()` will
automatically use it and record the spend to the store.

---

## Fallback Chains

A `FallbackChain` tries multiple providers in order with configurable retries
and exponential backoff.  If all providers are exhausted, an
`AllProvidersExhaustedError` is raised.

```python
import asyncio
from crazypumpkin.llm.registry import (
    FallbackChain,
    RetryPolicy,
    ProviderRegistry,
    AllProvidersExhaustedError,
)

config = {
    "default_provider": "anthropic_api",
    "providers": {
        "anthropic_api": {"api_key": "sk-ant-..."},
        "openai_api":    {"api_key": "sk-..."},
    },
}

registry = ProviderRegistry(config)

chain = FallbackChain(
    provider_names=["anthropic_api", "openai_api"],
    retry_policy=RetryPolicy(
        max_retries=3,          # attempts per provider
        base_delay=1.0,         # initial delay in seconds
        max_delay=30.0,         # delay cap
        exponential_base=2.0,   # multiplier per retry
    ),
)

async def main():
    try:
        result = await registry.call_with_fallback(
            chain,
            messages=[{"role": "user", "content": "Hello"}],
        )
        print(result["provider"], result["result"])
    except AllProvidersExhaustedError as exc:
        print("All providers failed:", exc)

asyncio.run(main())
```

### RetryPolicy

| Field              | Default | Description                                     |
|--------------------|---------|-------------------------------------------------|
| `max_retries`      | `3`     | Number of attempts per provider                 |
| `base_delay`       | `1.0`   | Initial backoff delay in seconds                |
| `max_delay`        | `30.0`  | Maximum backoff delay in seconds                |
| `exponential_base` | `2.0`   | Multiplier applied each retry (`delay * base^n`)|

The delay for attempt *n* (0-indexed) is
`min(base_delay * exponential_base^n, max_delay)`.

---

## Cost Tracking

### Per-call costs

Providers that implement `call_with_cost()` return a `CallCost` dataclass:

```python
from crazypumpkin.llm.base import CallCost

# Returned by provider.call_with_cost()
cost = CallCost(
    prompt_tokens=150,
    completion_tokens=80,
    cost_usd=0.003,
    cache_creation_tokens=0,
    cache_read_tokens=50,
)
```

### Global CostTracker

The `CostTracker` singleton accumulates costs across all calls in a
thread-safe manner:

```python
from crazypumpkin.llm.base import CallCost, CostTracker, get_default_tracker

tracker = get_default_tracker()

# Record a call
tracker.record("claude-sonnet-4-6", CallCost(
    prompt_tokens=200,
    completion_tokens=100,
    cost_usd=0.002,
))

# Get aggregated summary
summary = tracker.get_summary()
print(summary)
# {
#     "total_cost_usd": 0.002,
#     "call_count": 1,
#     "total_prompt_tokens": 200,
#     "total_completion_tokens": 100,
#     "total_cache_creation_tokens": 0,
#     "total_cache_read_tokens": 0,
#     "by_model": {
#         "claude-sonnet-4-6": {
#             "total_cost_usd": 0.002,
#             "call_count": 1,
#             "total_prompt_tokens": 200,
#             "total_completion_tokens": 100,
#             "total_cache_creation_tokens": 0,
#             "total_cache_read_tokens": 0,
#         }
#     }
# }

# Reset counters
tracker.reset()
```

### Per-agent budget enforcement

When a `Store` is provided to the registry, calls through
`ProviderRegistry.call()` automatically record spend per agent.  Combined with
`AgentConfig.monthly_budget_usd`, the registry raises `BudgetExceededError`
when an agent exceeds its cap:

```python
from crazypumpkin.framework.models import AgentConfig, BudgetExceededError

agent_cfg = AgentConfig(
    name="developer",
    monthly_budget_usd=10.0,
    # ... other fields ...
)

try:
    registry.call(
        "Write a feature",
        agent="developer",
        agent_config=agent_cfg,
    )
except BudgetExceededError as exc:
    print(f"Agent {exc.agent} spent ${exc.spent:.2f} of ${exc.budget:.2f}")
```

### Pricing tables

**Anthropic** (per million tokens):

| Model                        | Input   | Output  |
|------------------------------|---------|---------|
| `claude-opus-4-6`            | $15.00  | $75.00  |
| `claude-sonnet-4-6`          | $3.00   | $15.00  |
| `claude-haiku-4-5-20251001`  | $0.25   | $1.25   |

**OpenAI** (per million tokens):

| Model           | Input  | Output |
|-----------------|--------|--------|
| `gpt-4o`        | $2.50  | $10.00 |
| `gpt-4o-mini`   | $0.15  | $0.60  |
| `gpt-4-turbo`   | $10.00 | $30.00 |
| `gpt-4`         | $30.00 | $60.00 |
| `gpt-3.5-turbo` | $0.50  | $1.50  |

---

## Configuration Reference

Full `config.yaml` LLM section:

```yaml
llm:
  # Which provider to use when an agent has no explicit mapping
  default_provider: anthropic_api

  # Provider credentials and settings
  providers:
    anthropic_api:
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-sonnet-4-6       # optional default model override
    openai_api:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4o                  # optional default model override
    # ollama:
    #   api_key: "ollama"
    #   model: "llama3"

  # Per-agent model and provider overrides
  agent_models:
    developer:      { model: sonnet }
    strategist:     { model: claude-sonnet-4-6 }
    reviewer:       { model: claude-sonnet-4-6, provider: openai_api }
```

### Environment variables

| Variable            | Used by                   |
|---------------------|---------------------------|
| `ANTHROPIC_API_KEY` | `AnthropicProvider`       |
| `OPENAI_API_KEY`    | `OpenAIProvider`          |
| `OPENAI_BASE_URL`   | `OpenAIProvider` (Ollama) |
