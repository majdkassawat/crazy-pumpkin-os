"""Cron expression parser for the scheduler module."""

from __future__ import annotations

from dataclasses import dataclass, field


FIELD_NAMES = ("minute", "hour", "dom", "month", "dow")

FIELD_RANGES: dict[str, tuple[int, int]] = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 6),
}


@dataclass
class CronField:
    """Parsed representation of a single cron field.

    Attributes:
        values: The sorted set of integer values this field matches.
    """

    values: list[int] = field(default_factory=list)

    @property
    def is_all(self) -> bool:
        """Return True if this field matches every value in its range."""
        return False  # caller sets _all flag via factory

    def __repr__(self) -> str:
        return f"CronField(values={self.values})"


@dataclass
class CronExpression:
    """Structured representation of a five-field cron expression.

    Fields: minute, hour, dom (day-of-month), month, dow (day-of-week).
    """

    minute: CronField
    hour: CronField
    dom: CronField
    month: CronField
    dow: CronField


def _parse_field(token: str, field_name: str) -> CronField:
    """Parse a single cron field token into a CronField.

    Supports:
      - ``*``      — all values in range
      - ``*/N``    — every N-th value starting from range minimum
      - ``A-B``    — inclusive range
      - ``A,B,C``  — explicit list (elements may themselves be ranges or steps)
    """
    lo, hi = FIELD_RANGES[field_name]

    parts = token.split(",")
    values: set[int] = set()

    for part in parts:
        if part == "*":
            values.update(range(lo, hi + 1))
        elif part.startswith("*/"):
            step_str = part[2:]
            if not step_str.isdigit() or int(step_str) == 0:
                raise ValueError(
                    f"Invalid step in '{token}' for {field_name}: "
                    f"step must be a positive integer"
                )
            step = int(step_str)
            values.update(range(lo, hi + 1, step))
        elif "-" in part:
            # Could be A-B or A-B/N
            if "/" in part:
                range_part, step_str = part.split("/", 1)
                if not step_str.isdigit() or int(step_str) == 0:
                    raise ValueError(
                        f"Invalid step in '{token}' for {field_name}"
                    )
                step = int(step_str)
            else:
                range_part = part
                step = 1

            bounds = range_part.split("-")
            if len(bounds) != 2:
                raise ValueError(
                    f"Invalid range in '{token}' for {field_name}"
                )
            try:
                start, end = int(bounds[0]), int(bounds[1])
            except ValueError:
                raise ValueError(
                    f"Invalid range in '{token}' for {field_name}: "
                    f"non-integer bounds"
                )
            if start < lo or end > hi or start > end:
                raise ValueError(
                    f"Range {start}-{end} out of bounds for {field_name} "
                    f"(valid: {lo}-{hi})"
                )
            values.update(range(start, end + 1, step))
        else:
            # Single integer value
            try:
                val = int(part)
            except ValueError:
                raise ValueError(
                    f"Invalid value '{part}' in '{token}' for {field_name}: "
                    f"expected integer"
                )
            if val < lo or val > hi:
                raise ValueError(
                    f"Value {val} out of range for {field_name} "
                    f"(valid: {lo}-{hi})"
                )
            values.add(val)

    return CronField(values=sorted(values))


def parse_cron_expression(expr: str) -> CronExpression:
    """Parse a standard five-field cron expression.

    Args:
        expr: A cron expression string with five whitespace-separated fields
              (minute, hour, day-of-month, month, day-of-week).

    Returns:
        A ``CronExpression`` with each field parsed into a ``CronField``
        containing the sorted list of matching integer values.

    Raises:
        ValueError: If the expression does not have exactly five fields or
                    contains invalid syntax.
    """
    tokens = expr.strip().split()
    if len(tokens) != 5:
        raise ValueError(
            f"Cron expression must have exactly 5 fields, got {len(tokens)}: "
            f"'{expr}'"
        )

    fields: dict[str, CronField] = {}
    for token, name in zip(tokens, FIELD_NAMES):
        fields[name] = _parse_field(token, name)

    return CronExpression(
        minute=fields["minute"],
        hour=fields["hour"],
        dom=fields["dom"],
        month=fields["month"],
        dow=fields["dow"],
    )
