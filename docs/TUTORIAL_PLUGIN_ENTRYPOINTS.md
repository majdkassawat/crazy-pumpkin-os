# Tutorial: Build and Publish a CP-OS Plugin with Entry Points

This step-by-step tutorial walks you through creating a CP-OS plugin as a
standalone Python package, registering it via setuptools entry points, and
managing it with the CLI.

## Prerequisites

- Python 3.10+
- Crazy Pumpkin OS installed (`pip install crazypumpkin`)
- A working `cpos` CLI (verify with `cpos --help`)

## Step 1: Create the Plugin Package

Create a new directory for your plugin project:

```bash
mkdir cpos-hello-plugin
cd cpos-hello-plugin
```

Create the package structure:

```
cpos-hello-plugin/
  cpos_hello/
    __init__.py
  pyproject.toml
```

```bash
mkdir cpos_hello
touch cpos_hello/__init__.py
```

## Step 2: Define the Plugin Manifest

Edit `cpos_hello/__init__.py` to export a `PluginManifest` and a plugin class:

```python
from crazypumpkin.framework.models import PluginManifest


manifest = PluginManifest(
    name="hello_plugin",
    version="1.0.0",
    description="A greeting plugin for CP-OS",
    entry_point="cpos_hello:HelloPlugin",
    plugin_type="agent",
    min_framework_version="0.1.0",
    permissions=["read"],
    requires=[],
)


class HelloPlugin:
    """A minimal plugin that prints a greeting."""

    def __init__(self):
        self.greeting = "Hello from HelloPlugin!"

    def run(self):
        print(self.greeting)
        return self.greeting
```

### What each manifest field means

| Field | Value | Why |
| --- | --- | --- |
| `name` | `"hello_plugin"` | Unique identifier — must match the entry-point key |
| `version` | `"1.0.0"` | Semver version shown in `cpos list-plugins` |
| `description` | `"A greeting plugin..."` | Human-readable summary |
| `entry_point` | `"cpos_hello:HelloPlugin"` | `module:class` path the framework uses to instantiate |
| `plugin_type` | `"agent"` | Either `"agent"` or `"provider"` |
| `min_framework_version` | `"0.1.0"` | Minimum CP-OS version required |
| `permissions` | `["read"]` | Permissions the plugin requests |
| `requires` | `[]` | Other plugins this one depends on |

## Step 3: Create pyproject.toml

Create `pyproject.toml` in the project root:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "cpos-hello-plugin"
version = "1.0.0"
description = "A greeting plugin for Crazy Pumpkin OS"
requires-python = ">=3.10"
dependencies = ["crazypumpkin>=0.1.0"]

[project.entry-points.'crazypumpkin.plugins']
hello_plugin = "cpos_hello:manifest"
```

The critical section is `[project.entry-points.'crazypumpkin.plugins']`. This
tells setuptools to register `hello_plugin` as a CP-OS plugin. When the
framework scans entry points, it calls `ep.load()` which resolves
`cpos_hello:manifest` — the `PluginManifest` object you defined in Step 2.

## Step 4: Install the Plugin in Development Mode

From the `cpos-hello-plugin/` directory:

```bash
pip install -e .
```

Expected output:

```
Successfully installed cpos-hello-plugin-1.0.0
```

The `-e` (editable) flag means changes to `cpos_hello/__init__.py` take effect
immediately without reinstalling.

## Step 5: Verify with `cpos list-plugins`

Run:

```bash
cpos list-plugins
```

Expected output:

```
Name                           Version      Type         Status
--------------------------------------------------------------
hello_plugin                   1.0.0        agent        ok
```

Your plugin appears in the list with status `ok`. If it does not appear, check:

1. The virtualenv is activated (same one where `crazypumpkin` is installed).
2. The entry-point group name is exactly `crazypumpkin.plugins`.
3. You ran `pip install -e .` successfully.

## Step 6: Load the Plugin Programmatically

Create a test script `try_plugin.py`:

```python
from crazypumpkin.framework.plugin_loader import (
    discover_plugins,
    validate_plugin,
    load_plugin,
)

# Discover all installed plugins
manifests = discover_plugins()
print(f"Found {len(manifests)} plugin(s):\n")

for m in manifests:
    print(f"  Name:        {m.name}")
    print(f"  Version:     {m.version}")
    print(f"  Type:        {m.plugin_type}")
    print(f"  Entry point: {m.entry_point}")

    # Validate the manifest
    errors = validate_plugin(m)
    if errors:
        print(f"  Errors:      {errors}")
    else:
        print(f"  Valid:       yes")

    # Load and instantiate the plugin
    obj = load_plugin(m)
    if obj is not None:
        print(f"  Loaded:      {obj}")
        if hasattr(obj, "run"):
            result = obj.run()
            print(f"  Run result:  {result}")

    print()
```

Run it:

```bash
python try_plugin.py
```

Expected output:

```
Found 1 plugin(s):

  Name:        hello_plugin
  Version:     1.0.0
  Type:        agent
  Entry point: cpos_hello:HelloPlugin
  Valid:       yes
  Loaded:      <cpos_hello.HelloPlugin object at 0x...>
Hello from HelloPlugin!
  Run result:  Hello from HelloPlugin!
```

## Step 7: Use PluginLoader with Config Overrides

If you need to override an entry-point plugin with a config-defined version,
use `PluginLoader` directly:

```python
from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_loader import PluginLoader

# Override hello_plugin with a custom config version
config_override = PluginManifest(
    name="hello_plugin",
    version="9.9.9",
    entry_point="cpos_hello:HelloPlugin",
    plugin_type="provider",
)

loader = PluginLoader(config_plugins=[config_override])
plugins = loader.discover_entrypoint_plugins()

for p in plugins:
    print(f"{p.name} v{p.version} type={p.plugin_type}")
```

Expected output:

```
hello_plugin v9.9.9 type=provider
```

The config-defined manifest takes precedence — the entry point's `load()` is
never called for plugins whose name matches a config plugin.

## Step 8: Add a Dependency Between Plugins

If your plugin depends on another plugin, declare it in the `requires` field:

```python
manifest = PluginManifest(
    name="advanced_plugin",
    version="1.0.0",
    entry_point="my_advanced:AdvancedPlugin",
    plugin_type="agent",
    requires=["hello_plugin>=1.0.0"],
)
```

When `load_plugin()` is called, it checks that `hello_plugin` version 1.0.0 or
higher is available. If not, loading fails with a descriptive error:

```
Plugin 'advanced_plugin' dependency check failed: Required plugin 'hello_plugin' is not available
```

To satisfy the dependency, pass the available plugins map:

```python
from crazypumpkin.framework.plugin_loader import load_plugin

obj = load_plugin(manifest, available_plugins={"hello_plugin": "1.0.0"})
```

## Step 9: Uninstall the Plugin

```bash
cpos remove-plugin cpos-hello-plugin
```

Expected output:

```
Uninstalling package 'cpos-hello-plugin' ...
Successfully uninstalled cpos-hello-plugin-1.0.0
Plugin 'cpos-hello-plugin' removed.
```

Verify it is gone:

```bash
cpos list-plugins
```

Expected output:

```
No plugins found.
```

## Step 10: Publish to PyPI (Optional)

Once your plugin is ready for others to use, publish it:

```bash
pip install build twine
python -m build
twine upload dist/*
```

Users can then install your plugin with:

```bash
cpos install-plugin cpos-hello-plugin
```

The framework will automatically discover it via entry points — no config file
changes needed on the user's side.

## Summary

| Step | What you did |
| --- | --- |
| 1-2 | Created a Python package with a `PluginManifest` and plugin class |
| 3 | Declared the `crazypumpkin.plugins` entry point in `pyproject.toml` |
| 4 | Installed in editable mode with `pip install -e .` |
| 5 | Verified discovery with `cpos list-plugins` |
| 6 | Loaded and ran the plugin programmatically |
| 7 | Used `PluginLoader` config overrides |
| 8 | Declared inter-plugin dependencies |
| 9 | Removed the plugin with `cpos remove-plugin` |
| 10 | Published to PyPI for third-party adoption |

## Troubleshooting

See [PLUGIN_ENTRYPOINTS.md](PLUGIN_ENTRYPOINTS.md) for common errors and fixes,
including ImportError, missing manifest fields, invalid `plugin_type`, framework
version mismatches, and instantiation failures.
