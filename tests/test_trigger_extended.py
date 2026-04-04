"""Tests for NOT operator and parenthesized grouping in trigger parser."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.trigger import (
    TriggerParseError,
    _Not,
    _Sentinel,
    evaluate_trigger,
    parse_trigger,
)


class TestNotOperator:
    def test_parse_not_always(self):
        ast = parse_trigger("NOT always")
        assert isinstance(ast, _Not)
        assert isinstance(ast.operand, _Sentinel)
        assert ast.operand.value is True

    def test_not_status_idle(self):
        result = evaluate_trigger('NOT status == "idle"', {"status": "running"})
        assert result is True

    def test_not_status_idle_false(self):
        result = evaluate_trigger('NOT status == "idle"', {"status": "idle"})
        assert result is False

    def test_not_never(self):
        assert evaluate_trigger("NOT never", {}) is True

    def test_not_repr(self):
        ast = parse_trigger("NOT always")
        assert "Not(" in repr(ast)


class TestParentheses:
    def test_or_and_grouping(self):
        result = evaluate_trigger(
            "(a > 1 OR b > 1) AND c == 0",
            {"a": 0, "b": 2, "c": 0},
        )
        assert result is True

    def test_or_and_grouping_false(self):
        result = evaluate_trigger(
            "(a > 1 OR b > 1) AND c == 0",
            {"a": 0, "b": 0, "c": 0},
        )
        assert result is False

    def test_nested_parens(self):
        result = evaluate_trigger("((a > 1))", {"a": 5})
        assert result is True

    def test_nested_parens_false(self):
        result = evaluate_trigger("((a > 1))", {"a": 0})
        assert result is False

    def test_unmatched_paren_raises(self):
        with pytest.raises(TriggerParseError):
            parse_trigger("(a > 1")


class TestNotWithParens:
    def test_not_parenthesized_and(self):
        result = evaluate_trigger(
            "NOT (a > 5 AND b > 5)",
            {"a": 3, "b": 10},
        )
        assert result is True

    def test_not_parenthesized_and_false(self):
        result = evaluate_trigger(
            "NOT (a > 5 AND b > 5)",
            {"a": 10, "b": 10},
        )
        assert result is False
