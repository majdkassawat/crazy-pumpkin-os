# Plugin Development Guide

Build and submit plugins for Crazy Pumpkin OS.

## What Is a Plugin?

A plugin extends the framework with new capabilities without modifying core code. Common plugin types:

- **Agent plugins** — New specialized agents (e.g., a Jira sync agent)
- **LLM provider plugins** — Support for additional LLM backends
- **Notification plugins** — New alert channels (Slack, Discord, email)
- **Integration plugins** — Connect to external services

## Plugin Structure

```
src/crazypumpkin/plugins/my_plugin/
    __init__.py
    plugin.py          # Main plugin class
    config.py          # Plugin configuration
    tests/
        test_plugin.py # Plugin tests
    README.md          # Plugin documentation
```

## Creating an Agent Plugin

Agent plugins extend `BaseAgent`:

```python
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Task, TaskOutput

class MyCustomAgent(BaseAgent):
    """Description of what this agent does."""

    def execute(self, task: Task, context: dict) -> TaskOutput:
        # Your agent logic here
        return TaskOutput(
            content="Result description",
            artifacts={},  # {filename: content} if files were created
            metadata={},
        )
```

Register in your config.yaml:

```yaml
agents:
  - name: "MyAgent"
    role: "custom"
    class: "crazypumpkin.plugins.my_plugin.plugin.MyCustomAgent"
    model: "sonnet"
    trigger:
      expression: "always"
      cooldown_sec: 300
```

## Creating a Notification Plugin

Notification plugins implement a simple send interface:

```python
class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        import httpx
        response = httpx.post(self.webhook_url, json={"text": message})
        return response.status_code == 200
```

## Creating an LLM Provider Plugin

LLM providers extend the base provider:

```python
from crazypumpkin.llm.base import LLMProvider

class MyProvider(LLMProvider):
    def call(self, prompt: str, model: str, **kwargs) -> str:
        # Call your LLM API
        return response_text

    def call_json(self, prompt: str, model: str, **kwargs) -> dict:
        # Call and parse JSON response
        return parsed_json
```

Register in config.yaml:

```yaml
llm:
  provider: "my_provider"
  api_key: "${MY_PROVIDER_API_KEY}"
```

## Testing Your Plugin

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run your plugin tests
python -m pytest src/crazypumpkin/plugins/my_plugin/tests/ -v

# Run the full test suite to ensure nothing is broken
python -m pytest tests/ -v --tb=short
```

## Submitting Your Plugin

1. Follow [CONTRIBUTING.md](CONTRIBUTING.md) guidelines
2. Create a PR with your plugin in `src/crazypumpkin/plugins/`
3. Include tests with at least 80% coverage
4. Include a README.md in your plugin directory
5. Add configuration examples to `examples/`
6. All existing tests must still pass

Plugin PRs are typically Tier 1 (auto-approvable) if they:
- Only add new files (no modifications to existing code)
- Include comprehensive tests
- Follow the plugin structure above
