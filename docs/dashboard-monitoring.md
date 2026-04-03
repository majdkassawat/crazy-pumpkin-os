# Dashboard Monitoring

## Overview

The Crazy Pumpkin OS agent monitoring dashboard provides real-time visibility into agent status and LLM cost data. It exposes two interfaces:

- **REST API** — JSON endpoints for querying agent status and cost summaries on demand (`GET /api/agents/status`, `GET /api/cost/summary`).
- **WebSocket** — a persistent connection at `/ws` that streams live events (e.g. agent status changes) to connected clients as they occur.

The dashboard is built on [aiohttp](https://docs.aiohttp.org/) and can be started via the CLI (`crazypumpkin dashboard`) or embedded programmatically. It is designed to support both human operators viewing the built-in HTML page at `/dashboard/agents` and automated tooling consuming the JSON API.

## API Reference

### GET /api/agents/status

Returns a JSON array of agent status objects. Each object contains the agent's identity, current status, last activity timestamp, and the title of any in-progress task.

**curl example:**

```bash
curl -s http://127.0.0.1:8500/api/agents/status | python -m json.tool
```

**Response — 200 OK:**

```json
[
  {
    "id": "agent-001",
    "name": "StrategyAgent",
    "role": "strategy",
    "status": "active",
    "last_active": "2026-04-03T12:34:56",
    "current_task": "Implement authentication module"
  },
  {
    "id": "agent-002",
    "name": "DeveloperAgent",
    "role": "developer",
    "status": "idle",
    "last_active": "2026-04-03T12:30:00",
    "current_task": ""
  }
]
```

**Response schema:**

| Field          | Type   | Description                                         |
|----------------|--------|-----------------------------------------------------|
| `id`           | string | Unique agent identifier                             |
| `name`         | string | Agent display name                                  |
| `role`         | string | Agent role (e.g. `strategy`, `developer`, `reviewer`)|
| `status`       | string | Current status (`active`, `idle`, `disabled`)        |
| `last_active`  | string | ISO 8601 timestamp of last heartbeat, or `""`       |
| `current_task` | string | Title of the agent's in-progress task, or `""`      |

**HTTP status codes:**

| Code | Meaning                        |
|------|--------------------------------|
| 200  | Success                        |
| 500  | Internal server error          |

---

### GET /api/cost/summary

Returns a JSON object with the total LLM cost, broken down by model and by agent.

**curl example:**

```bash
curl -s http://127.0.0.1:8500/api/cost/summary | python -m json.tool
```

**Response — 200 OK:**

```json
{
  "total_cost_usd": 1.2345,
  "by_model": {
    "claude-sonnet-4-20250514": 0.8123,
    "gpt-4o": 0.4222
  },
  "by_agent": {
    "StrategyAgent": 0.5100,
    "DeveloperAgent": 0.7245
  }
}
```

**Response schema:**

| Field            | Type   | Description                                              |
|------------------|--------|----------------------------------------------------------|
| `total_cost_usd` | number | Cumulative LLM spend in USD                              |
| `by_model`       | object | Cost per model name (key: model string, value: USD float)|
| `by_agent`       | object | Cost per agent (key: agent name, value: USD float)       |

**HTTP status codes:**

| Code | Meaning                        |
|------|--------------------------------|
| 200  | Success                        |
| 500  | Internal server error          |

## WebSocket Event Format

Connect to the WebSocket endpoint at `ws://HOST:PORT/ws` to receive real-time events. Each message is a JSON string.

### General event payload

When the `WebSocketBroadcaster.broadcast()` method forwards a framework event, the payload has the following shape:

```json
{
  "id": "evt-abc123",
  "timestamp": "2026-04-03T12:35:00",
  "agent_id": "agent-001",
  "action": "task_completed",
  "detail": "Finished implementing auth module",
  "result": "success",
  "risk_level": "low"
}
```

| Field        | Type   | Description                                 |
|--------------|--------|---------------------------------------------|
| `id`         | string | Event identifier                            |
| `timestamp`  | string | ISO 8601 timestamp                          |
| `agent_id`   | string | Agent that triggered the event              |
| `action`     | string | Event action name                           |
| `detail`     | string | Human-readable detail                       |
| `result`     | string | Outcome of the action                       |
| `risk_level` | string | Risk assessment (`low`, `medium`, `high`)   |

### agent_status_changed event

When an agent's status changes, a dedicated `agent_status` message is broadcast via `broadcast_agent_status()`:

```json
{
  "type": "agent_status",
  "agent_id": "agent-001",
  "status": "active",
  "timestamp": "2026-04-03T12:35:10"
}
```

| Field       | Type   | Description                                   |
|-------------|--------|-----------------------------------------------|
| `type`      | string | Always `"agent_status"` for this event type   |
| `agent_id`  | string | The agent whose status changed                |
| `status`    | string | New status value (e.g. `active`, `idle`)      |
| `timestamp` | string | ISO 8601 timestamp of the change              |

### cost_updated event

Cost updates can be derived by periodically polling `GET /api/cost/summary` or by listening for framework events that include cost data. When cost data flows through the general broadcast channel, it uses the general event payload format shown above with `action` set to a cost-related action string.

## Tutorial: Setting Up Dashboard Monitoring

Follow these steps to get the dashboard running and connected.

### 1. Install dependencies

Make sure you have Crazy Pumpkin OS and its dashboard dependencies installed:

```bash
pip install crazypumpkin
```

The dashboard uses `aiohttp`, which is included as a dependency.

### 2. Configure the dashboard

In your project's `config.yaml`, add or verify the `dashboard` section:

```yaml
dashboard:
  port: 8500
  host: "127.0.0.1"
  password: ${DASHBOARD_PASSWORD}   # leave empty for open access
```

Set the `DASHBOARD_PASSWORD` environment variable in your `.env` file if you want password protection.

### 3. Start the dashboard server

Start the dashboard using the CLI:

```bash
crazypumpkin dashboard
```

For continuous live monitoring in the terminal, use watch mode:

```bash
crazypumpkin dashboard --watch --interval 5
```

### 4. Query the REST API

With the server running, query agent status:

```bash
curl -s http://127.0.0.1:8500/api/agents/status | python -m json.tool
```

Query cost summary:

```bash
curl -s http://127.0.0.1:8500/api/cost/summary | python -m json.tool
```

### 5. Connect to the WebSocket

Use any WebSocket client to connect and receive live events. For example, with [websocat](https://github.com/vi/websocat):

```bash
websocat ws://127.0.0.1:8500/ws
```

Or in Python:

```python
import asyncio
import websockets

async def listen():
    async with websockets.connect("ws://127.0.0.1:8500/ws") as ws:
        async for message in ws:
            print(message)

asyncio.run(listen())
```

### 6. Interpret the results

- **Agent status**: each agent shows `active`, `idle`, or `disabled`. An empty `current_task` means the agent is not working on anything.
- **Cost summary**: `total_cost_usd` is the cumulative LLM spend. Use `by_model` and `by_agent` breakdowns to identify cost drivers.
- **WebSocket events**: `agent_status` messages indicate real-time agent transitions. Use them to trigger alerts or update external dashboards.

## Configuration

The `dashboard` section in `config.yaml` controls how the dashboard server starts.

| Key        | Type   | Default       | Description                                                        |
|------------|--------|---------------|--------------------------------------------------------------------|
| `host`     | string | `"127.0.0.1"` | Network interface the dashboard binds to. Use `"0.0.0.0"` to expose externally. |
| `port`     | int    | `8500`        | TCP port the dashboard listens on.                                 |
| `password` | string | `""`          | Optional password for dashboard access. Supports `${ENV_VAR}` substitution. Leave empty to disable authentication. |

**Example configuration:**

```yaml
dashboard:
  host: "0.0.0.0"
  port: 9000
  password: ${DASHBOARD_PASSWORD}
```

**CLI flags** (for `crazypumpkin dashboard`):

| Flag         | Default | Description                                        |
|--------------|---------|----------------------------------------------------|
| `--watch`    | `false` | Continuously poll and print dashboard status        |
| `--interval` | `5`     | Seconds between polls in watch mode                 |
