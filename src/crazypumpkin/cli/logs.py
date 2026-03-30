"""Tail pipeline log files with filtering options.

Usage:
    crazypumpkin logs                     — show recent log lines
    crazypumpkin logs --follow            — tail logs continuously
    crazypumpkin logs --level ERROR       — filter by severity
    crazypumpkin logs --agent Developer   — filter by agent name
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


DEFAULT_LOG_DIR = "logs"
VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _find_log_dir() -> Path:
    """Return the logs directory under the project root (cwd)."""
    return Path.cwd() / DEFAULT_LOG_DIR


def _matches_filters(line: str, level: str | None, agent: str | None) -> bool:
    """Return True if *line* passes the --level and --agent filters."""
    if level and level.upper() not in line.upper():
        return False
    if agent and agent.lower() not in line.lower():
        return False
    return True


def _tail_file(path: Path, num_lines: int = 50) -> list[str]:
    """Return the last *num_lines* lines from *path*."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return lines[-num_lines:]
    except OSError:
        return []


def cmd_logs(args) -> None:
    """Display and optionally follow pipeline log files."""
    log_dir = _find_log_dir()
    follow: bool = getattr(args, "follow", False)
    level: str | None = getattr(args, "level", None)
    agent: str | None = getattr(args, "agent", None)
    lines_count: int = getattr(args, "lines", 50)

    if not log_dir.is_dir():
        print(f"No logs directory found at {log_dir}")
        return

    log_files = sorted(log_dir.glob("*.log"))
    if not log_files:
        print(f"No log files found in {log_dir}")
        return

    # Show recent lines from each log file
    for log_file in log_files:
        tail = _tail_file(log_file, num_lines=lines_count)
        for line in tail:
            if _matches_filters(line, level, agent):
                sys.stdout.write(line)

    if not follow:
        return

    # Follow mode: watch for new lines
    # Track file positions
    positions: dict[Path, int] = {}
    for log_file in log_files:
        try:
            positions[log_file] = log_file.stat().st_size
        except OSError:
            positions[log_file] = 0

    print("--- following logs (Ctrl+C to stop) ---")
    try:
        while True:
            # Re-scan for new log files
            current_files = sorted(log_dir.glob("*.log"))
            for log_file in current_files:
                if log_file not in positions:
                    positions[log_file] = 0

                try:
                    size = log_file.stat().st_size
                except OSError:
                    continue

                if size > positions[log_file]:
                    try:
                        with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(positions[log_file])
                            new_data = fh.read()
                        positions[log_file] = size
                        for line in new_data.splitlines(keepends=True):
                            if _matches_filters(line, level, agent):
                                sys.stdout.write(line)
                    except OSError:
                        continue
                elif size < positions[log_file]:
                    # File was truncated/rotated — reset
                    positions[log_file] = 0

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped following logs.")
