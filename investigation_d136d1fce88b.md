# Investigation: Phantom Agent d136d1fce88b and Bolt Entry

**Task**: FW-285b148dc088
**Date**: 2026-03-28
**State file**: `C:\Users\kasmaj\TFS\Repositories\kassawat-framework\data\state.json`

## Findings

### 1. d136d1fce88b — Present in task assignments, absent from agent_metrics

The ID `d136d1fce88b` does NOT appear in the `agent_metrics` section of state.json.

It DOES appear as `assigned_to` on 3 tasks (all in project `811c8c0f5db2` — "Ship MCP server"):

| Task ID | Title | Status |
|---------|-------|--------|
| 1212d43e2618 | [FRAMEWORK FIX] Skipped review: developer produced 0 artifacts | planned |
| 3fbc1dfb9456 | [FRAMEWORK FIX] Validation errors: Developer produced 0 artifacts | planned |
| 11f61f988aca | [FRAMEWORK FIX] REJECTED [governance] produced 0 code artifacts | in_progress |

The AGENTS.md task board (synced from framework) shows these 3 tasks assigned to **"Atlas - Architect"**. This means `d136d1fce88b` was the runtime agent ID for an Atlas instance.

### 2. Bolt — Present in agent_metrics under a different ID

Bolt appears in `agent_metrics` as:
- **Agent ID**: `dee9a23f94cc`
- **Agent name**: `Bolt - Developer`
- **Stats**: 2 completed, 2 rejected, 4 retries, ~19k sec total duration

Bolt is also defined in `config/default.json` (line 220):
- Name: "Bolt - Developer"
- Role: execution
- Trigger: `planned_tasks > 0 OR in_progress_tasks > 0` / cooldown 15s

### 3. Relationship: d136d1fce88b is NOT Bolt

`d136d1fce88b` is a **stale Atlas - Architect instance ID**, not Bolt.

**Root cause**: Agent IDs are generated via `uuid.uuid4().hex[:12]` (see `models.py:35-36`) on every agent instantiation. Each pipeline restart gives every agent a new random 12-char hex ID. When the pipeline restarts:
1. Atlas gets a new ID (e.g., the current one differs from `d136d1fce88b`)
2. Tasks previously assigned to `d136d1fce88b` become orphaned — no active agent claims them
3. The framework detects `d136d1fce88b` in metrics as an unrecognized ID with poor success rate

Bolt's current instance ID is `dee9a23f94cc` and has no connection to `d136d1fce88b`.

### 4. Impact

The 3 orphaned tasks assigned to `d136d1fce88b` are stuck:
- 2 in `planned` status (will never be picked up)
- 1 in `in_progress` status (will never complete)

These consume pipeline metrics capacity and inflate failure rates.

## Recommended Fix

1. **Reassign or unassign** the 3 tasks currently assigned to `d136d1fce88b` so the current Atlas instance can pick them up
2. **Add an agent-ID stability mechanism** (e.g., deterministic IDs from agent name hash, or persist IDs across restarts) to prevent orphaned assignments
3. **Add orphan detection**: on startup, scan for tasks assigned to IDs not matching any active agent and either reassign or flag them
