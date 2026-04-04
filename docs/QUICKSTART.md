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

## 6. Set Up Slack Notifications

Crazy Pumpkin OS can send lifecycle alerts (task start/complete/fail, agent
start/complete/fail) and health reports to a Slack channel via an incoming
webhook.

### 6.1 Create a Slack Incoming Webhook

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and create a new app (or use an existing one).
2. Navigate to **Incoming Webhooks** and toggle the feature **On**.
3. Click **Add New Webhook to Workspace**, choose a channel, and authorize.
4. Copy the webhook URL — it looks like `https://hooks.slack.com/services/T.../B.../xxxx`.
5. Store it in an environment variable:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../xxxx"
```

### 6.2 Configure Slack in `config.yaml`

Add a `slack` block inside the `notifications` section of your `config.yaml`:

```yaml
notifications:
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}
    channel: "#cp-alerts"          # optional — override the webhook default
    username: "CrazyPumpkin"       # optional — bot display name
    icon_emoji: ":jack_o_lantern:" # optional — bot avatar emoji
```

| Key | Required | Description |
| --- | --- | --- |
| `webhook_url` | **yes** | Slack incoming webhook URL (use `${ENV_VAR}` syntax) |
| `channel` | no | Channel override (e.g. `#alerts`). Defaults to the webhook's channel. |
| `username` | no | Bot username displayed in Slack |
| `icon_emoji` | no | Emoji used as the bot's avatar |

### 6.3 Channel Routing with the NotificationRouter

The framework provides a `NotificationRouter` that dispatches events to one or
more channels. To set up Slack programmatically:

```python
from crazypumpkin.notifications import configure_slack, get_router

# Option A — automatic setup from config dict
channel = configure_slack({
    "slack": {
        "webhook_url": "https://hooks.slack.com/services/T.../B.../xxxx",
        "channel": "#cp-alerts",
    }
})

# The channel is now registered on the global router.
router = get_router()
print(router.channels)  # [<SlackWebhookChannel ...>]

# Option B — manual setup
from crazypumpkin.notifications.slack import SlackWebhookChannel

alerts = SlackWebhookChannel(
    webhook_url="https://hooks.slack.com/services/T.../B.../xxxx",
    channel="#cp-alerts",
)
router.add_channel(alerts)
```

You can register multiple channels (Slack, email, etc.) on the same router.
Events are broadcast to all of them.

### 6.4 Sending Notifications

```python
from crazypumpkin.notifications import notify

# Lifecycle event — automatically routed to all registered channels
notify({
    "action": "task_complete",
    "entity_id": "task-42",
    "detail": "All tests passed",
})
```

The `SlackWebhookChannel` also supports direct messaging and alert levels:

```python
from crazypumpkin.notifications.slack import SlackWebhookChannel

slack = SlackWebhookChannel(
    webhook_url="https://hooks.slack.com/services/T.../B.../xxxx",
)

# Plain message
slack.send_message("Deployment finished successfully.")

# Alert with severity level (info | warning | error | critical)
slack.send_alert("Disk usage above 90%", level="warning")
```

### 6.5 Batch Messages

To combine multiple messages into a single Slack post (useful during pipeline
cycles):

```python
slack.start_batch()
slack.send_message("Step 1 complete")
slack.send_message("Step 2 complete")
slack.send_alert("Step 3 failed", level="error")
count = slack.flush_batch()  # sends one combined message, returns 3
```

Call `slack.discard_batch()` instead of `flush_batch()` to drop queued
messages without sending.

### 6.6 Test the Integration

**Quick smoke test** — verify your webhook URL works:

```bash
python -c "
from crazypumpkin.notifications.slack import SlackWebhookChannel
ch = SlackWebhookChannel(webhook_url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL')
ch.send_message(':wave: Hello from Crazy Pumpkin OS!')
"
```

If the message appears in your Slack channel, the integration is working.

**End-to-end test** — wire up the router and emit an event:

```python
from crazypumpkin.notifications import configure_slack, notify

configure_slack({
    "slack": {
        "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        "channel": "#cp-alerts",
    }
})

notify({
    "action": "task_complete",
    "entity_id": "test-task-1",
    "detail": "Integration test passed",
})
```

**Unit tests** — run the existing test suite to confirm nothing is broken:

```bash
python -m pytest tests/test_notifications.py tests/test_slack.py -v
```

## Next Steps

- [API Reference](api-reference.md) — Full public API documentation
- [Plugin Development Guide](plugin-guide.md) — Package your agents as plugins
- [CLI Reference](cli-reference.md) — Command-line interface usage
