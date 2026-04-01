"""Trigger expression parser and evaluator.

Supports expressions like::

    planned_tasks > 0 AND hours_since_last_run > 1

Operators: ``>``, ``<``, ``==``, ``>=``, ``<=``
Logical:   ``AND``, ``OR``
Sentinels: ``always`` (True), ``never`` (False), ``schedule`` (True)
"""

from __future__ import annotations

import re
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TriggerParseError(Exception):
    """Raised when a trigger expression cannot be parsed."""


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<NUMBER>   -?\d+(?:\.\d+)? )   |
    (?P<STRING>   "[^"]*" | '[^']*' )  |
    (?P<OP>       >=|<=|==|>|<     )   |
    (?P<AND>      \bAND\b          )   |
    (?P<OR>       \bOR\b           )   |
    (?P<IDENT>    [A-Za-z_]\w*     )   |
    (?P<WS>       \s+              )
    """,
    re.VERBOSE,
)

_SENTINEL_MAP = {
    "always": True,
    "never": False,
    "schedule": True,
}


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Return a list of ``(kind, value)`` tokens from *expr*."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if m is None:
            raise TriggerParseError(
                f"Unexpected character at position {pos}: {expr[pos:]!r}"
            )
        kind = m.lastgroup
        assert kind is not None
        value = m.group()
        if kind != "WS":
            tokens.append((kind, value))
        pos = m.end()
    return tokens


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class _Sentinel:
    __slots__ = ("value",)

    def __init__(self, value: bool) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f"Sentinel({self.value})"


class _Comparison:
    __slots__ = ("left", "op", "right")

    def __init__(self, left: str, op: str, right: Any) -> None:
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self) -> str:
        return f"Cmp({self.left} {self.op} {self.right!r})"


class _LogicalOp:
    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Any, right: Any) -> None:
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"Logic({self.left} {self.op} {self.right})"


# ---------------------------------------------------------------------------
# Parser — recursive-descent: expr → and_expr (OR and_expr)*
#                              and_expr → comparison (AND comparison)*
#                              comparison → IDENT OP literal | sentinel
# ---------------------------------------------------------------------------


class _Parser:
    """Simple recursive-descent parser for trigger expressions."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> tuple[str, str] | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self) -> tuple[str, str]:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str) -> tuple[str, str]:
        tok = self._peek()
        if tok is None or tok[0] != kind:
            expected = kind
            got = tok[1] if tok else "end of expression"
            raise TriggerParseError(
                f"Expected {expected}, got {got!r}"
            )
        return self._advance()

    # ----- grammar -----

    def parse(self) -> Any:
        if not self._tokens:
            raise TriggerParseError("Empty expression")
        node = self._or_expr()
        if self._pos < len(self._tokens):
            leftover = " ".join(t[1] for t in self._tokens[self._pos:])
            raise TriggerParseError(f"Unexpected trailing tokens: {leftover!r}")
        return node

    def _or_expr(self) -> Any:
        left = self._and_expr()
        while self._peek() and self._peek()[0] == "OR":  # type: ignore[index]
            self._advance()
            right = self._and_expr()
            left = _LogicalOp("OR", left, right)
        return left

    def _and_expr(self) -> Any:
        left = self._primary()
        while self._peek() and self._peek()[0] == "AND":  # type: ignore[index]
            self._advance()
            right = self._primary()
            left = _LogicalOp("AND", left, right)
        return left

    def _primary(self) -> Any:
        tok = self._peek()
        if tok is None:
            raise TriggerParseError("Unexpected end of expression")

        kind, value = tok

        # Sentinel keywords
        if kind == "IDENT" and value in _SENTINEL_MAP:
            self._advance()
            return _Sentinel(_SENTINEL_MAP[value])

        # Comparison: IDENT OP literal
        if kind == "IDENT":
            ident_tok = self._advance()
            op_tok = self._expect("OP")
            lit_tok = self._peek()
            if lit_tok is None:
                raise TriggerParseError(
                    f"Expected a value after '{ident_tok[1]} {op_tok[1]}'"
                )
            lit_kind, lit_value = self._advance()
            if lit_kind == "NUMBER":
                parsed_val: Any = float(lit_value) if "." in lit_value else int(lit_value)
            elif lit_kind == "STRING":
                parsed_val = lit_value[1:-1]  # strip quotes
            elif lit_kind == "IDENT":
                # Allow bare identifiers as string values
                parsed_val = lit_value
            else:
                raise TriggerParseError(
                    f"Expected number, string, or identifier after operator, "
                    f"got {lit_kind} ({lit_value!r})"
                )
            return _Comparison(ident_tok[1], op_tok[1], parsed_val)

        raise TriggerParseError(f"Unexpected token: {value!r}")


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

_CMP_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def _evaluate(node: Any, snapshot: dict[str, Any]) -> bool:
    """Walk the AST and return a boolean result."""
    if isinstance(node, _Sentinel):
        return node.value

    if isinstance(node, _Comparison):
        if node.left not in snapshot:
            raise KeyError(
                f"Snapshot is missing required key: {node.left!r}"
            )
        left_val = snapshot[node.left]
        return _CMP_OPS[node.op](left_val, node.right)

    if isinstance(node, _LogicalOp):
        left_result = _evaluate(node.left, snapshot)
        if node.op == "AND":
            return left_result and _evaluate(node.right, snapshot)
        # OR
        return left_result or _evaluate(node.right, snapshot)

    raise TriggerParseError(f"Unknown AST node: {node!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_trigger(expr: str) -> Any:
    """Tokenize and parse *expr* into an AST.

    Raises :class:`TriggerParseError` on malformed input.
    """
    tokens = _tokenize(expr)
    return _Parser(tokens).parse()


def evaluate_trigger(expr: str, snapshot: dict[str, Any]) -> bool:
    """Parse *expr* and evaluate it against the *snapshot* dict.

    Returns ``True`` or ``False``.

    Raises :class:`TriggerParseError` on malformed syntax and
    :class:`KeyError` if *snapshot* is missing a referenced variable.
    """
    ast = parse_trigger(expr)
    return _evaluate(ast, snapshot)


# ---------------------------------------------------------------------------
# Cron trigger support
# ---------------------------------------------------------------------------


class CronTrigger:
    """A named cron-based trigger with an associated callback."""

    def __init__(self, name: str, cron_expr: str, callback: Callable) -> None:
        self.name = name
        self.cron_expr = cron_expr
        self.callback = callback
        self._fired = False

    def should_fire(self) -> bool:
        """Check whether this trigger should fire based on its cron expression.

        Uses :func:`crazypumpkin.scheduler.cron.parse_cron_expression` to
        validate the expression and compares against the current time.
        """
        from datetime import datetime

        from crazypumpkin.scheduler.cron import parse_cron_expression

        now = datetime.now()
        cron = parse_cron_expression(self.cron_expr)
        return (
            now.minute in cron.minute.values
            and now.hour in cron.hour.values
            and now.day in cron.dom.values
            and now.month in cron.month.values
            and now.weekday() in cron.dow.values
        )

    def fire(self) -> None:
        """Invoke the callback."""
        self._fired = True
        self.callback()

    def __repr__(self) -> str:
        return f"CronTrigger(name={self.name!r}, cron={self.cron_expr!r})"


_cron_trigger_registry: dict[str, CronTrigger] = {}


def register_cron_trigger(name: str, cron_expr: str, callback: Callable) -> CronTrigger:
    """Register a named cron trigger with a callback.

    Args:
        name: Unique identifier for this trigger.
        cron_expr: A five-field cron expression string.
        callback: Callable to invoke when the trigger fires.

    Returns:
        The newly created :class:`CronTrigger`.
    """
    trigger = CronTrigger(name, cron_expr, callback)
    _cron_trigger_registry[name] = trigger
    return trigger
