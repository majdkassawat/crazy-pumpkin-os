import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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
    products: list[dict[str, Any]] = field(default_factory=list)
    llm: dict[str, Any] = field(default_factory=dict)
    agents: list[dict[str, Any]] = field(default_factory=list)
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
        raise ValueError("company.name is missing or empty")

    # products
    products = raw.get("products")
    if not products:
        raise ValueError("products list is absent or empty")

    # agents
    agents = raw.get("agents")
    if not agents:
        raise ValueError("agents list is absent or empty")

    # Resolve product workspace paths
    for product in products:
        ws = product.get("workspace")
        if ws:
            product["workspace"] = str(resolve_path(ws, project_root))

    # pipeline defaults
    pipeline = raw.get("pipeline") or {}
    pipeline.setdefault("cycle_interval", 30)
    pipeline["cycle_interval"] = int(pipeline["cycle_interval"])

    return Config(
        company=company,
        products=products,
        llm=raw.get("llm") or {},
        agents=agents,
        pipeline=pipeline,
        notifications=raw.get("notifications") or {},
        dashboard=raw.get("dashboard") or {},
        voice=raw.get("voice") or {},
    )


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
        with open(yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    elif json_path.is_file():
        with open(json_path, encoding="utf-8") as f:
            config = json.load(f)
    else:
        raise FileNotFoundError(
            f"No config.yaml or config/default.json found in {project_root}"
        )

    raw = _expand_vars(config)
    return _validate_and_build(raw, project_root)
