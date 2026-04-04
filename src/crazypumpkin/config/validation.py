"""Configuration schema validation using Pydantic and PipelineConfig."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from crazypumpkin.framework.config import PipelineConfig


class ConfigFieldError(BaseModel):
    """A single validation error for a config field."""
    path: str
    message: str
    value: Any | None = None


class ValidationResult(BaseModel):
    """Result of validating a configuration dict."""
    valid: bool
    errors: list[ConfigFieldError]


def validate_config(config: dict[str, Any], strict: bool = False) -> ValidationResult:
    """Validate a config dict against the PipelineConfig schema.

    In strict mode, unknown top-level keys are reported as errors.
    All errors are collected (not fail-fast).
    """
    errors: list[ConfigFieldError] = []

    # Use Pydantic validation to collect schema errors
    try:
        PipelineConfig.model_validate(config)
    except ValidationError as exc:
        for err in exc.errors():
            loc_parts = [str(p) for p in err["loc"]]
            path = ".".join(loc_parts)
            # Try to extract the value at the error location
            val = config
            for part in err["loc"]:
                if isinstance(val, dict):
                    val = val.get(str(part))
                elif isinstance(val, list):
                    try:
                        val = val[int(part)]
                    except (IndexError, ValueError, TypeError):
                        val = None
                        break
                else:
                    val = None
                    break
            errors.append(ConfigFieldError(
                path=path,
                message=err["msg"],
                value=val,
            ))

    # Strict mode: flag unknown top-level keys
    if strict:
        known_fields = set(PipelineConfig.model_fields.keys())
        for key in config:
            if key not in known_fields:
                errors.append(ConfigFieldError(
                    path=key,
                    message=f"Unknown configuration key: {key}",
                    value=config[key],
                ))

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_config_file(path: Path, strict: bool = False) -> ValidationResult:
    """Read a YAML or JSON config file and validate it."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    _ALLOWED_EXTENSIONS = {".yaml", ".yml", ".json"}
    suffix = path.suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported config file extension '{suffix}'. "
            f"Allowed extensions: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )

    if suffix in (".yaml", ".yml"):
        config = yaml.safe_load(text) or {}
    else:
        config = json.loads(text)

    if not isinstance(config, dict):
        raise ValueError(
            f"Config file {path} must contain a mapping at the top level, "
            f"got {type(config).__name__}"
        )

    return validate_config(config, strict=strict)
