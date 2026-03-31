"""ConfigSchema validator with field-level type checking and required-field enforcement."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationError:
    path: str
    message: str
    suggestion: str = ""


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)


# Type string -> Python type mapping
_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
}


def _check_type(value: Any, expected: str) -> bool:
    """Check if value matches the expected type string."""
    if expected == "number":
        return isinstance(value, (int, float))
    py_type = _TYPE_MAP.get(expected)
    if py_type is None:
        return True  # unknown type spec — skip check
    # bool is subclass of int in Python, so exclude bools from int/float checks
    if expected in ("int", "float") and isinstance(value, bool):
        return False
    return isinstance(value, py_type)


def _validate_node(
    value: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> None:
    """Recursively validate a value against a schema node."""
    expected_type = schema.get("type")

    if expected_type and not _check_type(value, expected_type):
        errors.append(ValidationError(
            path=path or "(root)",
            message=f"Expected type '{expected_type}', got '{type(value).__name__}'",
        ))
        return  # no point checking children if type is wrong

    # Dict validation
    if expected_type == "dict" and isinstance(value, dict):
        known_fields = schema.get("fields", {})
        required_fields = schema.get("required_fields", [])
        known_names = list(known_fields.keys())

        # Check required fields
        for req in required_fields:
            if req not in value:
                errors.append(ValidationError(
                    path=f"{path}.{req}" if path else req,
                    message=f"Required field '{req}' is missing",
                ))

        # Check each present field
        for key, child_val in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in known_fields:
                _validate_node(child_val, known_fields[key], child_path, errors, warnings)
            else:
                # Unknown field — suggest close matches
                matches = difflib.get_close_matches(key, known_names, n=1, cutoff=0.6)
                suggestion = f"Did you mean '{matches[0]}'?" if matches else ""
                warnings.append(ValidationError(
                    path=child_path,
                    message=f"Unknown field '{key}'",
                    suggestion=suggestion,
                ))

    # List validation
    elif expected_type == "list" and isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                item_path = f"{path}.{i}" if path else str(i)
                _validate_node(item, items_schema, item_path, errors, warnings)


def get_default_schema() -> dict[str, Any]:
    """Return the built-in CP-OS config schema with all known sections and their types/required fields."""
    return {
        "type": "dict",
        "required_fields": ["company", "agents"],
        "fields": {
            "company": {
                "type": "dict",
                "required_fields": ["name"],
                "fields": {
                    "name": {"type": "str"},
                },
            },
            "products": {
                "type": "list",
                "items": {
                    "type": "dict",
                    "required_fields": ["name", "workspace"],
                    "fields": {
                        "name": {"type": "str"},
                        "workspace": {"type": "str"},
                        "source_dir": {"type": "str"},
                        "test_dir": {"type": "str"},
                        "test_command": {"type": "str"},
                        "git_branch": {"type": "str"},
                        "auto_pm": {"type": "bool"},
                    },
                },
            },
            "agents": {
                "type": "list",
                "items": {
                    "type": "dict",
                    "required_fields": ["name", "role"],
                    "fields": {
                        "name": {"type": "str"},
                        "role": {"type": "str"},
                        "description": {"type": "str"},
                        "model": {"type": "str"},
                        "group": {"type": "str"},
                        "trigger": {"type": "str"},
                        "class": {"type": "str"},
                        "schedule": {"type": "str"},
                    },
                },
            },
            "triggers": {
                "type": "list",
                "items": {
                    "type": "dict",
                    "fields": {
                        "name": {"type": "str"},
                        "type": {"type": "str"},
                        "schedule": {"type": "str"},
                    },
                },
            },
            "notifications": {
                "type": "dict",
                "fields": {
                    "providers": {"type": "list"},
                    "enabled": {"type": "bool"},
                },
            },
            "llm": {
                "type": "dict",
                "fields": {
                    "default_provider": {"type": "str"},
                    "providers": {"type": "dict"},
                    "agent_models": {"type": "dict"},
                },
            },
            "observability": {
                "type": "dict",
                "fields": {
                    "enabled": {"type": "bool"},
                    "exporters": {"type": "list"},
                },
            },
            "scheduler": {
                "type": "dict",
                "fields": {
                    "enabled": {"type": "bool"},
                    "interval": {"type": "int"},
                },
            },
            "plugins": {
                "type": "list",
                "items": {
                    "type": "dict",
                    "fields": {
                        "name": {"type": "str"},
                        "enabled": {"type": "bool"},
                    },
                },
            },
            "dashboard": {
                "type": "dict",
                "fields": {
                    "port": {"type": "int"},
                    "host": {"type": "str"},
                    "password": {"type": "str"},
                    "enabled": {"type": "bool"},
                },
            },
            "pipeline": {
                "type": "dict",
                "fields": {
                    "cycle_interval": {"type": "int"},
                },
            },
            "voice": {
                "type": "dict",
                "fields": {
                    "enabled": {"type": "bool"},
                },
            },
        },
    }


def validate_config(
    config: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> ValidationResult:
    """Validate a config dict against the CP-OS config schema.

    If schema is None, use the built-in default schema.
    """
    if not isinstance(config, dict):
        return ValidationResult(
            valid=False,
            errors=[ValidationError(path="(root)", message="Config must be a dict")],
        )

    if schema is None:
        schema = get_default_schema()

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    _validate_node(config, schema, "", errors, warnings)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
