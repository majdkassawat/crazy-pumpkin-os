# Config Validation & Environment Variable Overrides

## Overview

Crazy Pumpkin OS uses a **two-layer validation system** to catch configuration errors early:

1. **`validate_config()`** (`src/crazypumpkin/config/__init__.py:74`) — lightweight validator that checks for required sections and fields, returning a list of error strings. Suitable for quick checks and CLI tooling (e.g., `cpos doctor`).

2. **`_validate_and_build()`** (`src/crazypumpkin/framework/config.py:42`) — strict validator used during `load_config()`. Raises `ValueError` with detailed, contextual error messages including examples of the correct format. Builds a typed `Config` dataclass on success.

Both layers enforce the same structural requirements but differ in strictness: `validate_config()` collects all errors and returns them, while `_validate_and_build()` raises on the first error with rich diagnostic output.

### Required Sections

| Section    | Type | Required Fields                                                                 |
|------------|------|---------------------------------------------------------------------------------|
| `company`  | dict | `name` (str) — the company or organization name                                |
| `products` | list | Each item requires `name` (str) and `workspace` (str, path to product directory)|
| `agents`   | list | Each item requires `name` (str) and `role` (one of `strategy`, `execution`, `review`) |

### Optional Sections

| Section         | Type | Description                                          |
|-----------------|------|------------------------------------------------------|
| `llm`           | dict | LLM provider configuration (`default_provider`, `providers`, `agent_models`) |
| `pipeline`      | dict | Pipeline settings (`cycle_interval`, default 30)     |
| `notifications` | dict | Notification provider configuration                  |
| `dashboard`     | dict | Dashboard server settings (`port`, `host`)           |
| `voice`         | dict | Voice feature toggle (`enabled`)                     |

## `${VAR_NAME}` Expansion

Before validation, `_expand_vars()` (`src/crazypumpkin/framework/config.py:14`) recursively expands `${VAR_NAME}` patterns in all string values from environment variables.

- Pattern: `${VARIABLE_NAME}` — matches word characters (`\w+`) inside `${}`.
- If the environment variable exists, the pattern is replaced with its value.
- If the environment variable does **not** exist, the pattern is left unchanged (passthrough).
- Expansion is recursive: it processes strings inside dicts and lists at any nesting depth.

### Example

Given `config.yaml`:

```yaml
llm:
  providers:
    anthropic_api:
      api_key: "${ANTHROPIC_API_KEY}"
```

And environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-abc123
```

After expansion, the config value becomes `"sk-ant-abc123"`.

Variable expansion happens **before** environment variable overrides and **before** validation.

## Environment Variable Overrides

Environment variables with the `CPOS_` prefix override config values at load time via `resolve_env_overrides()` (`src/crazypumpkin/config/env_override.py:54`). This lets you change configuration without editing YAML files — useful for CI, Docker, and per-environment deployments.

### Convention

- **Prefix**: `CPOS_`
- **Nesting**: double underscore `__` separates nesting levels.
- **Key casing**: env var segments are lowercased to match config keys.
- Single underscores within a segment are literal underscores in the config key.

### Type Coercion Rules

| Rule | Env Var Value         | Coerced Result     | Notes                                           |
|------|-----------------------|--------------------|--------------------------------------------------|
| 1    | `"true"` or `"1"`    | `True` (bool)      | Case-insensitive; `"1"` → bool only if existing field is bool |
| 2    | `"false"` or `"0"`   | `False` (bool)     | Case-insensitive; `"0"` → bool only if existing field is bool |
| 3    | All-digit string     | `int`              | e.g., `"8080"` → `8080`                         |
| 4    | Comma-separated      | `list[str]`        | e.g., `"a, b, c"` → `["a", "b", "c"]`          |

Any value that does not match the above rules is kept as `str`.

When the target config key already has a value, schema-aware coercion matches the existing type (bool, int, float, list, or str). When the key is new, heuristic coercion applies — but `"0"` and `"1"` coerce to `int` (not `bool`) to prevent silent data corruption.

### Override Examples

| Environment Variable                  | Config Path                | Effect                                    |
|---------------------------------------|----------------------------|-------------------------------------------|
| `CPOS_DASHBOARD__PORT=9000`           | `dashboard.port`           | Sets dashboard port to `9000` (int)       |
| `CPOS_DASHBOARD__HOST=0.0.0.0`       | `dashboard.host`           | Sets dashboard host to `"0.0.0.0"`       |
| `CPOS_LLM__DEFAULT_PROVIDER=openai`  | `llm.default_provider`     | Switches LLM provider to `"openai"`      |
| `CPOS_VOICE__ENABLED=true`           | `voice.enabled`            | Enables voice features (`True`)           |
| `CPOS_PIPELINE__CYCLE_INTERVAL=60`   | `pipeline.cycle_interval`  | Changes cycle interval to `60` (int)      |
| `CPOS_COMPANY__NAME=Acme`            | `company.name`             | Overrides company name to `"Acme"`       |

### Listing Active Overrides

Use `list_active_overrides()` to inspect which environment variables are currently overriding config values — useful for debugging:

```python
from crazypumpkin.config.env_override import list_active_overrides

overrides = list_active_overrides(config)
for env_var, config_path, value in overrides:
    print(f"{env_var} -> {config_path} = {value!r}")
```

Returns a list of `(env_var_name, config_path, coerced_value)` tuples for every `CPOS_*` variable found in the environment.

## Common Validation Errors

The table below lists error messages raised by `_validate_and_build()` with their cause and fix.

| # | Error Message | Cause | Fix |
|---|---------------|-------|-----|
| 1 | `Missing required field: company.name` | The `company` section is missing or has no `name` field | Add `company:\n  name: YourCompany` to your config |
| 2 | `Missing required section: products` | The `products` key is missing or empty | Add a `products` list with at least one product entry |
| 3 | `Missing required field in products[i]: name` | A product entry is missing the `name` field | Add `name: MyProduct` to the product entry |
| 4 | `Missing required field in products[i] ('X'): workspace` | Product `X` is missing the `workspace` field | Add `workspace: ./products/myapp` to the product entry |
| 5 | `Missing required section: agents` | The `agents` key is missing or empty | Add an `agents` list with at least one agent entry |
| 6 | `Missing required field in agents[i]: name` | An agent entry is missing the `name` field | Add `name: Developer` to the agent entry |
| 7 | `Missing required field in agents[i] ('X'): role` | Agent `X` is missing the `role` field | Add `role: execution` (valid: `strategy`, `execution`, `review`) |
| 8 | `Invalid role in agents[i] ('X'): 'bad_role'` | Agent `X` has a role not in `strategy\|execution\|review` | Change the role to one of: `strategy`, `execution`, `review` |
| 9 | `YAML syntax error in <path> at line L, column C` | The YAML file has a syntax error (bad indentation, missing quotes, etc.) | Fix the YAML syntax at the indicated line and column |
| 10 | `JSON syntax error in <path> at line L, column C` | The `config/default.json` file has invalid JSON | Fix the JSON syntax at the indicated line and column |
| 11 | `No configuration file found in <project_root>` | Neither `config.yaml` nor `config/default.json` exists | Create a `config.yaml` or `config/default.json` in the project root |
