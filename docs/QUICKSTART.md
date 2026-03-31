# Quickstart: Build a Custom Agent in 5 Minutes

This tutorial walks you through creating and running a custom agent for Crazy Pumpkin OS.

## 1. Install Crazy Pumpkin OS

```bash
pip install crazypumpkin
```

For development (includes pytest):

```bash
pip install crazypumpkin[dev]
```

## 2. Create Your Agent

Create a file called `my_agent.py`:

```python
from typing import Any

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.framework.registry import register_agent


@register_agent(name="hello-agent", role=AgentRole.EXECUTION)
class HelloAgent(BaseAgent):
    """A minimal agent that greets the user."""

    def setup(self, context: dict[str, Any]) -> None:
        """Called before execute(). Use for initialization."""
        self.greeting = context.get("greeting", "Hello")

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Core logic — process the task and return a result."""
        message = f"{self.greeting}, working on: {task.title}"
        return TaskOutput(
            content=message,
            artifacts={"result.txt": message},
        )

    def teardown(self, context: dict[str, Any]) -> None:
        """Called after execute(), even if it raised an error. Use for cleanup."""
        self.greeting = None
```

### What's happening here?

- **`BaseAgent`** — Abstract base class. Every custom agent must subclass it and implement `execute()`.
- **`execute(task, context)`** — Required. Receives a `Task` and a context dict, returns a `TaskOutput`.
- **`setup(context)`** — Optional. Runs before `execute()`. Use it to initialize resources.
- **`teardown(context)`** — Optional. Runs after `execute()`, guaranteed even on errors. Use it for cleanup.
- **`@register_agent`** — Decorator that automatically creates an `Agent` model and registers the agent in the default registry. Takes a `name` and `role`.

## 3. Run Your Agent Programmatically

Add this to `my_agent.py` or a separate script:

```python
from crazypumpkin.framework.models import Task
from crazypumpkin.framework.registry import default_registry

# The @register_agent decorator already registered HelloAgent.
# Retrieve it by name:
agent = default_registry.by_name("hello-agent")

# Create a task:
task = Task(title="Write a greeting", description="Generate a welcome message")

# run() calls setup -> execute -> teardown automatically:
result = agent.run(task, context={"greeting": "Hi there"})

print(result.content)
# => Hi there, working on: Write a greeting

print(result.artifacts)
# => {'result.txt': 'Hi there, working on: Write a greeting'}
```

## 4. Run Your Agent via the CLI

Register your agent in `config.yaml`:

```yaml
agents:
  - name: "HelloAgent"
    role: execution
    class: "my_agent.HelloAgent"
    model: none
    group: execution
    description: "A custom greeting agent"
```

Then start the pipeline:

```bash
crazy-pumpkin run --once
```

## Retry & Error Recovery

Crazy Pumpkin OS includes built-in retry logic with exponential backoff for agent
operations. Use `RetryPolicy` to control how transient failures are handled.

### Setting a retry policy on an agent

```python
from crazypumpkin.framework.retry import RetryPolicy, with_retry

# Define a custom retry policy
policy = RetryPolicy(
    max_attempts=5,
    base_delay=2.0,
    factor=2.0,
    max_delay=30.0,
)

# Use as a decorator on async functions
@with_retry(policy=policy)
async def call_llm(prompt: str) -> str:
    ...
```

You can also call `retry_async` directly:

```python
from crazypumpkin.framework.retry import RetryPolicy, retry_async

policy = RetryPolicy(max_attempts=3)
result = await retry_async(my_async_fn, arg1, arg2, policy=policy)
```

### RetryPolicy parameters and defaults

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `max_attempts` | `int` | `3` | Total number of attempts (including the first call) |
| `base_delay` | `float` | `1.0` | Initial delay in seconds before the first retry |
| `factor` | `float` | `2.0` | Multiplier applied to the delay after each retry (exponential backoff) |
| `max_delay` | `float` | `60.0` | Upper bound on the delay between retries in seconds |
| `retryable_exceptions` | `Sequence[Type[BaseException]]` | `[TimeoutError, ConnectionError, OSError]` | Exception types that trigger a retry |

### Default retryable exceptions

By default, only transient network/system errors are retried:

- **`TimeoutError`** — request or socket timed out
- **`ConnectionError`** — connection refused, reset, or dropped
- **`OSError`** — low-level I/O errors (includes socket errors)

Any other exception will propagate immediately without retrying.

### Customizing retryable exceptions for LLM providers

Different LLM providers raise different exceptions for rate limits and transient errors.
Override `retryable_exceptions` to match your provider:

```python
# For Anthropic (anthropic SDK)
from anthropic import RateLimitError, APIStatusError

policy = RetryPolicy(
    max_attempts=5,
    base_delay=2.0,
    retryable_exceptions=[RateLimitError, APIStatusError, TimeoutError],
)

# For OpenAI (openai SDK)
from openai import RateLimitError, APITimeoutError

policy = RetryPolicy(
    max_attempts=4,
    base_delay=1.0,
    retryable_exceptions=[RateLimitError, APITimeoutError, ConnectionError],
)
```

## 5. Complete Working Example

Copy this into `my_agent.py` and run it with `python my_agent.py`:

```python
"""Complete working example of a custom Crazy Pumpkin OS agent."""

from typing import Any

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.framework.registry import default_registry, register_agent


@register_agent(name="hello-agent", role=AgentRole.EXECUTION)
class HelloAgent(BaseAgent):
    """A minimal agent that greets the user."""

    def setup(self, context: dict[str, Any]) -> None:
        self.greeting = context.get("greeting", "Hello")

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        message = f"{self.greeting}, working on: {task.title}"
        return TaskOutput(
            content=message,
            artifacts={"result.txt": message},
        )

    def teardown(self, context: dict[str, Any]) -> None:
        self.greeting = None


if __name__ == "__main__":
    # Retrieve the registered agent
    agent = default_registry.by_name("hello-agent")

    # Create and run a task
    task = Task(title="Write a greeting", description="Generate a welcome message")
    result = agent.run(task, context={"greeting": "Hi there"})

    print(f"Content: {result.content}")
    print(f"Artifacts: {result.artifacts}")
```

## API Reference

| Class / Function | Import | Purpose |
| --- | --- | --- |
| `BaseAgent` | `crazypumpkin.framework.agent` | Abstract base class for all agents |
| `Task` | `crazypumpkin.framework.models` | Task dataclass passed to `execute()` |
| `TaskOutput` | `crazypumpkin.framework.models` | Return type of `execute()` |
| `AgentRole` | `crazypumpkin.framework.models` | Enum of agent roles (EXECUTION, STRATEGY, REVIEWER, ...) |
| `Agent` | `crazypumpkin.framework.models` | Agent identity model (name, role, config) |
| `@register_agent` | `crazypumpkin.framework.registry` | Decorator to auto-register an agent class |
| `default_registry` | `crazypumpkin.framework.registry` | The global agent registry instance |
| `RetryPolicy` | `crazypumpkin.framework.retry` | Dataclass configuring retry attempts, delays, and retryable exceptions |
| `retry_async` | `crazypumpkin.framework.retry` | Calls an async function with retry/backoff governed by a `RetryPolicy` |
| `@with_retry` | `crazypumpkin.framework.retry` | Decorator that wraps an async function with retry logic |

## Next Steps

- See [PLUGIN_GUIDE.md](../PLUGIN_GUIDE.md) for packaging agents as plugins
- See [GETTING_STARTED.md](../GETTING_STARTED.md) for full project setup
- See [API_DOCS.md](../API_DOCS.md) for detailed API documentation
