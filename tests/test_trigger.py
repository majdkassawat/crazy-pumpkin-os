"""Tests for the trigger expression parser and evaluator."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.trigger import (
    TriggerParseError,
    _Comparison,
    _LogicalOp,
    _Sentinel,
    _tokenize,
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


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_parser_tokenize_simple_comparison(self):
        tokens = _tokenize("x > 5")
        assert tokens == [("IDENT", "x"), ("OP", ">"), ("NUMBER", "5")]

    def test_parser_tokenize_string_literal(self):
        tokens = _tokenize('status == "active"')
        assert tokens == [
            ("IDENT", "status"),
            ("OP", "=="),
            ("STRING", '"active"'),
        ]

    def test_parser_tokenize_single_quoted_string(self):
        tokens = _tokenize("status == 'idle'")
        assert tokens == [
            ("IDENT", "status"),
            ("OP", "=="),
            ("STRING", "'idle'"),
        ]

    def test_parser_tokenize_logical_operators(self):
        tokens = _tokenize("a > 0 AND b < 10 OR c == 1")
        kinds = [t[0] for t in tokens]
        assert kinds == [
            "IDENT", "OP", "NUMBER",
            "AND",
            "IDENT", "OP", "NUMBER",
            "OR",
            "IDENT", "OP", "NUMBER",
        ]

    def test_parser_tokenize_all_comparison_ops(self):
        for op in [">", "<", "==", ">=", "<="]:
            tokens = _tokenize(f"x {op} 1")
            assert tokens[1] == ("OP", op)

    def test_parser_tokenize_negative_number(self):
        tokens = _tokenize("x > -3")
        assert tokens == [("IDENT", "x"), ("OP", ">"), ("NUMBER", "-3")]

    def test_parser_tokenize_float(self):
        tokens = _tokenize("val >= 1.5")
        assert tokens == [("IDENT", "val"), ("OP", ">="), ("NUMBER", "1.5")]

    def test_parser_tokenize_negative_float(self):
        tokens = _tokenize("val < -2.5")
        assert tokens == [("IDENT", "val"), ("OP", "<"), ("NUMBER", "-2.5")]

    def test_parser_tokenize_sentinel(self):
        tokens = _tokenize("always")
        assert tokens == [("IDENT", "always")]

    def test_parser_tokenize_strips_whitespace(self):
        tokens = _tokenize("  x   >   5  ")
        assert tokens == [("IDENT", "x"), ("OP", ">"), ("NUMBER", "5")]

    def test_parser_tokenize_invalid_char_raises(self):
        with pytest.raises(TriggerParseError, match="Unexpected character"):
            _tokenize("x @ 5")


# ---------------------------------------------------------------------------
# Parser — AST structure
# ---------------------------------------------------------------------------


class TestParserAST:
    def test_parser_sentinel_always(self):
        ast = parse_trigger("always")
        assert isinstance(ast, _Sentinel)
        assert ast.value is True

    def test_parser_sentinel_never(self):
        ast = parse_trigger("never")
        assert isinstance(ast, _Sentinel)
        assert ast.value is False

    def test_parser_sentinel_schedule(self):
        ast = parse_trigger("schedule")
        assert isinstance(ast, _Sentinel)
        assert ast.value is True

    def test_parser_comparison_greater_than(self):
        ast = parse_trigger("count > 10")
        assert isinstance(ast, _Comparison)
        assert ast.left == "count"
        assert ast.op == ">"
        assert ast.right == 10

    def test_parser_comparison_less_equal(self):
        ast = parse_trigger("score <= 100")
        assert isinstance(ast, _Comparison)
        assert ast.left == "score"
        assert ast.op == "<="
        assert ast.right == 100

    def test_parser_comparison_equal_string(self):
        ast = parse_trigger('mode == "fast"')
        assert isinstance(ast, _Comparison)
        assert ast.left == "mode"
        assert ast.op == "=="
        assert ast.right == "fast"

    def test_parser_comparison_float_value(self):
        ast = parse_trigger("threshold >= 0.75")
        assert isinstance(ast, _Comparison)
        assert ast.right == 0.75

    def test_parser_comparison_negative_int(self):
        ast = parse_trigger("delta > -5")
        assert isinstance(ast, _Comparison)
        assert ast.right == -5

    def test_parser_comparison_bare_ident_value(self):
        ast = parse_trigger("status == active")
        assert isinstance(ast, _Comparison)
        assert ast.right == "active"

    def test_parser_and_expression(self):
        ast = parse_trigger("x > 0 AND y < 10")
        assert isinstance(ast, _LogicalOp)
        assert ast.op == "AND"
        assert isinstance(ast.left, _Comparison)
        assert isinstance(ast.right, _Comparison)
        assert ast.left.left == "x"
        assert ast.right.left == "y"

    def test_parser_or_expression(self):
        ast = parse_trigger("a == 1 OR b == 2")
        assert isinstance(ast, _LogicalOp)
        assert ast.op == "OR"

    def test_parser_chained_and(self):
        ast = parse_trigger("a > 0 AND b > 0 AND c > 0")
        assert isinstance(ast, _LogicalOp)
        assert ast.op == "AND"
        # Left-associative: ((a>0 AND b>0) AND c>0)
        assert isinstance(ast.left, _LogicalOp)
        assert isinstance(ast.right, _Comparison)
        assert ast.right.left == "c"

    def test_parser_and_or_precedence(self):
        # OR has lower precedence: a>0 OR (b>0 AND c>0)
        ast = parse_trigger("a > 0 OR b > 0 AND c > 0")
        assert isinstance(ast, _LogicalOp)
        assert ast.op == "OR"
        assert isinstance(ast.left, _Comparison)
        assert isinstance(ast.right, _LogicalOp)
        assert ast.right.op == "AND"

    def test_parser_all_operators_produce_comparison(self):
        for op in [">", "<", "==", ">=", "<="]:
            ast = parse_trigger(f"x {op} 1")
            assert isinstance(ast, _Comparison)
            assert ast.op == op


# ---------------------------------------------------------------------------
# Parser — round-trip repr
# ---------------------------------------------------------------------------


class TestParserRoundTrip:
    def test_parser_repr_sentinel(self):
        ast = parse_trigger("always")
        assert repr(ast) == "Sentinel(True)"

    def test_parser_repr_comparison(self):
        ast = parse_trigger("x > 5")
        assert repr(ast) == "Cmp(x > 5)"

    def test_parser_repr_comparison_string(self):
        ast = parse_trigger('name == "bob"')
        assert repr(ast) == "Cmp(name == 'bob')"

    def test_parser_repr_logical(self):
        ast = parse_trigger("x > 0 AND y < 10")
        assert repr(ast) == "Logic(Cmp(x > 0) AND Cmp(y < 10))"

    def test_parser_repr_or(self):
        ast = parse_trigger("a == 1 OR b == 2")
        assert repr(ast) == "Logic(Cmp(a == 1) OR Cmp(b == 2))"
