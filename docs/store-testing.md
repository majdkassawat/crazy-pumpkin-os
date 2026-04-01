# Store Module — Test Documentation & Tutorial

The `Store` class (`crazypumpkin.framework.store`) is the persistence layer for
the Crazy Pumpkin agent framework. It manages projects, tasks, reviews,
approvals, change proposals, agent metrics, and run history — backed by an
in-memory dict with optional JSON file persistence.

---

## API Reference

### Module-level helpers

| Function | Description |
|----------|-------------|
| `_to_dict(obj)` | Recursively convert dataclasses and enums to plain dicts for JSON serialization. |

### `Store` — constructor

| Method | Description |
|--------|-------------|
| `Store(data_dir=None)` | Create a new store, optionally backed by a directory for `state.json` persistence. |

### `Store` — Projects

| Method | Description |
|--------|-------------|
| `add_project(project)` | Insert or overwrite a `Project` keyed by its `id`. |
| `get_project(project_id)` | Return the `Project` with the given ID, or `None`. |

### `Store` — Tasks

| Method | Description |
|--------|-------------|
| `add_task(task)` | Insert or overwrite a `Task` keyed by its `id`. |
| `get_task(task_id)` | Return the `Task` with the given ID, or `None`. |
| `tasks_by_project(project_id)` | Return all tasks belonging to a project. |
| `tasks_by_status(status)` | Return all tasks whose status value matches the given string. |

### `Store` — Reviews

| Method | Description |
|--------|-------------|
| `add_review(review)` | Insert or overwrite a `Review` keyed by its `id`. |
| `reviews_for_task(task_id)` | Return all reviews linked to a task. |

### `Store` — Approvals

| Method | Description |
|--------|-------------|
| `add_approval(approval)` | Insert or overwrite an `Approval` keyed by its `id`. |
| `pending_approvals()` | Return all approvals with `status == "pending"`. |

### `Store` — Proposals

| Method | Description |
|--------|-------------|
| `add_proposal(proposal)` | Insert or overwrite a `ChangeProposal` keyed by its `id`. |

### `Store` — Agent Metrics

| Method | Description |
|--------|-------------|
| `record_task_outcome(agent_id, agent_name, completed, retries, duration_sec, first_attempt)` | Record a task completion or rejection for an agent's performance counters. |
| `is_low_success_rate(agent_id, window=10, threshold=0.20)` | Return `True` when the agent's recent success rate is below the threshold. |
| `record_llm_spend(agent_id, cost_usd)` | Increment `budget_spent_usd` for the given agent (creates entry if absent). |
| `is_budget_exceeded(agent_id, config)` | Return `True` when the agent has reached or exceeded its monthly budget cap. |
| `get_all_agent_metrics()` | Return a list of all `AgentMetrics` objects. |
| `purge_agent(agent_id)` | Remove an agent's metrics and unassign its orphaned tasks; returns counts. |
| `purge_orphaned_agents(active_ids)` | Purge metrics and task assignments for agent IDs not in the active set. |

### `Store` — Digest & Compaction

| Method | Description |
|--------|-------------|
| `compute_digest_stats(window_hours=24)` | Compute summary statistics (completed count, rejection rate, escalated tasks, cycle-time p50). |
| `compact(keep_recent=50, task_retention_days=7)` | Archive old completed/cancelled projects, stale tasks, and terminal-task reviews to `archive.jsonl`. |

### `Store` — Persistence

| Method | Description |
|--------|-------------|
| `save()` | Serialize the full store to `<data_dir>/state.json` (no-op without a `data_dir`). |
| `load()` | Deserialize state from `state.json`; returns `True` if state was loaded. |
| `_strip_task_history(tasks_dict, max_entries=20)` | *(static)* Truncate each task's history to the last `max_entries` items during serialization. |
| `_strip_artifact_contents(tasks_dict)` | *(static)* Strip large artifact/metadata content from task outputs to keep `state.json` small. |

### `Store` — Run History

| Method | Description |
|--------|-------------|
| `save_run_record(record)` | *(async)* Save or overwrite a `RunRecord` by its `run_id`. |
| `get_run_record(run_id)` | *(async)* Retrieve a single `RunRecord` by ID, or `None`. |
| `list_run_records(*, agent_name=None, status=None, limit=50, offset=0)` | *(async)* List run records newest-first with optional filtering and pagination. |

---

## Tutorial

This section shows how to use the `Store` in tests with `pytest`'s `tmp_path`
fixture for isolated, file-backed persistence.

### Imports

All examples use these imports:

```python
from pathlib import Path

from crazypumpkin.framework.store import Store
from crazypumpkin.framework.models import (
    AgentConfig,
    Approval,
    ApprovalStatus,
    ChangeProposal,
    Project,
    ProjectStatus,
    ProposalType,
    Review,
    ReviewDecision,
    Task,
    TaskOutput,
    TaskStatus,
)
```

### Example 1 — Create a Store, add a project and tasks, then query

```python
def test_basic_project_and_tasks(tmp_path: Path):
    """Instantiate a file-backed Store and perform basic CRUD."""
    store = Store(data_dir=tmp_path)

    # Create a project
    project = Project(id="proj-1", name="My Project", status=ProjectStatus.ACTIVE)
    store.add_project(project)
    assert store.get_project("proj-1") is project

    # Add tasks to the project
    t1 = Task(id="t1", project_id="proj-1", title="Write code", status=TaskStatus.CREATED)
    t2 = Task(id="t2", project_id="proj-1", title="Write tests", status=TaskStatus.COMPLETED)
    store.add_task(t1)
    store.add_task(t2)

    # Query tasks by project
    tasks = store.tasks_by_project("proj-1")
    assert len(tasks) == 2
    assert {t.id for t in tasks} == {"t1", "t2"}

    # Query tasks by status
    completed = store.tasks_by_status("completed")
    assert len(completed) == 1
    assert completed[0].id == "t2"
```

### Example 2 — Save and load round-trip with reviews

```python
def test_persistence_round_trip(tmp_path: Path):
    """Save state to disk, create a fresh Store, load, and verify."""
    store = Store(data_dir=tmp_path)

    store.add_project(Project(id="p1", name="Alpha"))
    store.add_task(Task(
        id="t1", project_id="p1", title="Implement feature",
        output=TaskOutput(content="done", artifacts={"main.py": "print(1)"}),
    ))
    store.add_review(Review(
        id="r1", task_id="t1",
        decision=ReviewDecision.APPROVED, feedback="Looks good",
    ))
    store.save()

    # Verify state.json was written
    assert (tmp_path / "state.json").exists()

    # Load into a fresh store
    store2 = Store(data_dir=tmp_path)
    assert store2.load() is True

    assert store2.get_project("p1").name == "Alpha"
    assert store2.get_task("t1").output.content == "done"
    reviews = store2.reviews_for_task("t1")
    assert len(reviews) == 1
    assert reviews[0].decision == ReviewDecision.APPROVED
```

### Example 3 — Track agent metrics and check budget

```python
def test_agent_metrics_and_budget(tmp_path: Path):
    """Record task outcomes, track LLM spend, and check budget caps."""
    store = Store(data_dir=tmp_path)

    # Record successful and failed task outcomes
    store.record_task_outcome(
        agent_id="agent-dev", agent_name="Developer",
        completed=True, retries=0, duration_sec=12.5, first_attempt=True,
    )
    store.record_task_outcome(
        agent_id="agent-dev", agent_name="Developer",
        completed=False, retries=2, duration_sec=8.0, first_attempt=False,
    )

    metrics = store.get_all_agent_metrics()
    assert len(metrics) == 1
    assert metrics[0].tasks_completed == 1
    assert metrics[0].tasks_rejected == 1

    # Track LLM spend
    store.record_llm_spend("agent-dev", 3.50)
    store.record_llm_spend("agent-dev", 1.25)

    # Check budget cap
    cfg_low = AgentConfig(monthly_budget_usd=4.0)
    assert store.is_budget_exceeded("agent-dev", cfg_low) is True  # 4.75 >= 4.0

    cfg_high = AgentConfig(monthly_budget_usd=10.0)
    assert store.is_budget_exceeded("agent-dev", cfg_high) is False  # 4.75 < 10.0

    # Verify round-trip persistence of metrics
    store.save()
    store2 = Store(data_dir=tmp_path)
    store2.load()
    m = store2.get_all_agent_metrics()[0]
    assert abs(m.budget_spent_usd - 4.75) < 1e-9
```

### Example 4 — Approvals and proposals

```python
def test_approvals_and_proposals(tmp_path: Path):
    """Add approvals/proposals and query pending items."""
    store = Store(data_dir=tmp_path)

    store.add_approval(Approval(id="a1", action="deploy", status=ApprovalStatus.PENDING))
    store.add_approval(Approval(id="a2", action="delete", status=ApprovalStatus.APPROVED))

    pending = store.pending_approvals()
    assert len(pending) == 1
    assert pending[0].id == "a1"

    store.add_proposal(ChangeProposal(
        id="cp1", title="Scale up workers",
        proposal_type=ProposalType.ADJUST_CONFIG,
    ))
    assert "cp1" in store.proposals
```

---

## Running Tests

Run the store module tests from the repository root:

```bash
python -m pytest tests/test_store.py -v --tb=short
```

To run a single test class:

```bash
python -m pytest tests/test_store.py::TestProjectCRUD -v --tb=short
```

To run the full test suite (all modules):

```bash
python -m pytest tests/ -v --tb=short
```
