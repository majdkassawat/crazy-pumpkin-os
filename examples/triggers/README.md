# Trigger System

Crazy Pumpkin OS supports two types of triggers that control when agents are dispatched:

1. **Expression triggers** — Boolean expressions parsed by `parse_trigger()` and evaluated by `evaluate_trigger()` from `crazypumpkin.framework.trigger`. Expression triggers support comparison operators `>`, `<`, `==`, `>=`, `<=` and logical connectives `AND`, `OR`, plus sentinel keywords `always`, `never`, `schedule`.

2. **Cron triggers** — Time-based scheduling via the `CronTrigger` class and `register_cron_trigger()` from `crazypumpkin.framework.trigger`. Cron triggers use standard five-field cron expressions (`minute hour dom month dow`).

## Expression Triggers

Expression triggers use a simple DSL with comparison operators and logical connectives.

### Supported Syntax

| Element | Examples |
|---------|---------|
| Comparisons | `planned_tasks > 0`, `hours_since_last_run >= 2` |
| Operators | `>`, `<`, `==`, `>=`, `<=` |
| Logical | `AND`, `OR` |
| Sentinels | `always` (always true), `never` (always false), `schedule` (time-based) |

### Code Example

```python
from crazypumpkin.framework.trigger import evaluate_trigger

snapshot = {"planned_tasks": 3, "hours_since_last_run": 2}
result = evaluate_trigger("planned_tasks > 0 AND hours_since_last_run > 1", snapshot)
print(result)  # True
```

### Snapshot Variables

The scheduler builds a snapshot with these keys before evaluating triggers:

| Variable | Type | Description |
|----------|------|-------------|
| `planned_tasks` | int | Number of tasks in PLANNED status |
| `in_progress_tasks` | int | Number of tasks currently IN_PROGRESS |
| `hours_since_last_run` | float | Hours elapsed since the last scheduler cycle |

## Cron Triggers

Cron triggers use the `CronTrigger` class and `register_cron_trigger()` to associate a cron schedule with a callback function.

### Code Example

```python
from crazypumpkin.framework.trigger import register_cron_trigger

def my_callback():
    print("Triggered!")

trigger = register_cron_trigger("nightly-build", "0 2 * * *", my_callback)
if trigger.should_fire():
    trigger.fire()
```

### Assigning a Cron Schedule to an Agent

In `config.yaml`, add a `cron` field to an agent definition:

```yaml
agents:
  - name: "NightlyReviewer"
    role: review
    class: crazypumpkin.agents.reviewer_agent.ReviewerAgent
    cron: "0 2 * * *"  # runs at 2:00 AM daily
```

## CLI Usage

### `crazypumpkin schedule list`

List all agents with a cron schedule:

```bash
$ crazypumpkin schedule list
NightlyReviewer  0 2 * * *
HourlyCheck      0 * * * *
```

### `crazypumpkin schedule add`

Add or update a cron schedule for an agent:

```bash
$ crazypumpkin schedule add NightlyReviewer "0 2 * * *"
Scheduled NightlyReviewer with cron '0 2 * * *'
```

### `crazypumpkin schedule remove`

Remove a cron schedule from an agent:

```bash
$ crazypumpkin schedule remove NightlyReviewer
Removed schedule for NightlyReviewer
```

## Running the Demo

```bash
cd examples/triggers
python demo_triggers.py
```

This will demonstrate expression parsing, evaluation, cron parsing, and error handling.
