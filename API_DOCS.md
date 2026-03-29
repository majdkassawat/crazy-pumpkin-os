# API Documentation

Public API reference for Crazy Pumpkin OS.

## Core Framework

### Models (`crazypumpkin.framework.models`)

#### Task
```python
@dataclass
class Task:
    id: str                        # Auto-generated 12-char hex UUID
    project_id: str                # Parent project ID
    title: str                     # Short task description
    description: str               # Detailed requirements
    status: TaskStatus             # Current lifecycle state
    priority: int                  # 1 (highest) to 5 (lowest)
    acceptance_criteria: list[str] # Conditions for approval
    output: TaskOutput | None      # Agent execution result
```

#### TaskStatus
```python
class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ARCHIVED = "archived"
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
    priority: int
    task_ids: list[str]
```

#### TaskOutput
```python
@dataclass
class TaskOutput:
    content: str                   # Agent's text response
    artifacts: dict[str, str]      # {filename: file_content}
    metadata: dict[str, Any]       # Execution details
```

### Agent Base Class (`crazypumpkin.framework.agent`)

```python
class BaseAgent:
    def __init__(self, agent: Agent):
        self.agent = agent

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Execute a task. Override in subclasses."""
        raise NotImplementedError

    def can_handle(self, task: Task) -> bool:
        """Check if this agent can handle the given task."""
        return True
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
