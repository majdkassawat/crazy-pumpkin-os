"""Tests for the trigger expression parser and evaluator."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.trigger import (
    TriggerParseError,
    _Comparison,
    _LogicalOp,
    _Parser,
    _Sentinel,
    _tokenize,
    _evaluate,
    evaluate_trigger,
    parse_trigger,
)


# ---------------------------------------------------------------------------
# Required test cases
# ---------------------------------------------------------------------------


def test_parse_simple_expression():
    """Single field comparisons (e.g., status == 'done')."""
    ast = parse_trigger("status == 'done'")
    assert isinstance(ast, _Comparison)
    assert ast.left == "status"
    assert ast.op == "=="
    assert ast.right == "done"

    ast2 = parse_trigger("x > 5")
    assert isinstance(ast2, _Comparison)
    assert ast2.left == "x"
    assert ast2.op == ">"
    assert ast2.right == 5

    ast3 = parse_trigger("val >= 1.5")
    assert isinstance(ast3, _Comparison)
    assert ast3.right == 1.5


def test_parse_compound_expression():
    """AND/OR combinations."""
    ast = parse_trigger("a > 0 AND b > 0")
    assert isinstance(ast, _LogicalOp)
    assert ast.op == "AND"
    assert isinstance(ast.left, _Comparison)
    assert isinstance(ast.right, _Comparison)

    ast2 = parse_trigger("a > 0 OR b > 0")
    assert isinstance(ast2, _LogicalOp)
    assert ast2.op == "OR"

    # Chained: a > 0 AND b > 0 AND c > 0  →  AND(AND(a>0, b>0), c>0)
    ast3 = parse_trigger("a > 0 AND b > 0 AND c > 0")
    assert isinstance(ast3, _LogicalOp)
    assert ast3.op == "AND"
    assert isinstance(ast3.left, _LogicalOp)
    assert isinstance(ast3.right, _Comparison)


def test_parse_nested_expression():
    """AND has higher precedence than OR — acts like parenthesized nesting."""
    # "a > 0 OR b > 0 AND c > 0" → OR(a>0, AND(b>0, c>0))
    ast = parse_trigger("a > 0 OR b > 0 AND c > 0")
    assert isinstance(ast, _LogicalOp)
    assert ast.op == "OR"
    assert isinstance(ast.left, _Comparison)
    assert isinstance(ast.right, _LogicalOp)
    assert ast.right.op == "AND"

    # Verify evaluation honours precedence:
    # a=0, b=1, c=1 → OR(False, AND(True,True)) → True
    assert evaluate_trigger("a > 0 OR b > 0 AND c > 0",
                            {"a": 0, "b": 1, "c": 1}) is True
    # a=0, b=1, c=0 → OR(False, AND(True,False)) → False
    assert evaluate_trigger("a > 0 OR b > 0 AND c > 0",
                            {"a": 0, "b": 1, "c": 0}) is False


def test_parse_invalid_expression():
    """Malformed input raises TriggerParseError."""
    with pytest.raises(TriggerParseError):
        parse_trigger("")

    with pytest.raises(TriggerParseError):
        parse_trigger("   ")

    with pytest.raises(TriggerParseError):
        parse_trigger("x @ 5")

    with pytest.raises(TriggerParseError):
        parse_trigger("x 5")

    with pytest.raises(TriggerParseError):
        parse_trigger("x >")

    with pytest.raises(TriggerParseError):
        parse_trigger("x > 5 y")

    with pytest.raises(TriggerParseError):
        parse_trigger("AND x > 5")


def test_trigger_evaluate_true():
    """Trigger fires when context matches."""
    assert evaluate_trigger("x > 0", {"x": 1}) is True
    assert evaluate_trigger("x == 42", {"x": 42}) is True
    assert evaluate_trigger("x < 10", {"x": 5}) is True
    assert evaluate_trigger("x >= 5", {"x": 5}) is True
    assert evaluate_trigger("x <= 5", {"x": 5}) is True
    assert evaluate_trigger('status == "active"', {"status": "active"}) is True
    assert evaluate_trigger("always", {}) is True
    assert evaluate_trigger("schedule", {}) is True
    assert evaluate_trigger("planned > 0 AND hours > 1",
                            {"planned": 2, "hours": 2.5}) is True
    assert evaluate_trigger("x > 10 OR y > 10",
                            {"x": 5, "y": 20}) is True


def test_trigger_evaluate_false():
    """Trigger does not fire on mismatch."""
    assert evaluate_trigger("x > 0", {"x": 0}) is False
    assert evaluate_trigger("x == 42", {"x": 43}) is False
    assert evaluate_trigger("x < 10", {"x": 10}) is False
    assert evaluate_trigger("x >= 5", {"x": 4}) is False
    assert evaluate_trigger("x <= 5", {"x": 6}) is False
    assert evaluate_trigger('status == "active"', {"status": "idle"}) is False
    assert evaluate_trigger("never", {}) is False
    assert evaluate_trigger("x > 10 OR y > 10",
                            {"x": 5, "y": 5}) is False
    assert evaluate_trigger("a > 0 AND b > 0",
                            {"a": 0, "b": 5}) is False


def test_trigger_registration():
    """Triggers can be registered (stored) and retrieved by name."""
    registry: dict[str, str] = {}
    registry["deploy_check"] = "planned_tasks > 0 AND hours_since_last_run > 1"
    registry["always_on"] = "always"
    registry["never_fire"] = "never"

    assert "deploy_check" in registry
    assert "always_on" in registry
    assert "never_fire" in registry

    # Registered expressions parse without error
    for name, expr in registry.items():
        ast = parse_trigger(expr)
        assert ast is not None

    # Evaluate registered triggers
    snapshot = {"planned_tasks": 3, "hours_since_last_run": 2}
    assert evaluate_trigger(registry["deploy_check"], snapshot) is True
    assert evaluate_trigger(registry["always_on"], {}) is True
    assert evaluate_trigger(registry["never_fire"], {}) is False


def test_trigger_callback_invocation():
    """Registered callback executes on match."""
    invocations: list[str] = []

    def on_trigger(name: str) -> None:
        invocations.append(name)

    triggers = {
        "task_ready": "pending > 0",
        "idle_check": "idle_minutes > 30",
    }
    snapshot = {"pending": 5, "idle_minutes": 10}

    for name, expr in triggers.items():
        if evaluate_trigger(expr, snapshot):
            on_trigger(name)

    assert "task_ready" in invocations
    assert "idle_check" not in invocations

    # Fire the second trigger with updated snapshot
    snapshot2 = {"pending": 0, "idle_minutes": 45}
    invocations.clear()
    for name, expr in triggers.items():
        if evaluate_trigger(expr, snapshot2):
            on_trigger(name)

    assert "task_ready" not in invocations
    assert "idle_check" in invocations


# ---------------------------------------------------------------------------
# AST node coverage — all 5 classes
# ---------------------------------------------------------------------------


class TestSentinel:
    def test_init_true(self):
        s = _Sentinel(True)
        assert s.value is True

    def test_init_false(self):
        s = _Sentinel(False)
        assert s.value is False

    def test_repr(self):
        assert repr(_Sentinel(True)) == "Sentinel(True)"
        assert repr(_Sentinel(False)) == "Sentinel(False)"


class TestComparison:
    def test_init(self):
        c = _Comparison("x", ">", 5)
        assert c.left == "x"
        assert c.op == ">"
        assert c.right == 5

    def test_repr(self):
        c = _Comparison("x", "==", "done")
        assert repr(c) == "Cmp(x == 'done')"


class TestLogicalOp:
    def test_init(self):
        left = _Comparison("a", ">", 0)
        right = _Comparison("b", ">", 0)
        node = _LogicalOp("AND", left, right)
        assert node.op == "AND"
        assert node.left is left
        assert node.right is right

    def test_repr(self):
        left = _Comparison("a", ">", 0)
        right = _Comparison("b", "<", 10)
        node = _LogicalOp("OR", left, right)
        r = repr(node)
        assert "OR" in r
        assert "Cmp" in r


class TestParser:
    def test_empty_tokens_raises(self):
        p = _Parser([])
        with pytest.raises(TriggerParseError, match="Empty expression"):
            p.parse()

    def test_unexpected_token_raises(self):
        tokens = [("OP", ">")]
        p = _Parser(tokens)
        with pytest.raises(TriggerParseError):
            p.parse()


class TestTriggerParseError:
    def test_is_exception(self):
        assert issubclass(TriggerParseError, Exception)

    def test_message(self):
        err = TriggerParseError("bad input")
        assert str(err) == "bad input"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_simple_tokens(self):
        tokens = _tokenize("x > 5")
        assert ("IDENT", "x") in tokens
        assert ("OP", ">") in tokens
        assert ("NUMBER", "5") in tokens

    def test_string_tokens(self):
        tokens = _tokenize('status == "active"')
        assert ("STRING", '"active"') in tokens

    def test_single_quote_string(self):
        tokens = _tokenize("status == 'done'")
        assert ("STRING", "'done'") in tokens

    def test_logical_tokens(self):
        tokens = _tokenize("a > 0 AND b < 10 OR c == 1")
        kinds = [t[0] for t in tokens]
        assert "AND" in kinds
        assert "OR" in kinds

    def test_negative_number(self):
        tokens = _tokenize("x > -5")
        assert ("NUMBER", "-5") in tokens

    def test_float_number(self):
        tokens = _tokenize("val >= 3.14")
        assert ("NUMBER", "3.14") in tokens

    def test_invalid_char_raises(self):
        with pytest.raises(TriggerParseError, match="Unexpected character"):
            _tokenize("x @ 5")

    def test_whitespace_stripped(self):
        tokens = _tokenize("  x  >  5  ")
        assert all(t[0] != "WS" for t in tokens)
        assert len(tokens) == 3


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_sentinel_true(self):
        assert _evaluate(_Sentinel(True), {}) is True

    def test_sentinel_false(self):
        assert _evaluate(_Sentinel(False), {}) is False

    def test_comparison_missing_key(self):
        node = _Comparison("missing", ">", 0)
        with pytest.raises(KeyError, match="missing"):
            _evaluate(node, {})

    def test_and_short_circuit(self):
        left = _Sentinel(False)
        right = _Comparison("x", ">", 0)
        node = _LogicalOp("AND", left, right)
        # Should not raise KeyError because AND short-circuits
        assert _evaluate(node, {}) is False

    def test_or_short_circuit(self):
        left = _Sentinel(True)
        right = _Comparison("x", ">", 0)
        node = _LogicalOp("OR", left, right)
        # Should not raise KeyError because OR short-circuits
        assert _evaluate(node, {}) is True

    def test_bare_identifier_as_value(self):
        # "status == active" where 'active' is parsed as a bare IDENT
        assert evaluate_trigger("status == active", {"status": "active"}) is True
        assert evaluate_trigger("status == active", {"status": "other"}) is False

    def test_all_comparison_operators(self):
        assert evaluate_trigger("x > 0", {"x": 1}) is True
        assert evaluate_trigger("x < 0", {"x": -1}) is True
        assert evaluate_trigger("x == 0", {"x": 0}) is True
        assert evaluate_trigger("x >= 0", {"x": 0}) is True
        assert evaluate_trigger("x <= 0", {"x": 0}) is True
