"""Edge-case tests for the products section of config.yaml."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import _write_init_files


@pytest.fixture()
def answers():
    return {
        "company_name": "Test Corp",
        "provider": "anthropic_api",
        "api_key": "sk-test-key",
        "product_path": "/some/product",
        "dashboard_password": "s3cr3t",
    }


def _load_config(tmp_path):
    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


def test_products_name_with_special_chars(tmp_path, answers):
    """Products name handles company names with special characters."""
    answers["company_name"] = "Acme & Sons"
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["name"] == "Acme & Sons Product"


def test_products_workspace_with_spaces(tmp_path, answers):
    """Products workspace preserves paths with spaces."""
    answers["product_path"] = "/some/path with spaces/product"
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["workspace"] == "/some/path with spaces/product"


def test_products_workspace_empty_string(tmp_path, answers):
    """Products workspace handles empty string product_path."""
    answers["product_path"] = ""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["workspace"] == ""


def test_products_name_reflects_company_name(tmp_path, answers):
    """Products name dynamically uses the company_name from answers."""
    answers["company_name"] = "Widget Factory"
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["name"] == "Widget Factory Product"


def test_products_auto_pm_is_boolean_false(tmp_path, answers):
    """auto_pm is a boolean False, not a string."""
    _write_init_files(answers, tmp_path)
    product = _load_config(tmp_path)["products"][0]
    assert product["auto_pm"] is False
    assert not isinstance(product["auto_pm"], str)


def test_products_section_keys_complete(tmp_path, answers):
    """products[0] has exactly the expected set of keys."""
    _write_init_files(answers, tmp_path)
    product = _load_config(tmp_path)["products"][0]
    expected_keys = {"name", "workspace", "source_dir", "test_dir",
                     "test_command", "git_branch", "auto_pm"}
    assert set(product.keys()) == expected_keys


def test_products_name_equals_company_product(tmp_path, answers):
    """products[0].name equals '{company_name} Product'."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["name"] == f"{answers['company_name']} Product"


def test_products_workspace_equals_product_path(tmp_path, answers):
    """products[0].workspace equals answers['product_path']."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["workspace"] == answers["product_path"]


def test_products_static_fields(tmp_path, answers):
    """products[0] contains the expected static field values."""
    _write_init_files(answers, tmp_path)
    product = _load_config(tmp_path)["products"][0]
    assert product["source_dir"] == "src"
    assert product["test_dir"] == "tests"
    assert product["test_command"] == "python -m pytest tests/ -v --tb=short"
    assert product["git_branch"] == "main"
    assert product["auto_pm"] is False


def test_products_section_exactly_one_entry(tmp_path, answers):
    """The products section is valid YAML and produces exactly one entry."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert isinstance(cfg["products"], list)
    assert len(cfg["products"]) == 1
