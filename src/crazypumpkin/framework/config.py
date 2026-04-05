import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ValidationError

from .models import AgentDefinition, AgentRole, ProductConfig
from .paths import get_project_root, resolve_path


# ---------------------------------------------------------------------------
# Pydantic-based PipelineConfig for schema validation & hot-reload
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Pydantic schema for the full pipeline configuration.

    Used by :mod:`crazypumpkin.config.validation` for schema-level
    validation and by :meth:`apply_reload` for hot-reload diffing.
    """
    model_config = {"extra": "allow"}

    company: dict[str, Any] = {}
    products: list[dict[str, Any]] = []
    llm: dict[str, Any] = {}
    agents: list[dict[str, Any]] = []
    pipeline: dict[str, Any] = {}
    notifications: dict[str, Any] = {}
    dashboard: dict[str, Any] = {}
    voice: dict[str, Any] = {}
    triggers: list[Any] = []
    plugins: list[Any] = []
    observability: dict[str, Any] = {}
    scheduler: dict[str, Any] = {}
    tracing: dict[str, Any] = {}

    def apply_reload(
        self,
        new_raw: dict,
        event_bus: Optional[Any] = None,
    ) -> list["ConfigChange"]:
        """Apply a new config dict, returning a list of changed fields.

        1. Validates *new_raw* via :func:`crazypumpkin.config.validation.validate_config`.
        2. Diffs against current values, building a :class:`ConfigChange` list.
        3. Updates ``self`` in-place for changed fields.
        4. If *event_bus* is provided, emits a ``config.reloaded`` event.
        5. Returns the list of changes (empty if nothing changed).

        Raises :class:`pydantic.ValidationError` if *new_raw* is invalid,
        leaving the current config untouched.
        """
        # Validate — raises ValidationError on bad input
        PipelineConfig.model_validate(new_raw)

        changes: list[ConfigChange] = []
        fields = PipelineConfig.model_fields
        for field_name in fields:
            old_value = getattr(self, field_name)
            new_value = new_raw.get(field_name, fields[field_name].default)
            if old_value != new_value:
                changes.append(ConfigChange(
                    field=field_name,
                    old_value=old_value,
                    new_value=new_value,
                ))
                setattr(self, field_name, new_value)

        if event_bus is not None and changes:
            from .events import EventBus, CONFIG_RELOADED
            event_bus.emit(
                agent_id="system",
                action=CONFIG_RELOADED,
                entity_type="config",
                detail=f"{len(changes)} field(s) changed",
                metadata={"changes": [
                    {"field": c.field, "old_value": c.old_value, "new_value": c.new_value}
                    for c in changes
                ]},
            )

        return changes


@dataclass
class ConfigChange:
    """Describes a single field-level change during config reload."""
    field: str
    old_value: object
    new_value: object


def _expand_vars(value: Any) -> Any:
    """Recursively expand ${VAR_NAME} patterns in all string values."""
    if isinstance(value, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {k: _expand_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_vars(item) for item in value]
    return value


@dataclass
class TracingConfig:
    """Configuration for LLM call tracing / observability."""
    enabled: bool = False
    provider: str = 'langfuse'
    public_key: str = ''
    secret_key: str = ''
    host: str = 'https://cloud.langfuse.com'


@dataclass
class Config:
    """Typed, validated configuration object."""
    company: dict[str, Any] = field(default_factory=dict)
    products: list[ProductConfig] = field(default_factory=list)
    llm: dict[str, Any] = field(default_factory=dict)
    agents: list[AgentDefinition] = field(default_factory=list)
    pipeline: dict[str, Any] = field(default_factory=dict)
    notifications: dict[str, Any] = field(default_factory=dict)
    dashboard: dict[str, Any] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)
    tracing: TracingConfig = field(default_factory=TracingConfig)


def _validate_and_build(raw: dict, project_root: Path) -> Config:
    """Validate required fields and return a typed Config."""
    # company.name
    company = raw.get("company") or {}
    name = company.get("name")
    if not name or not str(name).strip():
        raise ValueError(
            "Missing required field: company.name\n"
            "\n"
            "The 'company' section requires a 'name' field.\n"
            "Example:\n"
            "  company:\n"
            "    name: YourCompany"
        )

    # products
    products_raw = raw.get("products")
    if not products_raw:
        raise ValueError(
            "Missing required section: products\n"
            "\n"
            "The 'products' section must contain a list of product configurations.\n"
            "Each product requires 'name' and 'workspace' fields.\n"
            "Example:\n"
            "  products:\n"
            "    - name: MyApp\n"
            "      workspace: ./products/app\n"
            "      source_dir: src\n"
            "      test_dir: tests"
        )

    parsed_products: list[ProductConfig] = []
    for i, p in enumerate(products_raw):
        pname = p.get("name")
        if not pname or not str(pname).strip():
            raise ValueError(
                f"Missing required field in products[{i}]: name\n"
                "\n"
                f"Product entry at index {i} is missing the 'name' field.\n"
                "Each product must have:\n"
                "  - name: Product name (required)\n"
                "  - workspace: Path to product directory (required)\n"
                "Example:\n"
                "  products:\n"
                "    - name: \"<missing>\"\n"
                "      workspace: ./products/app"
            )
        pworkspace = p.get("workspace")
        if not pworkspace or not str(pworkspace).strip():
            raise ValueError(
                f"Missing required field in products[{i}] ('{pname}'): workspace\n"
                "\n"
                f"Product '{pname}' is missing the 'workspace' field.\n"
                "The workspace specifies the directory containing the product code.\n"
                "Example:\n"
                "  products:\n"
                f"    - name: {pname}\n"
                f"      workspace: ./products/{pname.lower()}"
            )
        resolved_ws = str(resolve_path(pworkspace, project_root))
        parsed_products.append(ProductConfig(
            name=str(pname),
            workspace=resolved_ws,
            source_dir=p.get("source_dir", "src"),
            test_dir=p.get("test_dir", "tests"),
            test_command=p.get("test_command", ""),
            git_branch=p.get("git_branch", "main"),
            auto_pm=bool(p.get("auto_pm", False)),
        ))

    # agents
    agents_raw = raw.get("agents")
    if not agents_raw:
        raise ValueError(
            "Missing required section: agents\n"
            "\n"
            "The 'agents' section must contain a list of agent definitions.\n"
            "Each agent requires 'name' and 'role' fields.\n"
            "Valid roles: strategy, execution, review\n"
            "Example:\n"
            "  agents:\n"
            "    - name: Strategist\n"
            "      role: strategy\n"
            "    - name: Developer\n"
            "      role: execution\n"
            "    - name: Reviewer\n"
            "      role: review"
        )

    parsed_agents: list[AgentDefinition] = []
    for i, a in enumerate(agents_raw):
        aname = a.get("name")
        if not aname or not str(aname).strip():
            raise ValueError(
                f"Missing required field in agents[{i}]: name\n"
                "\n"
                f"Agent entry at index {i} is missing the 'name' field.\n"
                "Each agent must have:\n"
                "  - name: Agent name (required)\n"
                "  - role: Agent role (required, one of: strategy, execution, review)\n"
                "Example:\n"
                "  agents:\n"
                "    - name: Developer\n"
                "      role: execution"
            )
        arole = a.get("role")
        if not arole or not str(arole).strip():
            raise ValueError(
                f"Missing required field in agents[{i}] ('{aname}'): role\n"
                "\n"
                f"Agent '{aname}' is missing the 'role' field.\n"
                "Valid roles are:\n"
                "  - strategy: Plans and decomposes tasks\n"
                "  - execution: Implements code changes\n"
                "  - review: Reviews and validates changes\n"
                "Example:\n"
                "  agents:\n"
                f"    - name: {aname}\n"
                "      role: execution"
            )
        try:
            role_enum = AgentRole(str(arole))
        except ValueError:
            valid_roles = ", ".join(r.value for r in AgentRole)
            raise ValueError(
                f"Invalid role in agents[{i}] ('{aname}'): '{arole}'\n"
                "\n"
                f"Agent '{aname}' has an invalid role '{arole}'.\n"
                f"Valid roles are: {valid_roles}\n"
                "  - strategy: Plans and decomposes tasks\n"
                "  - execution: Implements code changes\n"
                "  - review: Reviews and validates changes\n"
                "Example:\n"
                "  agents:\n"
                f"    - name: {aname}\n"
                "      role: execution"
            )
        parsed_agents.append(AgentDefinition(
            name=str(aname),
            role=role_enum,
            description=a.get("description", ""),
            model=a.get("model", ""),
            group=a.get("group", ""),
            trigger=a.get("trigger", ""),
            cooldown_seconds=int(a.get("cooldown_seconds", 0)),
            class_path=a.get("class", ""),
            cron=a.get("cron", ""),
        ))

    # notifications — validate slack sub-section if present
    notifications = raw.get("notifications") or {}
    slack_cfg = notifications.get("slack")
    if slack_cfg is not None:
        if not isinstance(slack_cfg, dict):
            raise ValueError(
                "Invalid notifications.slack: expected a mapping\n"
                "\n"
                "The 'slack' section must be a mapping with at least 'webhook_url'.\n"
                "Example:\n"
                "  notifications:\n"
                "    slack:\n"
                "      webhook_url: ${SLACK_WEBHOOK_URL}\n"
                "      channel: \"#general\"\n"
                "      bot_name: CrazyPumpkin"
            )
        webhook_url = slack_cfg.get("webhook_url")
        if not webhook_url or not str(webhook_url).strip():
            raise ValueError(
                "Missing required field: notifications.slack.webhook_url\n"
                "\n"
                "The 'slack' section requires a 'webhook_url' field.\n"
                "Example:\n"
                "  notifications:\n"
                "    slack:\n"
                "      webhook_url: ${SLACK_WEBHOOK_URL}"
            )

    # pipeline defaults
    pipeline = raw.get("pipeline") or {}
    pipeline.setdefault("cycle_interval", 30)
    pipeline["cycle_interval"] = int(pipeline["cycle_interval"])

    # tracing
    tracing_raw = raw.get("tracing") or {}
    tracing = TracingConfig(
        enabled=bool(tracing_raw.get("enabled", False)),
        provider=str(tracing_raw.get("provider", "langfuse")),
        public_key=str(tracing_raw.get("public_key", "")),
        secret_key=str(tracing_raw.get("secret_key", "")),
        host=str(tracing_raw.get("host", "https://cloud.langfuse.com")),
    )

    return Config(
        company=company,
        products=parsed_products,
        llm=raw.get("llm") or {},
        agents=parsed_agents,
        pipeline=pipeline,
        notifications=raw.get("notifications") or {},
        dashboard=raw.get("dashboard") or {},
        voice=raw.get("voice") or {},
        tracing=tracing,
    )


# Pre-defined error message templates to avoid f-string issues with braces
_YAML_SYNTAX_EXAMPLE = """YAML syntax error in {} at line {}, column {}:
  {}

Expected format: YAML with proper indentation and syntax.
Example:
  company:
    name: YourCompany
  products:
    - name: MyApp
      workspace: ./products/app
  agents:
    - name: Dev
      role: execution"""

_YAML_GENERIC_ERROR = """YAML parsing error in {}:
  {}

Please check the YAML syntax. Common issues:
  - Missing quotes around special characters
  - Incorrect indentation
  - Duplicate keys"""

_JSON_SYNTAX_EXAMPLE = """JSON syntax error in {} at line {}, column {}:
  {}

Expected format: Valid JSON with proper structure.
Example:
  {
    "company": {"name": "YourCompany"},
    "products": [{"name": "MyApp", "workspace": "./products/app"}],
    "agents": [{"name": "Dev", "role": "execution"}]
  }"""

_CONFIG_NOT_FOUND = """No configuration file found in {}.

Expected: config.yaml or config/default.json
Please create a configuration file with the following structure:

  company:
    name: YourCompany
  products:
    - name: MyApp
      workspace: ./products/app
  agents:
    - name: Dev
      role: execution"""


def load_config(project_root: Path | None = None) -> Config:
    """Load configuration from config.yaml or config/default.json.

    Reads config.yaml from project_root (primary) or falls back to
    config/default.json. All ${VAR_NAME} patterns in string values are
    expanded from environment variables. Validates required fields and
    returns a typed Config dataclass.
    """
    if project_root is None:
        project_root = get_project_root()
    project_root = Path(project_root)

    yaml_path = project_root / "config.yaml"
    json_path = project_root / "config" / "default.json"

    if yaml_path.is_file():
        try:
            with open(yaml_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            # Extract line number from YAML error if available
            line_num = getattr(e, 'problem_mark', None)
            if line_num:
                line = line_num.line + 1  # YAML marks are 0-indexed
                col = line_num.column + 1
                problem = e.problem if hasattr(e, 'problem') else str(e)
                raise ValueError(
                    _YAML_SYNTAX_EXAMPLE.format(yaml_path, line, col, problem)
                ) from e
            else:
                raise ValueError(
                    _YAML_GENERIC_ERROR.format(yaml_path, str(e))
                ) from e
    elif json_path.is_file():
        try:
            with open(json_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                _JSON_SYNTAX_EXAMPLE.format(json_path, e.lineno, e.colno, e.msg)
            ) from e
    else:
        raise FileNotFoundError(_CONFIG_NOT_FOUND.format(project_root))

    raw = _expand_vars(config)
    return _validate_and_build(raw, project_root)


def save_config(config: Config, project_root: Path | None = None) -> None:
    """Serialize *config* back to config.yaml in *project_root*.

    Writes the configuration as YAML, preserving the structure expected by
    :func:`load_config`.
    """
    if project_root is None:
        project_root = get_project_root()
    project_root = Path(project_root)

    agents_raw = []
    for a in config.agents:
        entry: dict[str, Any] = {
            "name": a.name,
            "role": a.role.value if isinstance(a.role, AgentRole) else a.role,
        }
        if a.description:
            entry["description"] = a.description
        if a.model:
            entry["model"] = a.model
        if a.group:
            entry["group"] = a.group
        if a.trigger:
            entry["trigger"] = a.trigger
        if a.class_path:
            entry["class"] = a.class_path
        if a.cron:
            entry["cron"] = a.cron
        agents_raw.append(entry)

    products_raw = []
    for p in config.products:
        products_raw.append({
            "name": p.name,
            "workspace": p.workspace,
            "source_dir": p.source_dir,
            "test_dir": p.test_dir,
            "test_command": p.test_command,
            "git_branch": p.git_branch,
            "auto_pm": p.auto_pm,
        })

    tracing_raw = {
        "enabled": config.tracing.enabled,
        "provider": config.tracing.provider,
        "public_key": config.tracing.public_key,
        "secret_key": config.tracing.secret_key,
        "host": config.tracing.host,
    }

    raw: dict[str, Any] = {
        "company": config.company,
        "products": products_raw,
        "llm": config.llm,
        "agents": agents_raw,
        "pipeline": config.pipeline,
        "notifications": config.notifications,
        "dashboard": config.dashboard,
        "voice": config.voice,
        "tracing": tracing_raw,
    }

    yaml_path = project_root / "config.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)