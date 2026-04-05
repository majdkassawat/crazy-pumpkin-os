"""Tests for tracing configuration: TracingConfig dataclass, env overrides, YAML loading, and doctor check."""

import sys
from dataclasses import fields
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.config import Config, TracingConfig, load_config
from crazypumpkin.config.env_override import apply_env_overrides
from crazypumpkin.cli.doctor import _check_tracing


# ── helpers ──────────────────────────────────────────────────────────────


def _minimal_valid() -> dict:
    return {
        "company": {"name": "TestCo"},
        "products": [{"name": "app", "workspace": "./products/app"}],
        "agents": [{"name": "Dev", "role": "execution"}],
    }


def _write_config(tmp_path: Path, data: dict) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump(data), encoding="utf-8")
    return cfg


# ── TracingConfig dataclass ──────────────────────────────────────────────


def test_tracing_config_has_five_fields():
    """TracingConfig dataclass has exactly 5 fields."""
    f = fields(TracingConfig)
    assert len(f) == 5


def test_tracing_config_field_names():
    """TracingConfig has the expected field names."""
    names = {f.name for f in fields(TracingConfig)}
    assert names == {"enabled", "provider", "public_key", "secret_key", "host"}


def test_tracing_config_defaults():
    """TracingConfig defaults match the specification."""
    tc = TracingConfig()
    assert tc.enabled is False
    assert tc.provider == "langfuse"
    assert tc.public_key == ""
    assert tc.secret_key == ""
    assert tc.host == "https://cloud.langfuse.com"


def test_tracing_config_custom_values():
    """TracingConfig accepts custom values."""
    tc = TracingConfig(
        enabled=True,
        provider="custom",
        public_key="pk-123",
        secret_key="sk-456",
        host="https://self-hosted.example.com",
    )
    assert tc.enabled is True
    assert tc.provider == "custom"
    assert tc.public_key == "pk-123"
    assert tc.secret_key == "sk-456"
    assert tc.host == "https://self-hosted.example.com"


# ── Main Config includes tracing field ───────────────────────────────────


def test_config_has_tracing_field():
    """Config dataclass has a tracing field."""
    field_names = {f.name for f in fields(Config)}
    assert "tracing" in field_names


def test_config_tracing_default_is_tracing_config():
    """Config.tracing defaults to a TracingConfig instance."""
    cfg = Config()
    assert isinstance(cfg.tracing, TracingConfig)
    assert cfg.tracing.enabled is False


# ── Config loads from YAML with tracing section ──────────────────────────


def test_load_config_with_tracing_section(tmp_path):
    """load_config parses a tracing section into TracingConfig."""
    data = _minimal_valid()
    data["tracing"] = {
        "enabled": True,
        "provider": "langfuse",
        "public_key": "pk-yaml",
        "secret_key": "sk-yaml",
        "host": "https://my-langfuse.example.com",
    }
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert isinstance(cfg.tracing, TracingConfig)
    assert cfg.tracing.enabled is True
    assert cfg.tracing.public_key == "pk-yaml"
    assert cfg.tracing.secret_key == "sk-yaml"
    assert cfg.tracing.host == "https://my-langfuse.example.com"


def test_load_config_without_tracing_section(tmp_path):
    """load_config returns default TracingConfig when tracing section is absent."""
    data = _minimal_valid()
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert isinstance(cfg.tracing, TracingConfig)
    assert cfg.tracing.enabled is False
    assert cfg.tracing.provider == "langfuse"
    assert cfg.tracing.host == "https://cloud.langfuse.com"


def test_load_config_partial_tracing_section(tmp_path):
    """Partial tracing section fills defaults for missing keys."""
    data = _minimal_valid()
    data["tracing"] = {"enabled": True}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.tracing.enabled is True
    assert cfg.tracing.provider == "langfuse"
    assert cfg.tracing.public_key == ""


# ── Env var overrides for tracing ────────────────────────────────────────


def test_env_override_tracing_enabled(monkeypatch):
    """CPOS_TRACING_ENABLED overrides tracing.enabled."""
    monkeypatch.setenv("CPOS_TRACING_ENABLED", "true")
    config = {"tracing": {"enabled": False, "provider": "langfuse"}}
    result = apply_env_overrides(config)
    assert result["tracing"]["enabled"] is True


def test_env_override_tracing_public_key(monkeypatch):
    """CPOS_TRACING_PUBLIC_KEY overrides tracing.public_key."""
    monkeypatch.setenv("CPOS_TRACING_PUBLIC_KEY", "pk-env")
    config = {"tracing": {"public_key": ""}}
    result = apply_env_overrides(config)
    assert result["tracing"]["public_key"] == "pk-env"


def test_env_override_tracing_secret_key(monkeypatch):
    """CPOS_TRACING_SECRET_KEY overrides tracing.secret_key."""
    monkeypatch.setenv("CPOS_TRACING_SECRET_KEY", "sk-env")
    config = {"tracing": {"secret_key": ""}}
    result = apply_env_overrides(config)
    assert result["tracing"]["secret_key"] == "sk-env"


def test_env_override_tracing_host(monkeypatch):
    """CPOS_TRACING_HOST overrides tracing.host."""
    monkeypatch.setenv("CPOS_TRACING_HOST", "https://custom.example.com")
    config = {"tracing": {"host": "https://cloud.langfuse.com"}}
    result = apply_env_overrides(config)
    assert result["tracing"]["host"] == "https://custom.example.com"


# ── Doctor tracing check ─────────────────────────────────────────────────


def test_doctor_tracing_disabled():
    """When tracing is disabled, the check passes with 'disabled' message."""
    mock_cfg = MagicMock()
    mock_cfg.tracing.enabled = False
    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_cfg, create=True), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_cfg):
        ok, msg = _check_tracing()
    assert ok is True
    assert "disabled" in msg


def test_doctor_tracing_enabled_missing_keys():
    """When tracing is enabled but keys are missing, the check fails."""
    mock_cfg = MagicMock()
    mock_cfg.tracing.enabled = True
    mock_cfg.tracing.public_key = ""
    mock_cfg.tracing.secret_key = ""
    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_cfg, create=True), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_cfg):
        ok, msg = _check_tracing()
    assert ok is False
    assert "missing" in msg


def test_doctor_tracing_enabled_reachable():
    """When tracing is enabled and Langfuse is reachable, the check passes."""
    mock_cfg = MagicMock()
    mock_cfg.tracing.enabled = True
    mock_cfg.tracing.public_key = "pk-test"
    mock_cfg.tracing.secret_key = "sk-test"
    mock_cfg.tracing.host = "https://cloud.langfuse.com"

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_cfg, create=True), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_cfg), \
         patch("httpx.get", return_value=mock_resp):
        ok, msg = _check_tracing()
    assert ok is True
    assert "reachable" in msg


def test_doctor_tracing_enabled_unreachable():
    """When tracing is enabled but Langfuse is unreachable, the check fails."""
    mock_cfg = MagicMock()
    mock_cfg.tracing.enabled = True
    mock_cfg.tracing.public_key = "pk-test"
    mock_cfg.tracing.secret_key = "sk-test"
    mock_cfg.tracing.host = "https://cloud.langfuse.com"

    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_cfg, create=True), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_cfg), \
         patch("httpx.get", side_effect=ConnectionError("no route")):
        ok, msg = _check_tracing()
    assert ok is False
    assert "unreachable" in msg


def test_doctor_tracing_server_error():
    """When Langfuse returns 500+, the check fails."""
    mock_cfg = MagicMock()
    mock_cfg.tracing.enabled = True
    mock_cfg.tracing.public_key = "pk-test"
    mock_cfg.tracing.secret_key = "sk-test"
    mock_cfg.tracing.host = "https://cloud.langfuse.com"

    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_cfg, create=True), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_cfg), \
         patch("httpx.get", return_value=mock_resp):
        ok, msg = _check_tracing()
    assert ok is False
    assert "500" in msg


def test_doctor_tracing_config_load_failure():
    """When config cannot be loaded, the tracing check fails gracefully."""
    with patch("crazypumpkin.framework.config.load_config", side_effect=FileNotFoundError):
        ok, msg = _check_tracing()
    assert ok is False
    assert "cannot load config" in msg
