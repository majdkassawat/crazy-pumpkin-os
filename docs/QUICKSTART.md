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

### Check Pipeline Status

Use the `status` command to see active projects, task breakdown, agent health, and recent activity:

```bash
crazy-pumpkin status
```

For machine-readable output (useful for scripts and CI):

```bash
crazy-pumpkin status --json
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

## Next Steps

- See [PLUGIN_GUIDE.md](../PLUGIN_GUIDE.md) for packaging agents as plugins
- See [GETTING_STARTED.md](../GETTING_STARTED.md) for full project setup
- See [API_DOCS.md](../API_DOCS.md) for detailed API documentation
