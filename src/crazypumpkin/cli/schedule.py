"""Schedule subcommands — list, add, and remove cron schedules for agents."""

from __future__ import annotations

import sys

from crazypumpkin.cli.errors import friendly_errors
from crazypumpkin.framework.config import load_config, save_config
from crazypumpkin.scheduler.cron import parse_cron_expression


@friendly_errors
def cmd_schedule_list(args):
    """List all agents that have a cron schedule configured."""
    config = load_config()
    scheduled = [a for a in config.agents if a.cron]

    if not scheduled:
        print("No scheduled agents found.")
        return

    for agent in scheduled:
        print(f"{agent.name}  {agent.cron}")


@friendly_errors
def cmd_schedule_add(args):
    """Add or update a cron schedule for an agent."""
    config = load_config()

    agent_name = args.agent_name
    cron_expr = args.cron_expr

    # Validate cron expression
    try:
        parse_cron_expression(cron_expr)
    except ValueError as exc:
        print(f"Invalid cron expression: {exc}", file=sys.stderr)
        sys.exit(1)

    # Find the agent
    target = None
    for agent in config.agents:
        if agent.name == agent_name:
            target = agent
            break

    if target is None:
        print(f"Agent '{agent_name}' not found in configuration.", file=sys.stderr)
        sys.exit(1)

    target.cron = cron_expr
    save_config(config)
    print(f"Scheduled {agent_name} with cron '{cron_expr}'")


@friendly_errors
def cmd_schedule_remove(args):
    """Remove the cron schedule from an agent."""
    config = load_config()

    agent_name = args.agent_name

    # Find the agent
    target = None
    for agent in config.agents:
        if agent.name == agent_name:
            target = agent
            break

    if target is None:
        print(f"Agent '{agent_name}' not found in configuration.", file=sys.stderr)
        sys.exit(1)

    if not target.cron:
        print(f"Agent '{agent_name}' has no schedule to remove.", file=sys.stderr)
        sys.exit(1)

    target.cron = ""
    save_config(config)
    print(f"Removed schedule for {agent_name}")
