# Plugin Developer Guide: Entry-Point Registration

Register your plugin so Crazy Pumpkin OS discovers it automatically at startup.

## Configuring `pyproject.toml`

CP-OS scans the `crazypumpkin.plugins` entry-point group via
`importlib.metadata`. Any installed package declaring an entry point in
this group is discovered automatically.

Add a `[project.entry-points.'crazypumpkin.plugins']` section to your
plugin's `pyproject.toml`. Each key is the plugin name and the value points
to a manifest object using `package:attribute` syntax.

```toml
[project]
name = "my-cpos-plugin"
version = "0.1.0"
dependencies = ["crazypumpkin"]

[project.entry-points.'crazypumpkin.plugins']
my_plugin = "my_package:manifest"
```

The loaded object can be a `PluginManifest`, a `dict` of manifest fields,
or any object (CP-OS falls back to a minimal manifest).

### Complete Example

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "cpos-hello-plugin"
version = "1.0.0"
dependencies = ["crazypumpkin>=0.1.0"]

[project.entry-points.'crazypumpkin.plugins']
hello_plugin = "cpos_hello:manifest"
```

And in `cpos_hello/__init__.py`:

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
    """Plugin class instantiated by the framework."""
    def __init__(self):
        pass
```

## PluginManifest Fields

The `PluginManifest` dataclass is defined in `crazypumpkin.framework.models`:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `str` | Yes | Unique plugin identifier |
| `version` | `str` | Yes | Semver version string |
| `description` | `str` | No | Human-readable summary |
| `entry_point` | `str` | Yes | `module.path:ClassName` to load |
| `plugin_type` | `str` | Yes | `"agent"` or `"provider"` |
| `min_framework_version` | `str` | No | Minimum CP-OS version (e.g. `"0.1.0"`) |
| `permissions` | `list[str]` | No | Permissions the plugin requests |
| `requires` | `list[str]` | No | Dependencies (`plugin-name>=1.0`) |

**Required fields** for validation: `name`, `version`, `entry_point`, and
`plugin_type`. Plugins missing any of these will fail `validate_plugin()`.

## Verifying Your Plugin

After installing your plugin package (`pip install -e .`), confirm it is
visible:

```bash
cpos plugins list
```

You should see your plugin name, version, and type in the output. If the
plugin does not appear, check the troubleshooting section below.

## Troubleshooting

### ImportError on load

```
Plugin 'my_plugin' import failed: No module named 'my_package'
```

**Cause:** The package is not installed in the active Python environment.
**Fix:** Run `pip install -e .` from the plugin project root, or verify
your virtualenv is activated.

### Missing manifest fields

```
Plugin 'my_plugin' validation failed: Missing required field: version
```

**Cause:** The manifest dict or `PluginManifest` is missing one of the four
required fields (`name`, `version`, `entry_point`, `plugin_type`).
**Fix:** Ensure all required fields are set. See the table above.

### Invalid `plugin_type`

```
Plugin 'my_plugin' validation failed: Invalid plugin_type 'custom'; expected 'agent' or 'provider'
```

**Cause:** `plugin_type` must be either `"agent"` or `"provider"`.
**Fix:** Correct the value in your manifest.

### Framework version mismatch

```
Plugin requires framework >= 2.0.0, but current is 0.1.0
```

**Cause:** `min_framework_version` is higher than the installed CP-OS.
**Fix:** Upgrade CP-OS or lower `min_framework_version`.

### Entry-point not found after install

**Cause:** The `[project.entry-points]` section is missing or misspelled.
**Fix:** Verify the group name is exactly `crazypumpkin.plugins` and
rebuild/reinstall: `pip install -e .`

### Plugin instantiation failure

```
Plugin 'my_plugin' instantiation failed (sandboxed): TypeError(...)
```

**Cause:** The plugin class `__init__` raised an exception.
**Fix:** The entry-point class must be callable with no arguments.
