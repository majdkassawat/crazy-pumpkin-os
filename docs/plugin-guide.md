# CP-OS Plugin Development Guide

This guide covers how to build, package, and register plugins for the
Crazy Pumpkin OS framework.

---

## 1. Plugin Structure

A plugin is a Python module (or package) that the framework discovers at
startup.  The minimal directory layout for a file-based plugin:

```
src/crazypumpkin/plugins/
├── __init__.py
└── my_plugin.py          # Your plugin module
```

For a **packaged** plugin distributed as a separate Python package:

```
my-cpos-plugin/
├── pyproject.toml        # with entry_points metadata
├── src/
│   └── my_plugin/
│       ├── __init__.py
│       └── agent.py      # contains the Plugin class
└── tests/
    └── test_plugin.py
```

### Manifest Fields

Every plugin is described by a `PluginManifest` (defined in
`crazypumpkin.framework.models`):

| Field                   | Type         | Required | Description                                           |
|-------------------------|--------------|----------|-------------------------------------------------------|
| `name`                  | `str`        | Yes      | Unique plugin identifier                              |
| `version`               | `str`        | Yes      | Semver version string (e.g. `"1.0.0"`)                |
| `description`           | `str`        | No       | Human-readable summary                                |
| `entry_point`           | `str`        | Yes      | Dotted module path, optionally with `:attribute`       |
| `plugin_type`           | `str`        | Yes      | Either `"agent"` or `"provider"`                      |
| `min_framework_version` | `str`        | No       | Minimum CP-OS version required (e.g. `"0.1.0"`)       |
| `permissions`           | `list[str]`  | No       | Requested sandbox permissions                         |
| `requires`              | `list[str]`  | No       | Dependency specs (e.g. `["crazypumpkin>=0.1.0"]`)      |

The four **required** fields are enforced by `validate_plugin()` in
`crazypumpkin.framework.plugin_loader`.

---

## 2. Writing a Plugin Agent

Plugin agents subclass `BaseAgent` from `crazypumpkin.framework.agent`.
You must implement the `execute()` method:

```python
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


class Plugin(BaseAgent):
    """A minimal plugin agent."""

    def execute(self, task: Task, context: dict) -> TaskOutput:
        # Your logic here
        return TaskOutput(content=f"Handled: {task.title}")
```

Key points:

- The class **must** be named `Plugin` (convention) or you must specify
  the class name via the `entry_point` field using `module:ClassName` syntax.
- `BaseAgent.__init__` expects an `Agent` model instance.  The framework
  creates this for you during `load_plugin()`.
- Override `setup()` and `teardown()` for lifecycle hooks that run before
  and after `execute()`.
- Override `can_handle(task)` to declare which tasks the agent supports.

### Using the `@register_agent` Decorator

You can also register your plugin agent with the framework registry:

```python
from crazypumpkin.framework.registry import register_agent
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import AgentRole, Task, TaskOutput


@register_agent(name="my-plugin-agent", role=AgentRole.EXECUTION)
class MyPluginAgent(BaseAgent):
    def execute(self, task: Task, context: dict) -> TaskOutput:
        return TaskOutput(content="done")
```

---

## 3. Plugin Discovery and Registration

The framework discovers plugins through two mechanisms, both implemented
in `discover_plugins()` (`crazypumpkin.framework.plugin_loader`):

### 3a. Entry-Point Based Discovery

Register your plugin as a Python entry point in `pyproject.toml`:

```toml
[project.entry-points."crazypumpkin.plugins"]
my-plugin = "my_plugin.agent"
```

The entry-point group must be `crazypumpkin.plugins` (defined as
`ENTRY_POINT_GROUP` in `plugin_loader.py`).  The framework reads these
via `importlib.metadata.entry_points()`.

Each entry point yields a `PluginManifest` with:
- `name` = the entry-point name (e.g. `"my-plugin"`)
- `entry_point` = the entry-point value (e.g. `"my_plugin.agent"`)
- `plugin_type` = `"agent"` (default)

### 3b. File-Based Discovery

Drop a `.py` file into the `src/crazypumpkin/plugins/` directory.  The
framework scans this directory and creates a manifest for every `.py`
file that is **not** `__init__.py`.

For example, placing `hello.py` in the plugins directory produces:
- `name` = `"hello"`
- `entry_point` = `"crazypumpkin.plugins.hello"`
- `plugin_type` = `"agent"`

You can also point `discover_plugins()` at a custom directory via its
`plugins_dir` parameter.

### Loading

After discovery, call `load_plugin(manifest)` to validate, check
dependencies, import the module, and instantiate the plugin class:

```python
from crazypumpkin.framework.plugin_loader import discover_plugins, load_plugin

manifests = discover_plugins()
for manifest in manifests:
    plugin = load_plugin(manifest)
    if plugin is not None:
        print(f"Loaded: {manifest.name}")
```

The `load_plugin` function:
1. Runs `validate_plugin()` — checks all required manifest fields and
   `plugin_type` validity.
2. Runs `check_requires()` — verifies dependency constraints against
   available plugins and the framework version.
3. Imports the module specified in `entry_point`.
4. Looks for a `Plugin` class (or a named attribute if `entry_point`
   uses `module:ClassName` syntax).
5. Instantiates the class inside `_sandbox_call()` to catch errors.

---

## 4. Sandbox Restrictions and Permissions

Plugin code executes inside a sandbox defined in
`crazypumpkin.plugins.sandbox`.  The sandbox enforces three resource
constraints:

### Timeout

Plugins are executed in a daemon thread with a configurable timeout
(default: **60 seconds**, set by `DEFAULT_TIMEOUT_SEC`).  If the plugin
does not finish in time, a `PluginTimeoutError` is raised.

### Memory Limit

Before and after execution, memory usage is checked against a cap
(default: **256 MB**, set by `DEFAULT_MEMORY_LIMIT_MB`).  Exceeding
the limit raises `PluginMemoryError`.

### Import Restrictions

An import guard replaces `builtins.__import__` during plugin execution.
Plugins may **only** import from the public API modules:

- `crazypumpkin`
- `crazypumpkin.framework`
- `crazypumpkin.framework.models`
- `crazypumpkin.framework.events`
- `crazypumpkin.framework.registry`

Any attempt to import other `crazypumpkin.*` internal modules raises
`PluginImportError`.  Third-party and standard-library imports are
unrestricted.

### Configuring the Sandbox

Pass a `SandboxConfig` to `run_sandboxed()` to customise limits:

```python
from crazypumpkin.plugins.sandbox import SandboxConfig, run_sandboxed

config = SandboxConfig(
    timeout_sec=30,
    memory_limit_mb=128,
    allowed_modules=frozenset({
        "crazypumpkin",
        "crazypumpkin.framework",
        "crazypumpkin.framework.models",
        "crazypumpkin.framework.events",
        "crazypumpkin.framework.registry",
    }),
)

result = run_sandboxed(
    plugin_name="my-plugin",
    func=my_plugin_callable,
    args=(task, context),
    config=config,
)
```

### Sandbox Exception Types

| Exception             | Trigger                                      |
|-----------------------|----------------------------------------------|
| `PluginTimeoutError`  | Execution exceeds `timeout_sec`              |
| `PluginMemoryError`   | Memory usage exceeds `memory_limit_mb`       |
| `PluginImportError`   | Plugin imports a restricted internal module   |

---

## 5. Complete Minimal Plugin Example

Below is a full, working plugin that can be dropped into
`src/crazypumpkin/plugins/greeting.py`:

```python
"""greeting — A minimal CP-OS plugin example."""

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


class Plugin(BaseAgent):
    """Greeting plugin agent that responds with a friendly message."""

    def setup(self, context: dict) -> None:
        """Prepare any resources before execution."""
        self._greeting = context.get("greeting", "Hello")

    def execute(self, task: Task, context: dict) -> TaskOutput:
        """Handle the task by producing a greeting."""
        message = f"{self._greeting}, {task.title}!"
        return TaskOutput(content=message)

    def teardown(self, context: dict) -> None:
        """Clean up after execution."""
        self._greeting = None

    def can_handle(self, task: Task) -> bool:
        """Only handle tasks with 'greet' in the title."""
        return "greet" in task.title.lower()
```

### Using the Plugin Programmatically

```python
from crazypumpkin.framework.models import Agent, AgentRole, Task, PluginManifest
from crazypumpkin.framework.plugin_loader import discover_plugins, load_plugin

# Discover all plugins (including our greeting.py)
manifests = discover_plugins()

# Or create a manifest manually
manifest = PluginManifest(
    name="greeting",
    version="1.0.0",
    entry_point="crazypumpkin.plugins.greeting",
    plugin_type="agent",
)

# Load and use the plugin
plugin = load_plugin(manifest)
if plugin is not None:
    task = Task(title="greet the world")
    output = plugin.run(task, context={"greeting": "Hi"})
    print(output.content)  # "Hi, greet the world!"
```

### Packaging as an Entry-Point Plugin

To distribute your plugin as a separate package, define the entry point
in `pyproject.toml`:

```toml
[project]
name = "cpos-greeting-plugin"
version = "1.0.0"

[project.entry-points."crazypumpkin.plugins"]
greeting = "cpos_greeting.agent:Plugin"
```

The framework will discover it via `importlib.metadata.entry_points()`
under the `crazypumpkin.plugins` group.

---

## 6. Testing Your Plugin

### Unit Testing

Test your plugin in isolation using standard pytest:

```python
import pytest
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


def test_greeting_plugin():
    # Import the plugin class directly
    from crazypumpkin.plugins.greeting import Plugin

    agent_model = Agent(id="test-001", name="test-greeting", role=AgentRole.EXECUTION)
    plugin = Plugin(agent_model)

    task = Task(title="greet everyone")
    context = {"greeting": "Hey"}

    output = plugin.execute(task, context)
    assert "Hey" in output.content
    assert "greet everyone" in output.content


def test_can_handle():
    from crazypumpkin.plugins.greeting import Plugin

    agent_model = Agent(id="test-002", name="test-greeting", role=AgentRole.EXECUTION)
    plugin = Plugin(agent_model)

    assert plugin.can_handle(Task(title="greet users"))
    assert not plugin.can_handle(Task(title="deploy service"))
```

### Testing Plugin Discovery

```python
from crazypumpkin.framework.plugin_loader import discover_plugins, validate_plugin
from crazypumpkin.framework.models import PluginManifest


def test_plugin_discovered():
    manifests = discover_plugins()
    names = [m.name for m in manifests]
    assert "greeting" in names


def test_manifest_valid():
    manifest = PluginManifest(
        name="greeting",
        version="1.0.0",
        entry_point="crazypumpkin.plugins.greeting",
        plugin_type="agent",
    )
    errors = validate_plugin(manifest)
    assert errors == []
```

### Testing Sandbox Behaviour

```python
from crazypumpkin.plugins.sandbox import run_sandboxed, SandboxConfig, PluginTimeoutError
import pytest


def test_sandbox_timeout():
    import time

    def slow_func():
        time.sleep(10)

    config = SandboxConfig(timeout_sec=0.1)
    with pytest.raises(PluginTimeoutError):
        run_sandboxed("test-plugin", slow_func, config=config)
```

### Running Tests

```bash
# Run all plugin-related tests
python -m pytest tests/test_plugin_loader.py tests/test_sandbox.py -v

# Run only your plugin's tests
python -m pytest tests/test_greeting_plugin.py -v
```
