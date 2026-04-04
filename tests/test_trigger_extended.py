"""Tests for extended trigger expressions: NOT, parentheses, IN, and combinations."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.trigger import (
    parse_trigger,
    evaluate_trigger,
    TriggerParseError,
)


def test_not_sentinel():
    assert evaluate_trigger("NOT always", {}) is False
    assert evaluate_trigger("NOT never", {}) is True


def test_not_comparison():
    assert evaluate_trigger("NOT x > 5", {"x": 3}) is True
    assert evaluate_trigger("NOT x > 5", {"x": 10}) is False


def test_parenthesized_or_and():
    expr = "(a > 1 OR b > 1) AND c == 0"
    assert evaluate_trigger(expr, {"a": 0, "b": 2, "c": 0}) is True
    assert evaluate_trigger(expr, {"a": 2, "b": 0, "c": 0}) is True
    assert evaluate_trigger(expr, {"a": 0, "b": 0, "c": 0}) is False
    assert evaluate_trigger(expr, {"a": 2, "b": 2, "c": 1}) is False


def test_nested_parens():
    assert evaluate_trigger("((x > 1))", {"x": 5}) is True
    assert evaluate_trigger("((x > 1))", {"x": 0}) is False


def test_not_parenthesized():
    expr = "NOT (a > 5 AND b > 5)"
    assert evaluate_trigger(expr, {"a": 3, "b": 10}) is True
    assert evaluate_trigger(expr, {"a": 10, "b": 10}) is False


def test_unmatched_paren_raises():
    with pytest.raises(TriggerParseError, match="Unmatched"):
        parse_trigger("(a > 1")


def test_in_numbers():
    assert evaluate_trigger('priority IN (1, 2, 3)', {"priority": 2}) is True
    assert evaluate_trigger('priority IN (1, 2, 3)', {"priority": 5}) is False


def test_in_strings():
    assert evaluate_trigger('status IN ("active", "pending")', {"status": "active"}) is True
    assert evaluate_trigger('status IN ("active", "pending")', {"status": "stopped"}) is False


def test_not_in_combo():
    assert evaluate_trigger('NOT status IN ("idle")', {"status": "running"}) is True
    assert evaluate_trigger('NOT status IN ("idle")', {"status": "idle"}) is False


def test_in_missing_parens_raises():
    with pytest.raises(TriggerParseError):
        parse_trigger("priority IN 1")


def test_in_missing_key_raises():
    with pytest.raises(KeyError, match="missing_var"):
        evaluate_trigger('missing_var IN (1, 2)', {})


def test_complex_expression():
    expr = 'NOT (priority IN (4, 5) OR status == "disabled") AND hours_since_last_run > 2'
    # priority not in bad set, status ok, hours met → True
    assert evaluate_trigger(expr, {"priority": 1, "status": "active", "hours_since_last_run": 5}) is True
    # priority in bad set → NOT(...) is False → whole thing False
    assert evaluate_trigger(expr, {"priority": 4, "status": "active", "hours_since_last_run": 5}) is False
    # status disabled → NOT(...) is False → whole thing False
    assert evaluate_trigger(expr, {"priority": 1, "status": "disabled", "hours_since_last_run": 5}) is False
    # hours not met → False
    assert evaluate_trigger(expr, {"priority": 1, "status": "active", "hours_since_last_run": 1}) is False
