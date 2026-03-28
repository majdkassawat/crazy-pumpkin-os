# Getting Started with Crazy Pumpkin OS

## Prerequisites

- **Python 3.11+** (3.12 and 3.13 are also supported)
- **pip** (comes with Python)
- An API key for at least one LLM provider (Anthropic, OpenAI, or a local Ollama instance)

## Installation

```bash
pip install crazypumpkin
```

To include optional dependencies:

```bash
# OpenAI provider support
pip install crazypumpkin[openai]

# All optional extras
pip install crazypumpkin[all]

# Development dependencies (pytest, etc.)
pip install crazypumpkin[dev]
```

## Configuration

Initialize a new project with the interactive wizard:

```bash
crazypumpkin init
```

This creates a `config.yaml`, `.env`, `.gitignore`, `goals/` directory, and `README.md` in the current folder.

For a detailed example of every configuration option, see [`examples/config.yaml`](examples/config.yaml). Key sections include:

| Section | Purpose |
| --- | --- |
| `company` | Company name |
| `products` | Repositories/products managed by the company |
| `llm` | LLM provider settings and per-agent model assignments |
| `agents` | Agent definitions (Strategist, Developer, Reviewer, Ops, …) |
| `pipeline` | Cycle interval, task timeout, escalation retries |
| `notifications` | Telegram, Slack, Discord, webhook integrations |
| `dashboard` | Host, port, and password for the web dashboard |
| `voice` | Voice interface settings (OpenAI Realtime API) |

Set your API key and dashboard password in the `.env` file:

```
ANTHROPIC_API_KEY=sk-...
DASHBOARD_PASSWORD=your-password
```

## Running the Pipeline

Start the continuous pipeline:

```bash
crazypumpkin run
```

The pipeline runs in a loop, executing one cycle every 30 seconds (configurable via `pipeline.cycle_interval` in `config.yaml`).

To run a single cycle and exit:

```bash
crazypumpkin run --once
```

To override the cycle interval:

```bash
crazypumpkin run --interval 60
```

### Creating Goals

Drop `.goal` files into the `goals/` directory, or use the CLI:

```bash
crazypumpkin goal "Add user authentication" "Build email/password login with JWT tokens"
```

## Running Tests

Install development dependencies first:

```bash
pip install crazypumpkin[dev]
```

Then run the test suite:

```bash
python -m pytest tests/ -v --tb=short
```

Or simply:

```bash
pytest
```

## Dashboard Access

Start the web dashboard:

```bash
crazypumpkin dashboard
```

Then open your browser to:

```
http://localhost:8500
```

The dashboard provides a real-time view of your AI company: org chart, agent timeline, and project tracking.

Dashboard host and port are configurable in `config.yaml` under the `dashboard` section. If you set a `DASHBOARD_PASSWORD` in `.env`, you will need it to access the dashboard.

## Other CLI Commands

```bash
crazypumpkin status     # Show current company status
crazypumpkin --help     # List all available commands
```
