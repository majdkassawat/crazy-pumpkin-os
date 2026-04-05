"""Tests for the click-based ``crazypumpkin plugin list`` and ``crazypumpkin plugin info`` commands."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cli
from crazypumpkin.framework.models import PluginManifest


# -- helpers ----------------------------------------------------------------

def _make_manifest(name="test-plugin", version="1.0.0", entry_point="pkg.mod:Cls",
                   plugin_type="agent", description="A test plugin"):
    return PluginManifest(
        name=name, version=version, entry_point=entry_point,
        plugin_type=plugin_type, description=description,
    )


# -- plugin list ------------------------------------------------------------


class TestPluginList:
    """Tests for ``crazypumpkin plugin list``."""

    def test_table_columns_present(self):
        manifests = [
            _make_manifest(name="alpha", version="2.0.0"),
            _make_manifest(name="beta", version="0.3.1"),
        ]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=manifests):
            result = runner.invoke(cli, ["plugin", "list"])

        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Version" in result.output
        assert "Source" in result.output
        assert "Status" in result.output

    def test_plugin_rows_displayed(self):
        manifests = [
            _make_manifest(name="alpha", version="2.0.0"),
            _make_manifest(name="beta", version="0.3.1"),
        ]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=manifests):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "alpha" in result.output
        assert "2.0.0" in result.output
        assert "beta" in result.output
        assert "0.3.1" in result.output

    def test_source_entrypoint_when_in_ep_list(self):
        ep_plugin = _make_manifest(name="ep-plug", version="1.0.0")
        all_plugins = [ep_plugin]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[ep_plugin]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=all_plugins):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "entrypoint" in result.output

    def test_source_directory_when_not_in_ep_list(self):
        dir_plugin = _make_manifest(name="dir-plug", version="1.0.0")
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[dir_plugin]):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "directory" in result.output

    def test_status_ok_when_entry_point_set(self):
        manifests = [_make_manifest(name="good", entry_point="pkg:Cls")]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=manifests):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "ok" in result.output

    def test_status_error_when_no_entry_point(self):
        manifests = [_make_manifest(name="broken", entry_point="")]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=manifests):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "error" in result.output

    def test_empty_table_when_no_plugins(self):
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[]):
            result = runner.invoke(cli, ["plugin", "list"])

        assert result.exit_code == 0
        assert "No plugins found" in result.output

    def test_no_header_when_empty(self):
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[]):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "Name" not in result.output

    def test_unknown_version_fallback(self):
        manifests = [_make_manifest(name="noversion", version="")]
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=manifests):
            result = runner.invoke(cli, ["plugin", "list"])

        assert "unknown" in result.output


# -- plugin info ------------------------------------------------------------


class TestPluginInfo:
    """Tests for ``crazypumpkin plugin info <name>``."""

    def test_outputs_yaml_manifest(self):
        plugin = _make_manifest(name="my-plugin", version="1.2.3", description="A great plugin")
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[plugin]):
            result = runner.invoke(cli, ["plugin", "info", "my-plugin"])

        assert result.exit_code == 0
        parsed = yaml.safe_load(result.output)
        assert parsed["name"] == "my-plugin"
        assert parsed["version"] == "1.2.3"
        assert parsed["description"] == "A great plugin"

    def test_yaml_contains_agents_and_hooks(self):
        plugin = _make_manifest(name="my-plugin", version="1.0.0")
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[plugin]):
            result = runner.invoke(cli, ["plugin", "info", "my-plugin"])

        parsed = yaml.safe_load(result.output)
        assert "agents" in parsed
        assert "hooks" in parsed

    def test_nonexistent_plugin_exits_with_error(self):
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[]):
            result = runner.invoke(cli, ["plugin", "info", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_nonexistent_plugin_error_message_includes_name(self):
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[]):
            result = runner.invoke(cli, ["plugin", "info", "ghost-plugin"])

        assert "ghost-plugin" in result.output

    def test_info_shows_source_entrypoint(self):
        plugin = _make_manifest(name="ep-plug", version="1.0.0")
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[plugin]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[plugin]):
            result = runner.invoke(cli, ["plugin", "info", "ep-plug"])

        parsed = yaml.safe_load(result.output)
        assert parsed["source"] == "entrypoint"

    def test_info_shows_source_directory(self):
        plugin = _make_manifest(name="dir-plug", version="1.0.0")
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[plugin]):
            result = runner.invoke(cli, ["plugin", "info", "dir-plug"])

        parsed = yaml.safe_load(result.output)
        assert parsed["source"] == "directory"

    def test_info_with_zero_plugins_returns_error(self):
        runner = CliRunner()
        with patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins", return_value=[]), \
             patch("crazypumpkin.framework.plugin_loader.load_plugins", return_value=[]):
            result = runner.invoke(cli, ["plugin", "info", "anything"])

        assert result.exit_code == 1
        assert "not found" in result.output
