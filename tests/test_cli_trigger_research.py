"""Research tests — verify CLI trigger commands, public trigger API, and schedule commands.

Confirmed findings against the LOCAL worktree source:

(a) Click CLI `cli` group (src/crazypumpkin/cli/__init__.py):
    - `cli` is a click.Group with subcommand: `run`
    - `triggers` group with `list` / `test` subcommands exists in the
      UPSTREAM repo but is NOT yet present in this worktree.

(b) Public API in crazypumpkin.framework.trigger (this worktree):
    - parse_trigger(expr) -> AST
    - evaluate_trigger(expr, snapshot) -> bool
    - TriggerParseError (exception class)
    NOTE: CronTrigger, register_cron_trigger, _cron_trigger_registry exist
    in the UPSTREAM repo but are NOT yet in this worktree's trigger.py.

(c) Argparse `main()` schedule subcommands (this worktree):
    - schedule list   -> cmd_schedule_list
    - schedule add    -> cmd_schedule_add
    - schedule remove -> cmd_schedule_remove
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from click.testing import CliRunner

from crazypumpkin.cli import cli
from crazypumpkin.framework import trigger as trigger_mod


# ── (a) Click CLI commands present in this worktree ────────────────


class TestClickCLICommands:
    """Verify the Click `cli` group and its registered subcommands."""

    def test_cli_is_click_group(self):
        import click
        assert isinstance(cli, click.Group)

    def test_run_command_registered(self):
        """The Click `cli` object has a `run` subcommand."""
        assert "run" in cli.commands

    def test_triggers_group_not_yet_present(self):
        """The `triggers` group is not yet added to this worktree's CLI.

        It exists in the upstream repo at lines 849-890 of
        crazy-pumpkin-os/src/crazypumpkin/cli/__init__.py with subcommands:
          - triggers list   (list_triggers)
          - triggers test   (test_trigger, takes NAME argument)
        """
        # This documents that we need to add it
        assert "triggers" not in cli.commands


# ── (b) Public API in crazypumpkin.framework.trigger ───────────────


class TestTriggerPublicAPI:
    """Confirm each public name exported from the trigger module in this worktree."""

    def test_parse_trigger_exists_and_callable(self):
        assert callable(trigger_mod.parse_trigger)

    def test_evaluate_trigger_exists_and_callable(self):
        assert callable(trigger_mod.evaluate_trigger)

    def test_trigger_parse_error_is_exception_subclass(self):
        assert issubclass(trigger_mod.TriggerParseError, Exception)

    def test_parse_trigger_returns_ast(self):
        ast = trigger_mod.parse_trigger("x > 5")
        assert ast is not None

    def test_evaluate_trigger_returns_bool(self):
        result = trigger_mod.evaluate_trigger("x > 0", {"x": 1})
        assert result is True

    def test_cron_trigger_present(self):
        """CronTrigger class is available in this worktree."""
        assert hasattr(trigger_mod, "CronTrigger")

    def test_register_cron_trigger_present(self):
        """register_cron_trigger is available in this worktree."""
        assert callable(trigger_mod.register_cron_trigger)

    def test_cron_trigger_registry_present(self):
        """_cron_trigger_registry is available in this worktree."""
        assert hasattr(trigger_mod, "_cron_trigger_registry")


# ── (c) Argparse schedule subcommands ──────────────────────────────


class TestArgparseScheduleSubcommands:
    """Verify schedule-related handler functions exist in the CLI module."""

    def test_cmd_schedule_list_exists(self):
        from crazypumpkin.cli import cmd_schedule_list
        assert callable(cmd_schedule_list)

    def test_cmd_schedule_add_exists(self):
        from crazypumpkin.cli import cmd_schedule_add
        assert callable(cmd_schedule_add)

    def test_cmd_schedule_remove_exists(self):
        from crazypumpkin.cli import cmd_schedule_remove
        assert callable(cmd_schedule_remove)

    def test_main_function_exists(self):
        from crazypumpkin.cli import main
        assert callable(main)
