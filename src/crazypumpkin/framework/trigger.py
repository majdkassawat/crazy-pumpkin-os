"""Trigger expression parser and evaluator.

Supports expressions like::

    planned_tasks > 0 AND hours_since_last_run > 1

Operators: ``>``, ``<``, ``==``, ``>=``, ``<=``
Logical:   ``AND``, ``OR``
Sentinels: ``always`` (True), ``never`` (False), ``schedule`` (True)
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import re
from typing import Any

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
    (?P<IDENT>    [A-Za-z_]\w*(?:\.\w+)* )   |
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


def _resolve_key(snapshot: dict[str, Any], key: str) -> Any:
    """Resolve a potentially dotted key path in *snapshot*.

    Tries a direct lookup first, then walks nested dicts for dotted paths
    like ``metrics.cpu``.
    """
    if key in snapshot:
        return snapshot[key]
    parts = key.split(".")
    if len(parts) > 1:
        val: Any = snapshot
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                raise KeyError(
                    f"Snapshot is missing required key: {key!r}"
                )
        return val
    raise KeyError(f"Snapshot is missing required key: {key!r}")


def _evaluate(node: Any, snapshot: dict[str, Any]) -> bool:
    """Walk the AST and return a boolean result."""
    if isinstance(node, _Sentinel):
        return node.value

    if isinstance(node, _Comparison):
        left_val = _resolve_key(snapshot, node.left)
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
# High-level trigger classes
# ---------------------------------------------------------------------------


class EventTrigger:
    """Trigger that matches events by topic (action) pattern.

    Supports exact matches and glob-style wildcards via :mod:`fnmatch`.
    """

    def __init__(self, topic: str) -> None:
        self.topic = topic

    def matches(self, event: Any) -> bool:
        """Return ``True`` if *event*'s action matches this trigger's topic."""
        action: str = getattr(event, "action", "")
        if self.topic == "*":
            return True
        return fnmatch.fnmatch(action, self.topic)


class ConditionalTrigger:
    """Trigger that evaluates a comparison expression against a context dict.

    Wraps :func:`evaluate_trigger` for convenient reuse.
    """

    def __init__(self, expression: str) -> None:
        self.expression = expression
        # Eagerly parse so syntax errors surface at construction time.
        self._ast = parse_trigger(expression)

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Return ``True`` if *context* satisfies the expression."""
        return _evaluate(self._ast, context)


class CronTrigger:
    """Trigger that fires based on a cron schedule expression.

    Supports standard 5-field cron:
    ``minute hour day_of_month month day_of_week``
    """

    _DAY_NAMES: dict[str, int] = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
        "THU": 4, "FRI": 5, "SAT": 6,
    }

    def __init__(self, expression: str) -> None:
        self.expression = expression
        self._fields = self._parse(expression)

    def _parse(self, expression: str) -> list[set[int]]:
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields, got {len(parts)}: {expression!r}"
            )
        ranges = [
            (0, 59),  # minute
            (0, 23),  # hour
            (1, 31),  # day of month
            (1, 12),  # month
            (0, 6),   # day of week
        ]
        name_maps: list[dict[str, int] | None] = [
            None, None, None, None, self._DAY_NAMES,
        ]
        fields: list[set[int]] = []
        for part, (lo, hi), nmap in zip(parts, ranges, name_maps):
            fields.append(self._parse_field(part, lo, hi, nmap))
        return fields

    @staticmethod
    def _parse_field(
        field: str, lo: int, hi: int, name_map: dict[str, int] | None = None,
    ) -> set[int]:
        values: set[int] = set()
        for item in field.split(","):
            if name_map:
                upper = item.upper()
                for name, val in name_map.items():
                    upper = upper.replace(name, str(val))
                item = upper
            if "/" in item:
                range_part, step_str = item.split("/", 1)
                step = int(step_str)
                if step <= 0:
                    raise ValueError(
                        f"Step value must be positive, got {step} in {field!r}"
                    )
                if range_part == "*":
                    values.update(range(lo, hi + 1, step))
                else:
                    start = int(range_part)
                    values.update(range(start, hi + 1, step))
            elif item == "*":
                values.update(range(lo, hi + 1))
            elif "-" in item:
                start_str, end_str = item.split("-", 1)
                values.update(range(int(start_str), int(end_str) + 1))
            else:
                val = int(item)
                if val < lo or val > hi:
                    raise ValueError(
                        f"Value {val} out of range [{lo}, {hi}] in {field!r}"
                    )
                values.add(val)
        return values

    def should_fire(self, now: _dt.datetime | None = None) -> bool:
        """Return ``True`` if the cron expression matches *now*."""
        if now is None:
            now = _dt.datetime.now()
        minute, hour, day, month, dow = self._fields
        # isoweekday: Mon=1..Sun=7 → cron: Sun=0..Sat=6
        cron_dow = now.isoweekday() % 7
        return (
            now.minute in minute
            and now.hour in hour
            and now.day in day
            and now.month in month
            and cron_dow in dow
        )
