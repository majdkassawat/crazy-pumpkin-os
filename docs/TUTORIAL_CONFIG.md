# Configuration Tutorial

A hands-on walkthrough covering config validation in Crazy Pumpkin OS.

## Prerequisites

- Python 3.10+ with the `crazypumpkin` package installed (editable install via `pip install -e .`)

---

## Part 1: Config Validation

Learn how `validate_config` catches missing required fields and reports clear error messages.
The function returns a `list[str]` — an empty list means the config is valid.

### Step 1 — Import and generate a default config

```python
from crazypumpkin.config import get_default_config, validate_config
cfg = get_default_config()
print(cfg['company']['name'])  # Output: My AI Company
```

### Step 2 — Validate the default config (should pass)

```python
errors = validate_config(cfg)
print(errors)  # Output: []
```

### Step 3 — Break validation by removing company.name

```python
cfg_bad = get_default_config()
del cfg_bad['company']['name']
errors = validate_config(cfg_bad)
print(errors)  # Output: ['Missing required field: company.name']
```

### Step 4 — Break validation by removing agents

```python
cfg_bad2 = get_default_config()
cfg_bad2['agents'] = []
errors = validate_config(cfg_bad2)
print(errors)  # Output: ['Missing required section: agents']
```

### Step 5 — Break validation with an agent missing role

```python
cfg_bad3 = get_default_config()
cfg_bad3['agents'][0]['role'] = ''
errors = validate_config(cfg_bad3)
print(errors)  # Output: ['Missing required field: agents[0].role']
```

### Step 6 — Validate a completely empty dict

```python
errors = validate_config({})
print(errors)  # Output: ['Missing required section: company', 'Missing required section: agents']
```

---

## Part 2: Environment Variable Overrides

Learn how to override any config value at runtime using environment variables.
The `resolve_env_overrides` function reads `CPOS_`-prefixed env vars and applies
them to a config dict, returning a new dict with overrides applied.

The naming convention uses a **double underscore** (`__`) to separate nesting
levels: `CPOS_SECTION__KEY` maps to `config['section']['key']`.

### Step 1 — Import and set up a base config

```python
import os
from crazypumpkin.config import get_default_config
from crazypumpkin.config.env_override import resolve_env_overrides, list_active_overrides

cfg = get_default_config()
print(cfg['dashboard']['port'])  # Output: 8500
```

### Step 2 — Override a simple value via env var

```python
os.environ['CPOS_DASHBOARD__PORT'] = '9000'
result = resolve_env_overrides(cfg)
print(result['dashboard']['port'])  # Output: 9000
```

Because `dashboard.port` is an `int` in the default config, the string `'9000'`
is automatically coerced to the integer `9000`.

### Step 3 — Override a nested value (LLM provider)

```python
os.environ['CPOS_LLM__DEFAULT_PROVIDER'] = 'openai_api'
result = resolve_env_overrides(cfg)
print(result['llm']['default_provider'])  # Output: openai_api
```

### Step 4 — Boolean coercion

Boolean fields accept `true`, `false`, `1`, and `0` (case-insensitive).
The value is coerced to a Python `bool` when the existing config field is a boolean.

```python
os.environ['CPOS_VOICE__ENABLED'] = 'true'
result = resolve_env_overrides(cfg)
print(result['voice']['enabled'])  # Output: True (bool, not string)
```

### Step 5 — List active overrides

Use `list_active_overrides` to inspect which env vars are currently overriding
config values. It returns a list of `(env_var, config_path, value)` tuples.

```python
overrides = list_active_overrides(cfg)
for env_var, config_path, value in overrides:
    print(f'{env_var} -> {config_path} = {value!r}')
# Output (example):
# CPOS_DASHBOARD__PORT -> dashboard.port = 9000
# CPOS_LLM__DEFAULT_PROVIDER -> llm.default_provider = 'openai_api'
# CPOS_VOICE__ENABLED -> voice.enabled = True
```

### Step 6 — Clean up env vars

Remove all `CPOS_`-prefixed env vars to restore the original environment.

```python
for key in list(os.environ):
    if key.startswith('CPOS_'):
        del os.environ[key]
```
