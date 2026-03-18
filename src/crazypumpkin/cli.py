"""CLI entry point for Crazy Pumpkin OS.

Commands:
    crazypumpkin init       — Set up a new AI company
    crazypumpkin run        — Start the pipeline (continuous)
    crazypumpkin dashboard  — Start the web dashboard
    crazypumpkin goal       — Create a new goal
    crazypumpkin status     — Show current company status
"""

from __future__ import annotations

import argparse
import sys


def cmd_init(args):
    """Interactive setup wizard for a new AI company."""
    # TODO: implement init wizard
    print("crazypumpkin init — coming soon")


def cmd_run(args):
    """Start the pipeline."""
    # TODO: implement pipeline runner
    print("crazypumpkin run — coming soon")


def cmd_dashboard(args):
    """Start the web dashboard."""
    # TODO: implement dashboard launcher
    print("crazypumpkin dashboard — coming soon")


def cmd_goal(args):
    """Create a new goal."""
    # TODO: implement goal creation
    print("crazypumpkin goal — coming soon")


def cmd_status(args):
    """Show current company status."""
    # TODO: implement status
    print("crazypumpkin status — coming soon")


def main():
    parser = argparse.ArgumentParser(
        prog="crazypumpkin",
        description="Crazy Pumpkin OS — Autonomous AI Company Operating System",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Set up a new AI company")
    sub.add_parser("run", help="Start the pipeline")
    sub.add_parser("dashboard", help="Start the web dashboard")

    goal_parser = sub.add_parser("goal", help="Create a new goal")
    goal_parser.add_argument("name", help="Goal name")
    goal_parser.add_argument("description", nargs="?", default="", help="Goal description")

    sub.add_parser("status", help="Show current company status")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "goal": cmd_goal,
        "status": cmd_status,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
