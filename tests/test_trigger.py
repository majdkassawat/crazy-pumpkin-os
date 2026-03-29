"""Tests for the trigger expression parser and evaluator."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.trigger import (
    TriggerParseError,
    evaluate_trigger,
    parse_trigger,
)


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------


class TestSentinels:
    def test_always_returns_true(self):
        assert evaluate_trigger("always", {}) is True

    def test_never_returns_false(self):
        assert evaluate_trigger("never", {}) is False

    def test_schedule_returns_true(self):
        assert evaluate_trigger("schedule", {}) is True


# ---------------------------------------------------------------------------
# Comparison operators
# ---------------------------------------------------------------------------


class TestComparisonOperators:
    def test_greater_than_true(self):
        assert evaluate_trigger("x > 0", {"x": 1}) is True

    def test_greater_than_false(self):
        assert evaluate_trigger("x > 0", {"x": 0}) is False

    def test_less_than_true(self):
        assert evaluate_trigger("x < 10", {"x": 5}) is True

    def test_less_than_false(self):
        assert evaluate_trigger("x < 10", {"x": 10}) is False

    def test_equal_true(self):
        assert evaluate_trigger("x == 42", {"x": 42}) is True

    def test_equal_false(self):
        assert evaluate_trigger("x == 42", {"x": 43}) is False

    def test_greater_equal_true(self):
        assert evaluate_trigger("x >= 5", {"x": 5}) is True

    def test_greater_equal_false(self):
        assert evaluate_trigger("x >= 5", {"x": 4}) is False

    def test_less_equal_true(self):
        assert evaluate_trigger("x <= 5", {"x": 5}) is True

    def test_less_equal_false(self):
        assert evaluate_trigger("x <= 5", {"x": 6}) is False

    def test_float_comparison(self):
        assert evaluate_trigger("val > 1.5", {"val": 2.0}) is True

    def test_string_comparison(self):
        assert evaluate_trigger('status == "active"', {"status": "active"}) is True

    def test_string_comparison_false(self):
        assert evaluate_trigger('status == "active"', {"status": "idle"}) is False


# ---------------------------------------------------------------------------
# Logical operators
# ---------------------------------------------------------------------------


class TestLogicalOperators:
    def test_and_both_true(self):
        assert evaluate_trigger(
            "planned_tasks > 0 AND hours_since_last_run > 1",
            {"planned_tasks": 2, "hours_since_last_run": 2.5},
        ) is True

    def test_and_first_false(self):
        assert evaluate_trigger(
            "planned_tasks > 0 AND hours_since_last_run > 1",
            {"planned_tasks": 0, "hours_since_last_run": 5},
        ) is False

    def test_and_second_false(self):
        assert evaluate_trigger(
            "planned_tasks > 0 AND hours_since_last_run > 1",
            {"planned_tasks": 2, "hours_since_last_run": 0.5},
        ) is False

    def test_or_one_true(self):
        assert evaluate_trigger(
            "x > 10 OR y > 10",
            {"x": 5, "y": 20},
        ) is True

    def test_or_both_false(self):
        assert evaluate_trigger(
            "x > 10 OR y > 10",
            {"x": 5, "y": 5},
        ) is False

    def test_chained_and(self):
        assert evaluate_trigger(
            "a > 0 AND b > 0 AND c > 0",
            {"a": 1, "b": 2, "c": 3},
        ) is True

    def test_mixed_and_or(self):
        # AND has higher precedence than OR
        # "a > 0 OR b > 0 AND c > 0" → "a > 0 OR (b > 0 AND c > 0)"
        assert evaluate_trigger(
            "a > 0 OR b > 0 AND c > 0",
            {"a": 0, "b": 1, "c": 1},
        ) is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_empty_expression(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("")

    def test_invalid_character(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("x @ 5")

    def test_missing_operator(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("x 5")

    def test_missing_value(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("x >")

    def test_trailing_tokens(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("x > 5 y")

    def test_missing_snapshot_key_raises_key_error(self):
        with pytest.raises(KeyError, match="missing_var"):
            evaluate_trigger("missing_var > 0", {})

    def test_parse_trigger_returns_ast(self):
        ast = parse_trigger("always")
        assert ast is not None

    def test_whitespace_only(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("   ")
