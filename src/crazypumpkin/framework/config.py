import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import AgentDefinition, AgentRole, ProductConfig
from .paths import get_project_root, resolve_path


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
            class_path=a.get("class", ""),
        ))

    # pipeline defaults
    pipeline = raw.get("pipeline") or {}
    pipeline.setdefault("cycle_interval", 30)
    pipeline["cycle_interval"] = int(pipeline["cycle_interval"])

    return Config(
        company=company,
        products=parsed_products,
        llm=raw.get("llm") or {},
        agents=parsed_agents,
        pipeline=pipeline,
        notifications=raw.get("notifications") or {},
        dashboard=raw.get("dashboard") or {},
        voice=raw.get("voice") or {},
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