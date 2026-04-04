# Cost Observability

## Overview

Crazy Pumpkin OS tracks LLM spend in real time so you can monitor costs, set
budget caps, and break down spending by model or agent.

The system is built on three components:

| Component | Location | Purpose |
|---|---|---|
| **CostTracker** | `crazypumpkin.llm.base.CostTracker` | Thread-safe singleton that accumulates `CallCost` records (prompt tokens, completion tokens, cache tokens, and USD cost) for every LLM call. |
| **LLMUsageRecord** | Per-call `CallCost` dataclass | Captures prompt/completion/cache token counts and estimated cost for a single LLM invocation. |
| **Per-model tracking** | `CostTracker._by_model` | Automatic breakdown — every call is bucketed by its model name (e.g. `claude-sonnet-4-6`, `gpt-4o`). |
| **Per-agent tracking** | `Store.record_llm_spend()` | When `ProviderRegistry.call()` is used with an `agent` parameter, the cost is recorded against that agent in the store. |
| **Budget enforcement** | `AgentConfig.monthly_budget_usd` | The registry checks the agent's cumulative spend before each call and raises `BudgetExceededError` if the cap is exceeded. |

### How costs flow

1. An agent makes an LLM call through `ProviderRegistry.call()`.
2. The provider returns a response and a `CallCost`.
3. `CostTracker.record(model, cost)` adds the cost to the global tracker.
4. If an agent name was supplied, `Store.record_llm_spend(agent, cost_usd)` updates the per-agent ledger.
5. The CLI command `cpos cost` reads the tracker snapshot and prints the totals.

---

## Configuration

### Setting per-agent budgets

Add a `monthly_budget_usd` field to each agent's config section. A value of
`0.0` (the default) means **no limit**.

```yaml
agents:
  - name: developer
    role: execution
    model: claude-sonnet-4-6
    config:
      monthly_budget_usd: 50.00   # hard cap — raises BudgetExceededError

  - name: reviewer
    role: review
    model: claude-sonnet-4-6
    config:
      monthly_budget_usd: 20.00

  - name: strategist
    role: strategy
    model: claude-sonnet-4-6
    config:
      monthly_budget_usd: 0.0     # unlimited
```

### Choosing a provider with cost tracking

The **LiteLLM** provider supports automatic cost estimation for a wide range
of models. Set it as your default or route individual agents through it:

```yaml
llm:
  default_provider: litellm
  providers:
    litellm:
      model: gpt-4o
      api_key: ${OPENAI_API_KEY}

  agent_models:
    developer: { provider: litellm, model: gpt-4o }
```

The **Anthropic** provider also records `CallCost` via `call_with_cost()`,
so cost tracking works out of the box when using `anthropic_api`.

---

## CLI Usage

All cost commands are accessed via `cpos cost` (or `crazypumpkin cost`).

### Show overall summary

```bash
cpos cost
```

Example output:

```
Total cost: $1.2345
Total calls: 42
Prompt tokens: 85000
Completion tokens: 12000
Cache read tokens: 4000
Cache creation tokens: 2000

Per-model breakdown:
  claude-sonnet-4-6: $0.8100 | 30 calls | 60000+8000 tokens
  gpt-4o: $0.4245 | 12 calls | 25000+4000 tokens
```

### Break down by model

The default output already includes a per-model breakdown when data is
available. The `--by-model` flag is an explicit alias:

```bash
cpos cost --by-model
```

### JSON output

Pipe-friendly JSON for dashboards or scripts:

```bash
cpos cost --json
```

```json
{
  "total_cost_usd": 1.2345,
  "call_count": 42,
  "total_prompt_tokens": 85000,
  "total_completion_tokens": 12000,
  "total_cache_read_tokens": 4000,
  "total_cache_creation_tokens": 2000,
  "by_model": {
    "claude-sonnet-4-6": {
      "total_cost_usd": 0.81,
      "call_count": 30,
      "total_prompt_tokens": 60000,
      "total_completion_tokens": 8000
    }
  }
}
```

---

## Tutorial

This step-by-step guide walks you through enabling cost tracking with Langfuse
callbacks via the LiteLLM provider, setting budgets, running agents, and
viewing spend.

### Step 1 — Install dependencies

```bash
pip install crazypumpkin litellm langfuse
```

### Step 2 — Configure LiteLLM with Langfuse

Create or edit your `config.yaml`:

```yaml
company:
  name: "AcmeCorp"

products:
  - name: "WebApp"
    workspace: "./products/webapp"

llm:
  default_provider: litellm
  providers:
    litellm:
      model: gpt-4o
      api_key: ${OPENAI_API_KEY}
      langfuse_public_key: ${LANGFUSE_PUBLIC_KEY}
      langfuse_secret_key: ${LANGFUSE_SECRET_KEY}

  agent_models:
    developer:  { provider: litellm, model: gpt-4o }
    reviewer:   { provider: litellm, model: gpt-4o }
    strategist: { provider: litellm, model: gpt-4o }

agents:
  - name: developer
    role: execution
    description: "Writes code"
    config:
      monthly_budget_usd: 25.00

  - name: reviewer
    role: review
    description: "Reviews code"
    config:
      monthly_budget_usd: 10.00

  - name: strategist
    role: strategy
    description: "Plans tasks"
    config:
      monthly_budget_usd: 0.0

pipeline:
  cycle_interval: 30
```

Set the environment variables before running:

```bash
export OPENAI_API_KEY="sk-..."
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
```

### Step 3 — Run the pipeline

```bash
cpos run --once
```

The LiteLLM provider automatically registers the `"langfuse"` success callback
when both keys are present. Every LLM call is now traced in your Langfuse
dashboard **and** recorded locally by `CostTracker`.

### Step 4 — View spend from the CLI

```bash
# Overall summary
cpos cost

# Per-model breakdown
cpos cost --by-model

# Machine-readable JSON
cpos cost --json
```

Expected output after a single pipeline cycle:

```
Total cost: $0.0312
Total calls: 5
Prompt tokens: 12000
Completion tokens: 2400
Cache read tokens: 0
Cache creation tokens: 0

Per-model breakdown:
  gpt-4o: $0.0312 | 5 calls | 12000+2400 tokens
```

### Step 5 — View traces in Langfuse

Open your Langfuse project dashboard. Each LLM call appears as a trace tagged
with the agent name (via the `generation_name` / `trace_name` metadata fields).
You can filter by agent, model, and time range to drill into spend patterns.

---

## Troubleshooting

### No data shown in `cpos cost`

| Cause | Fix |
|---|---|
| No LLM calls have been made yet | Run `cpos run --once` first so at least one pipeline cycle executes. |
| Provider does not record costs | Ensure you are using `anthropic_api` or `litellm` — both support `CallCost` tracking. The `openai_api` provider may not populate cost data unless LiteLLM is used as a wrapper. |
| Tracker was reset | `CostTracker` lives in-process memory. If the process restarted, counters reset to zero. Use Langfuse for persistent, cross-session cost history. |

### `BudgetExceededError` is raised

This means the agent's cumulative spend has reached its `monthly_budget_usd` cap.

```
BudgetExceededError: Agent developer budget exceeded: $25.12 spent of $25.00 limit
```

**Options:**

1. **Increase the budget** — update `monthly_budget_usd` in `config.yaml` and restart.
2. **Remove the cap** — set `monthly_budget_usd: 0.0` to disable the limit.
3. **Wait for the next month** — the per-agent ledger resets on a monthly basis.

### Langfuse traces not appearing

- Verify both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set in the environment.
- Check that `litellm` is the configured provider — Langfuse callbacks are only registered by `LiteLLMProvider`.
- Look for connection errors in the logs: `cpos logs --tail 50`.
