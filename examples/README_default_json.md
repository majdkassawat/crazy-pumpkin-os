# examples/default.json — Field Reference

Minimal working configuration for Crazy Pumpkin OS.
Copy to `config/default.json` in your project root (the framework loads
`config.yaml` first, then falls back to `config/default.json`).

## Fields

### `company` (required)
| Field | Type | Description |
|---|---|---|
| `name` | string | Your company or project name. Must be non-empty. |

### `products` (required, at least one entry)
| Field | Type | Description |
|---|---|---|
| `name` | string | Human-readable product name. |
| `workspace` | string | Path to the product directory, resolved relative to the project root. Supports `~` and `${VAR}` expansion. |
| `source_dir` | string | Subdirectory inside workspace containing source code. |
| `test_dir` | string | Subdirectory inside workspace containing tests. |
| `test_command` | string | Shell command agents run to verify changes. |
| `git_branch` | string | Default branch for this product. |
| `auto_pm` | boolean | When `true`, the PM agent auto-generates goals for idle products. |

### `llm` (optional)
| Field | Type | Description |
|---|---|---|
| `default_provider` | string | Which provider to use by default (`anthropic_api`, `openai_api`, `ollama`). |
| `providers` | object | Provider-specific settings. Each key is a provider name; `api_key` values support `${ENV_VAR}` expansion. |
| `agent_models` | object | Per-role model overrides. Keys are role names; values have a `model` field. |

### `agents` (required, at least one entry)
| Field | Type | Description |
|---|---|---|
| `name` | string | Display name for the agent. |
| `role` | string | One of: `orchestrator`, `strategy`, `execution`, `reviewer`, `governance`, `evolution`, `architect`, `ceo`, `market_intel`, `human_interface`, `ops`, `triage`, `framework_doctor`, `product_manager`. |
| `class` | string | Fully-qualified Python class implementing the agent. |
| `model` | string | LLM model identifier (e.g. `sonnet`, `claude-sonnet-4-6`). Use `none` for agents that don't call an LLM. |
| `group` | string | Logical group for scheduling (e.g. `execution`, `review`, `operations`). |
| `description` | string | What this agent does. |

### `pipeline` (optional — defaults applied automatically)
| Field | Type | Default | Description |
|---|---|---|---|
| `cycle_interval` | integer | `30` | Seconds between pipeline cycles. |
| `task_timeout_sec` | integer | — | Maximum seconds for a single task execution. |
| `task_escalation_retries` | integer | — | How many retries before escalating a failed task. |

### `notifications` (optional)
| Field | Type | Description |
|---|---|---|
| `providers` | array | List of notification provider configs (e.g. `telegram`, `slack`, `webhook`). Empty array disables notifications. |

### `dashboard` (optional)
| Field | Type | Description |
|---|---|---|
| `port` | integer | Port for the web dashboard. |
| `host` | string | Bind address (use `127.0.0.1` for local-only). |
| `password` | string | Dashboard access password. Supports `${ENV_VAR}`. Leave absent for open access. |

### `voice` (optional)
| Field | Type | Description |
|---|---|---|
| `enabled` | boolean | Enable/disable voice interface. |

## Environment Variable Expansion

All string values support `${VAR_NAME}` syntax. If the variable is set in the
environment, it is substituted; otherwise the literal `${VAR_NAME}` is kept.
This lets you keep secrets out of the config file.
