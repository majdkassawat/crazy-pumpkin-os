# Entry-Point Plugin Discovery and CLI Plugin Management

## Overview

Crazy Pumpkin OS supports automatic plugin discovery via Python
[setuptools entry points](https://packaging.python.org/en/latest/specifications/entry-points/).
External Python packages can register themselves as CP-OS plugins by declaring
an entry point in the `crazypumpkin.plugins` group. The framework discovers
these plugins at startup without any manual configuration file edits.

The CLI provides three commands for managing the plugin lifecycle:

| Command | Purpose |
| --- | --- |
| `cpos list-plugins` | Discover and display all installed plugins |
| `cpos install-plugin <package>` | Install a plugin package and validate it |
| `cpos remove-plugin <package>` | Uninstall a plugin package |

This feature is the critical enabler for third-party ecosystem adoption — plugin
authors publish standard Python packages and users install them with pip.

## How Entry-Point Discovery Works

When the framework starts (or `list-plugins` is invoked), the
`PluginLoader.discover_entrypoint_plugins()` method scans all installed Python
packages for entry points in the `crazypumpkin.plugins` group using
`importlib.metadata.entry_points`.

The discovery process for each entry point:

1. **Config override check** — If a config-file plugin with the same name was
   provided at construction time, it takes precedence and the entry point's
   `load()` is never called.
2. **Load the entry point** — `ep.load()` is called, which imports the target
   module and returns the referenced object.
3. **Manifest coercion** — The loaded object is coerced into a `PluginManifest`:
   - If it is already a `PluginManifest` instance, it is used directly.
   - If it is a `dict`, it is unpacked as `PluginManifest(**loaded)`.
   - Otherwise, a minimal manifest is created with the entry-point name and value.
4. **Error handling** — `ImportError` and other exceptions are caught and logged
   as warnings; broken plugins do not crash the framework.

The standalone `discover_plugins()` function combines entry-point discovery with
a local-directory scan (`src/crazypumpkin/plugins/`) and returns a merged list.

## API Surface

### Module: `crazypumpkin.framework.plugin_loader`

#### Constants

| Name | Value | Description |
| --- | --- | --- |
| `FRAMEWORK_VERSION` | `"0.1.0"` | Current framework version used for compatibility checks |
| `ENTRY_POINT_GROUP` | `"crazypumpkin.plugins"` | The setuptools entry-point group scanned for plugins |
| `REQUIRED_MANIFEST_FIELDS` | `("name", "version", "entry_point", "plugin_type")` | Fields that must be non-empty for a manifest to pass validation |

#### `discover_plugins(plugins_dir=None) -> list[PluginManifest]`

Discover plugins from both entry points and a local plugins directory.

**Parameters:**
- `plugins_dir` (str | Path | None) — Path to a local plugins directory. Defaults
  to `src/crazypumpkin/plugins/`.

**Returns:** A list of `PluginManifest` instances.

#### `validate_plugin(manifest) -> list[str]`

Validate a plugin manifest against the required fields and framework version
constraints.

**Parameters:**
- `manifest` (PluginManifest) — The manifest to validate.

**Returns:** A list of error strings. Empty means valid.

**Checks performed:**
- All four required fields (`name`, `version`, `entry_point`, `plugin_type`)
  must be non-empty.
- `plugin_type` must be `"agent"` or `"provider"`.
- If `min_framework_version` is set, it must be <= `FRAMEWORK_VERSION`.

#### `load_plugin(manifest, available_plugins=None) -> Any`

Import and instantiate the plugin described by a manifest.

**Parameters:**
- `manifest` (PluginManifest) — The manifest describing the plugin.
- `available_plugins` (dict[str, str] | None) — Mapping of plugin name to
  version for already-loaded plugins, used for `requires` constraint checking.

**Returns:** The instantiated plugin object, or `None` on failure.

**Behaviour:**
1. Validates the manifest via `validate_plugin()`.
2. Checks dependency constraints via `check_requires()`.
3. Imports the module from `manifest.entry_point` (`module.path:ClassName`).
4. Instantiates the class inside `_sandbox_call()` which catches exceptions.

#### `check_requires(manifest, available_plugins=None, framework_version=None) -> list[str]`

Check whether a plugin's `requires` dependencies are satisfied.

**Parameters:**
- `manifest` (PluginManifest) — The manifest to check.
- `available_plugins` (dict[str, str] | None) — Available plugin name-to-version map.
- `framework_version` (str | None) — Override for the current framework version.

**Returns:** A list of error strings. Empty means all requirements met.

#### `class PluginLoader`

High-level plugin discovery and loading.

```python
loader = PluginLoader(config_plugins=[...])
manifests = loader.discover_entrypoint_plugins(group="crazypumpkin.plugins")
```

**Constructor Parameters:**
- `config_plugins` (list[PluginManifest] | None) — Plugins defined in
  configuration that take precedence over entry-point plugins with the same name.

**Methods:**
- `discover_entrypoint_plugins(group=ENTRY_POINT_GROUP) -> list[PluginManifest]`
  — Scans installed entry points and returns manifest list.

### Model: `crazypumpkin.framework.models.PluginManifest`

A dataclass describing a discovered plugin.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | `str` | `""` | Unique plugin identifier |
| `version` | `str` | `""` | Semver version string |
| `description` | `str` | `""` | Human-readable summary |
| `entry_point` | `str` | `""` | `module.path:ClassName` to load |
| `plugin_type` | `str` | `""` | `"agent"` or `"provider"` |
| `min_framework_version` | `str` | `""` | Minimum CP-OS version required |
| `permissions` | `list[str]` | `[]` | Permissions the plugin requests |
| `requires` | `list[str]` | `[]` | Dependencies (`plugin-name>=1.0`) |

### CLI Commands

#### `cpos list-plugins`

Calls `discover_plugins()` and prints a formatted table:

```
Name                           Version      Type         Status
--------------------------------------------------------------
hello_plugin                   1.0.0        agent        ok
my_provider                    0.2.0        provider     ok
```

- **Version** falls back to `"unknown"` if empty.
- **Status** is `"ok"` when `entry_point` is set, `"missing"` otherwise.

#### `cpos install-plugin <package>`

1. Runs `pip install <package>` in a subprocess.
2. Creates a minimal `PluginManifest` and validates it.
3. Prints success or validation warnings.
4. Exits with code 1 if pip fails.

#### `cpos remove-plugin <package>`

1. Checks for a local plugin file or directory under `plugins/` and removes it.
2. Runs `pip uninstall -y <package>`.
3. If pip fails but a local plugin was removed, does not exit with an error.

## Usage Examples

### Listing installed plugins

```bash
$ cpos list-plugins
Name                           Version      Type         Status
--------------------------------------------------------------
hello_plugin                   1.0.0        agent        ok
analytics                      0.3.0        provider     ok
```

### Installing a third-party plugin

```bash
$ cpos install-plugin cpos-analytics
Installing plugin 'cpos-analytics' ...
Successfully installed cpos-analytics-0.3.0
Plugin 'cpos-analytics' installed and validated successfully.
```

### Removing a plugin

```bash
$ cpos remove-plugin cpos-analytics
Uninstalling package 'cpos-analytics' ...
Successfully uninstalled cpos-analytics-0.3.0
Plugin 'cpos-analytics' removed.
```

### Programmatic discovery

```python
from crazypumpkin.framework.plugin_loader import discover_plugins, load_plugin

# Discover all plugins (entry points + local directory)
manifests = discover_plugins()
for m in manifests:
    print(f"{m.name} v{m.version} ({m.plugin_type})")

# Load a specific plugin
plugin_obj = load_plugin(manifests[0])
```

### Using PluginLoader with config overrides

```python
from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_loader import PluginLoader

# Config-defined plugin takes precedence over entry-point with same name
config_plugin = PluginManifest(
    name="my-plugin",
    version="2.0.0",
    entry_point="custom_module:MyPlugin",
    plugin_type="agent",
)

loader = PluginLoader(config_plugins=[config_plugin])
plugins = loader.discover_entrypoint_plugins()
```

## Entry-Point Registration (pyproject.toml)

Plugin authors declare their plugin in `pyproject.toml`:

```toml
[project.entry-points.'crazypumpkin.plugins']
my_plugin = "my_package:manifest"
```

The loaded object (`manifest`) can be:
- A `PluginManifest` instance
- A `dict` with PluginManifest field names
- Any other object (falls back to a minimal manifest using the entry-point name/value)

See [PLUGIN_ENTRYPOINTS.md](PLUGIN_ENTRYPOINTS.md) for a complete registration guide
with troubleshooting.
