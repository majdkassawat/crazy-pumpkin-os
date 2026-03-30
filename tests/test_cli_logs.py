"""Tests for crazypumpkin logs CLI command."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli.logs import cmd_logs, _tail_file, _matches_filters, _find_log_dir


# ── _matches_filters ────────────────────────────────────────────────────


def test_matches_no_filters():
    assert _matches_filters("[INFO] hello", level=None, agent=None) is True


def test_matches_level_filter_pass():
    assert _matches_filters("[ERROR] boom", level="ERROR", agent=None) is True


def test_matches_level_filter_fail():
    assert _matches_filters("[INFO] fine", level="ERROR", agent=None) is False


def test_matches_agent_filter_pass():
    assert _matches_filters("[INFO] Developer: doing stuff", level=None, agent="Developer") is True


def test_matches_agent_filter_fail():
    assert _matches_filters("[INFO] Reviewer: checking", level=None, agent="Developer") is False


def test_matches_both_filters():
    assert _matches_filters("[ERROR] Developer: crash", level="ERROR", agent="Developer") is True
    assert _matches_filters("[INFO] Developer: ok", level="ERROR", agent="Developer") is False


# ── _tail_file ──────────────────────────────────────────────────────────


def test_tail_file_returns_last_lines(tmp_path):
    log = tmp_path / "test.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)) + "\n", encoding="utf-8")
    lines = _tail_file(log, num_lines=5)
    assert len(lines) == 5
    assert "line 99" in lines[-1]


def test_tail_file_small_file(tmp_path):
    log = tmp_path / "small.log"
    log.write_text("one\ntwo\n", encoding="utf-8")
    lines = _tail_file(log, num_lines=50)
    assert len(lines) == 2


def test_tail_file_missing():
    lines = _tail_file(Path("/nonexistent/file.log"))
    assert lines == []


# ── cmd_logs — no log directory ─────────────────────────────────────────


def test_cmd_logs_no_log_dir(tmp_path, capsys):
    """When log directory doesn't exist, prints message and returns."""
    args = argparse.Namespace(follow=False, level=None, agent=None, lines=50)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=tmp_path / "logs"):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "No logs directory" in output


# ── cmd_logs — empty log directory ──────────────────────────────────────


def test_cmd_logs_no_log_files(tmp_path, capsys):
    """When log directory exists but is empty, prints message."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    args = argparse.Namespace(follow=False, level=None, agent=None, lines=50)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "No log files" in output


# ── cmd_logs — tailing ──────────────────────────────────────────────────


def test_cmd_logs_tails_log_files(tmp_path, capsys):
    """Logs command prints recent lines from log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text(
        "[INFO] started\n[ERROR] something broke\n[INFO] recovered\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(follow=False, level=None, agent=None, lines=50)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "started" in output
    assert "something broke" in output


# ── cmd_logs — level filtering ──────────────────────────────────────────


def test_cmd_logs_level_filter(tmp_path, capsys):
    """--level ERROR only shows error lines."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text(
        "[INFO] all good\n[ERROR] bad thing\n[INFO] fine\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(follow=False, level="ERROR", agent=None, lines=50)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "bad thing" in output
    assert "all good" not in output


# ── cmd_logs — agent filtering ──────────────────────────────────────────


def test_cmd_logs_agent_filter(tmp_path, capsys):
    """--agent Developer only shows lines mentioning Developer."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text(
        "[INFO] Developer: coding\n[INFO] Reviewer: reviewing\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(follow=False, level=None, agent="Developer", lines=50)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "Developer: coding" in output
    assert "Reviewer" not in output


# ── cmd_logs — lines limit ──────────────────────────────────────────────


def test_cmd_logs_lines_limit(tmp_path, capsys):
    """--lines N only shows the last N lines."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    content = "\n".join(f"[INFO] line {i}" for i in range(20)) + "\n"
    (log_dir / "pipeline.log").write_text(content, encoding="utf-8")
    args = argparse.Namespace(follow=False, level=None, agent=None, lines=3)
    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir):
        cmd_logs(args)
    output = capsys.readouterr().out
    assert "line 17" in output
    assert "line 19" in output
    assert "line 0" not in output


# ── cmd_logs — follow mode ──────────────────────────────────────────────


def test_cmd_logs_follow_interrupted(tmp_path, capsys):
    """Follow mode exits cleanly on KeyboardInterrupt."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pipeline.log").write_text("[INFO] start\n", encoding="utf-8")

    args = argparse.Namespace(follow=True, level=None, agent=None, lines=50)

    def _sleep_raises(seconds):
        raise KeyboardInterrupt

    with patch("crazypumpkin.cli.logs._find_log_dir", return_value=log_dir), \
         patch("crazypumpkin.cli.logs.time.sleep", side_effect=_sleep_raises):
        cmd_logs(args)

    output = capsys.readouterr().out
    assert "following logs" in output.lower() or "Stopped" in output
