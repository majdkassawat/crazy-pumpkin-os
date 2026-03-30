# API Documentation

Public API reference for Crazy Pumpkin OS.

## Versioning & Stability Commitments

Symbols marked **Stable Public API** are covered by semantic versioning:

- **Patch** releases (0.x.Y) contain only bug fixes — no signature changes.
- **Minor** releases (0.X.0) may add new optional parameters or fields but will not remove or rename existing ones.
- **Major** releases (X.0.0) may introduce breaking changes; a deprecation period of at least one minor release will precede removals.

The following symbols form the **stable public API surface**:

| Symbol | Module |
|---|---|
| `BaseAgent` | `crazypumpkin.framework.agent` |
| `@register_agent` | `crazypumpkin.framework.registry` |
| `AgentRegistry` | `crazypumpkin.framework.registry` |
| `default_registry` | `crazypumpkin.framework.registry` |
| `Task` | `crazypumpkin.framework.models` |
| `TaskOutput` | `crazypumpkin.framework.models` |
| `TaskStatus` | `crazypumpkin.framework.models` |
| `AgentRole` | `crazypumpkin.framework.models` |

All other symbols (internal helpers, private modules, underscore-prefixed names) are **not** part of the public API and may change without notice.

## Core Framework

### Models (`crazypumpkin.framework.models`)

#### TaskOutput — Stable Public API
```python
@dataclass
class TaskOutput:
    """Result produced by an execution agent.

    This is the return type of BaseAgent.execute(). Agent authors create
    instances of this to communicate results back to the framework.
    """
    content: str = ""                          # Agent's text response
    artifacts: dict[str, str] = field(...)     # {filename: file_content}
    metadata: dict[str, Any] = field(...)      # Arbitrary execution details
```

All fields are optional at construction time (they default to empty values),
so `TaskOutput(content="done")` is valid.

#### Task — Stable Public API
```python
@dataclass
class Task:
    """A unit of work assigned to an agent.

    Agents receive Task instances in execute(). The fields most relevant
    to agent authors are listed below.
    """
    id: str                        # Auto-generated 12-char hex UUID
    project_id: str                # Parent project ID
    title: str                     # Short task description
    description: str               # Detailed requirements
    status: TaskStatus             # Current lifecycle state
    assigned_to: str               # Agent ID of the assignee
    priority: int                  # 1 (highest) to 5 (lowest)
    dependencies: list[str]        # IDs of tasks this depends on
    acceptance_criteria: list[str] # Conditions for approval
    output: TaskOutput | None      # Agent execution result
    created_at: str                # ISO-8601 UTC timestamp
    updated_at: str                # ISO-8601 UTC timestamp
    metadata: dict[str, Any]       # Arbitrary metadata
```

#### TaskStatus — Stable Public API
```python
class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    ARCHIVED = "archived"
```

#### AgentRole — Stable Public API
```python
class AgentRole(str, Enum):
    """Role a registered agent fills within the organization."""
    ORCHESTRATOR = "orchestrator"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    REVIEWER = "reviewer"
    # … additional roles: GOVERNANCE, EVOLUTION, ARCHITECT, CEO,
    #   MARKET_INTEL, HUMAN_INTERFACE, OPS, TRIAGE,
    #   FRAMEWORK_DOCTOR, PRODUCT_MANAGER
```

#### Project
```python
@dataclass
class Project:
    id: str
    name: str                      # Derived from goal
    goal: str                      # Original goal text
    status: ProjectStatus          # ACTIVE, COMPLETED, PAUSED, CANCELLED
    workspace: str                 # Product workspace path
    task_ids: list[str]
```

### Agent Base Class (`crazypumpkin.framework.agent`) — Stable Public API

```python
class BaseAgent(ABC):
    """Abstract base for all agents.

    Subclass this to create a custom agent. You must implement execute();
    setup() and teardown() are optional lifecycle hooks.
    """

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    # ── Properties ──────────────────────────────────────────────────

    @property
    def id(self) -> str: ...          # Shortcut for self.agent.id

    @property
    def name(self) -> str: ...        # Shortcut for self.agent.name

    @property
    def role(self) -> AgentRole: ...  # Shortcut for self.agent.role

    # ── Lifecycle hooks ─────────────────────────────────────────────

    @abstractmethod
    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Execute a task and return an output.

        This is the only method you *must* implement. The framework calls
        it with a Task describing the work and a context dict containing
        runtime information (project metadata, codebase state, etc.).

        Returns:
            TaskOutput with content and optional artifacts.
        """
        ...

    def setup(self, context: dict[str, Any]) -> None:
        """Optional hook called *before* execute().

        Override to acquire resources, warm caches, or validate
        pre-conditions. The default implementation is a no-op.
        """

    def teardown(self, context: dict[str, Any]) -> None:
        """Optional hook called *after* execute().

        Always runs, even when execute() raises an exception.
        Override to release resources or record metrics.
        The default implementation is a no-op.
        """

    # ── Convenience methods ─────────────────────────────────────────

    def run(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Run the full agent lifecycle: setup → execute → teardown.

        Calls setup(), then execute(), then teardown(). Teardown is
        guaranteed to run even if execute() raises an exception.
        Prefer this over calling execute() directly.

        Returns:
            TaskOutput from execute().
        """

    def can_handle(self, task: Task) -> bool:
        """Whether this agent can handle the given task.

        Override for custom routing logic. Returns True by default.
        """
```

#### Minimal agent example

```python
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, Task, TaskOutput

class MyAgent(BaseAgent):
    def execute(self, task, context):
        return TaskOutput(content=f"Completed: {task.title}")
```

### `@register_agent` Decorator (`crazypumpkin.framework.registry`) — Stable Public API

```python
def register_agent(
    name: str,
    role: AgentRole,
    registry: AgentRegistry | None = None,
) -> Callable[[type], type]:
    """Class decorator that instantiates and registers a BaseAgent subclass.

    Args:
        name: Display name for the agent.
        role: The agent's role in the organization (see AgentRole enum).
        registry: Registry to add the agent to.
                  Defaults to the module-level ``default_registry``.

    Returns:
        The original class, unmodified.
    """
```

#### Usage example

```python
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import AgentRole, Task, TaskOutput
from crazypumpkin.framework.registry import register_agent

@register_agent(name="my-agent", role=AgentRole.EXECUTION)
class MyAgent(BaseAgent):
    def execute(self, task, context):
        return TaskOutput(content="done")
```

### AgentRegistry (`crazypumpkin.framework.registry`) — Stable Public API

```python
class AgentRegistry:
    """Central registry of all agents in the organization."""

    def register(self, agent: BaseAgent) -> None:
        """Add an agent to the registry."""

    def unregister(self, agent_id: str) -> BaseAgent | None:
        """Remove and return an agent by ID, or None."""

    def get(self, agent_id: str) -> BaseAgent | None:
        """Look up an agent by its ID."""

    def by_role(self, role: AgentRole) -> list[BaseAgent]:
        """Return all active agents with the given role."""

    def by_name(self, name: str) -> BaseAgent | None:
        """Look up an agent by display name."""

    def all_active(self) -> list[BaseAgent]:
        """Return all agents whose status is ACTIVE."""

    def active_ids(self) -> set[str]:
        """Return the set of all registered agent IDs."""

    @property
    def count(self) -> int:
        """Number of registered agents."""

    def summary(self) -> dict[str, int]:
        """Count of agents per role."""
```

A module-level `default_registry` instance is available:

```python
from crazypumpkin.framework.registry import default_registry
```

### Store (`crazypumpkin.framework.store`)

```python
class Store:
    # Projects
    def add_project(project: Project) -> None
    def get_project(project_id: str) -> Project | None

    # Tasks
    def add_task(task: Task) -> None
    def get_task(task_id: str) -> Task | None
    def tasks_by_project(project_id: str) -> list[Task]
    def tasks_by_status(status: str) -> list[Task]

    # Persistence
    def save() -> None        # Write to data/state.json
    def load() -> bool        # Load from data/state.json
```

### Config (`crazypumpkin.framework.config`)

```python
def load_config(path: str = "config.yaml") -> dict:
    """Load and validate configuration."""

def get_product_config(workspace: str) -> dict:
    """Get product-specific configuration by workspace path."""
```

## LLM Providers (`crazypumpkin.llm`)

### Registry

```python
from crazypumpkin.llm.registry import get_provider, register_provider

# Get the configured provider
provider = get_provider("anthropic")
response = provider.call("Your prompt here", model="sonnet")

# Register a custom provider
register_provider("my_provider", MyProviderClass)
```

### Supported Providers

| Provider | Module | Models |
|----------|--------|--------|
| Anthropic | `crazypumpkin.llm.anthropic_api` | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 |
| OpenAI | `crazypumpkin.llm.openai_api` | gpt-4, gpt-4-turbo, gpt-3.5-turbo |
| Ollama | (via config) | Any locally hosted model |

## CLI (`crazypumpkin.cli`)

```bash
# Initialize a new project
crazypumpkin init

# Run the pipeline
crazypumpkin run --config config.yaml

# Show pipeline status
crazypumpkin status
```

## Scheduler (`crazypumpkin.scheduler`)

```python
from crazypumpkin.scheduler.scheduler import Scheduler

scheduler = Scheduler(config)
scheduler.run_cycle()  # Execute one pipeline cycle
```

## Events (`crazypumpkin.framework.events`)

```python
from crazypumpkin.framework.events import EventBus

bus = EventBus()
bus.emit(agent_id="my_agent", action="task.completed", detail="Done")
```

## Configuration Format

See `examples/config.yaml` for a complete example. Key sections:

```yaml
company:
  name: "My Company"
  products:
    - name: "My Product"
      workspace: "./my-product"
      test_command: "python -m pytest tests/"

agents:
  - name: "My Agent"
    role: "execution"
    class: "path.to.AgentClass"
    model: "sonnet"
    trigger:
      expression: "planned_tasks > 0"
      cooldown_sec: 30

llm:
  provider: "anthropic"
  api_key: "${ANTHROPIC_API_KEY}"
```
