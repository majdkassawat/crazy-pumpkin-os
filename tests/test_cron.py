"""Tests for parse_cron_expression and _parse_field."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.scheduler.cron import (
    CronExpression,
    CronField,
    FIELD_RANGES,
    parse_cron_expression,
    _parse_field,
)


# ---------------------------------------------------------------------------
# Tests — wildcard (*)
# ---------------------------------------------------------------------------


class TestWildcard:
    """Wildcard (*) expands to all values in the field range."""

    def test_star_minute(self):
        field = _parse_field("*", "minute")
        assert field.values == list(range(0, 60))

    def test_star_hour(self):
        field = _parse_field("*", "hour")
        assert field.values == list(range(0, 24))

    def test_star_dom(self):
        field = _parse_field("*", "dom")
        assert field.values == list(range(1, 32))

    def test_star_month(self):
        field = _parse_field("*", "month")
        assert field.values == list(range(1, 13))

    def test_star_dow(self):
        field = _parse_field("*", "dow")
        assert field.values == list(range(0, 7))


# ---------------------------------------------------------------------------
# Tests — step (*/N)
# ---------------------------------------------------------------------------


class TestStep:
    """*/N produces every N-th value starting from range minimum."""

    def test_every_15_minutes(self):
        field = _parse_field("*/15", "minute")
        assert field.values == [0, 15, 30, 45]

    def test_every_2_hours(self):
        field = _parse_field("*/2", "hour")
        assert field.values == list(range(0, 24, 2))

    def test_every_5_months(self):
        field = _parse_field("*/5", "month")
        assert field.values == [1, 6, 11]

    def test_every_3_dow(self):
        field = _parse_field("*/3", "dow")
        assert field.values == [0, 3, 6]

    def test_step_1_is_same_as_star(self):
        field = _parse_field("*/1", "minute")
        assert field.values == list(range(0, 60))

    def test_step_larger_than_range(self):
        field = _parse_field("*/100", "minute")
        assert field.values == [0]


# ---------------------------------------------------------------------------
# Tests — range (A-B)
# ---------------------------------------------------------------------------


class TestRange:
    """A-B produces inclusive range of values."""

    def test_range_minutes(self):
        field = _parse_field("10-20", "minute")
        assert field.values == list(range(10, 21))

    def test_range_hours(self):
        field = _parse_field("9-17", "hour")
        assert field.values == list(range(9, 18))

    def test_range_single_value(self):
        field = _parse_field("5-5", "minute")
        assert field.values == [5]

    def test_range_with_step(self):
        field = _parse_field("1-10/3", "minute")
        assert field.values == [1, 4, 7, 10]

    def test_range_dom(self):
        field = _parse_field("1-15", "dom")
        assert field.values == list(range(1, 16))


# ---------------------------------------------------------------------------
# Tests — comma-list (A,B,C)
# ---------------------------------------------------------------------------


class TestCommaList:
    """Comma-separated lists produce the union of values."""

    def test_simple_list(self):
        field = _parse_field("1,15,30", "minute")
        assert field.values == [1, 15, 30]

    def test_list_with_range(self):
        field = _parse_field("1,10-12,20", "minute")
        assert field.values == [1, 10, 11, 12, 20]

    def test_list_with_star(self):
        # star in a comma list expands to full range
        field = _parse_field("*,5", "dow")
        assert field.values == list(range(0, 7))

    def test_list_deduplicates(self):
        field = _parse_field("5,5,5", "minute")
        assert field.values == [5]

    def test_list_sorted(self):
        field = _parse_field("30,10,20", "minute")
        assert field.values == [10, 20, 30]

    def test_list_months(self):
        field = _parse_field("1,6,12", "month")
        assert field.values == [1, 6, 12]


# ---------------------------------------------------------------------------
# Tests — full expression parsing
# ---------------------------------------------------------------------------


class TestParseExpression:
    """parse_cron_expression returns a CronExpression with correctly parsed fields."""

    def test_all_stars(self):
        expr = parse_cron_expression("* * * * *")
        assert isinstance(expr, CronExpression)
        assert expr.minute.values == list(range(0, 60))
        assert expr.hour.values == list(range(0, 24))
        assert expr.dom.values == list(range(1, 32))
        assert expr.month.values == list(range(1, 13))
        assert expr.dow.values == list(range(0, 7))

    def test_specific_values(self):
        expr = parse_cron_expression("30 9 1 1 0")
        assert expr.minute.values == [30]
        assert expr.hour.values == [9]
        assert expr.dom.values == [1]
        assert expr.month.values == [1]
        assert expr.dow.values == [0]

    def test_every_5_minutes(self):
        expr = parse_cron_expression("*/5 * * * *")
        assert expr.minute.values == [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

    def test_weekday_9am(self):
        expr = parse_cron_expression("0 9 * * 1-5")
        assert expr.hour.values == [9]
        assert expr.dow.values == [1, 2, 3, 4, 5]

    def test_range_with_step_1_10_2(self):
        expr = parse_cron_expression("1-10/2 * * * *")
        assert expr.minute.values == [1, 3, 5, 7, 9]

    def test_mixed_syntax(self):
        expr = parse_cron_expression("*/15 9-17 1,15 * 1-5")
        assert expr.minute.values == [0, 15, 30, 45]
        assert expr.hour.values == list(range(9, 18))
        assert expr.dom.values == [1, 15]
        assert expr.month.values == list(range(1, 13))
        assert expr.dow.values == [1, 2, 3, 4, 5]

    def test_leading_trailing_whitespace(self):
        expr = parse_cron_expression("  0 0 1 1 0  ")
        assert expr.minute.values == [0]
        assert expr.hour.values == [0]

    def test_multiple_spaces_between_fields(self):
        expr = parse_cron_expression("0  0  1  1  0")
        # split() without args handles multiple spaces
        assert expr.minute.values == [0]


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrors:
    """Invalid input raises ValueError with descriptive messages."""

    def test_too_few_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron_expression("* * *")

    def test_too_many_fields(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron_expression("* * * * * *")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron_expression("")

    def test_single_field(self):
        with pytest.raises(ValueError, match="5 fields"):
            parse_cron_expression("*")

    def test_out_of_range_minute(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("60 * * * *")

    def test_out_of_range_hour(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 24 * * *")

    def test_out_of_range_dom_zero(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 0 0 * *")

    def test_out_of_range_dom_32(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 0 32 * *")

    def test_out_of_range_month_zero(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 0 1 0 *")

    def test_out_of_range_month_13(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 0 1 13 *")

    def test_out_of_range_dow(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_cron_expression("0 0 * * 7")

    def test_negative_value(self):
        with pytest.raises(ValueError):
            _parse_field("-1", "minute")

    def test_non_numeric_value(self):
        with pytest.raises(ValueError, match="expected integer"):
            _parse_field("abc", "minute")

    def test_step_zero(self):
        with pytest.raises(ValueError, match="step must be a positive integer"):
            _parse_field("*/0", "minute")

    def test_step_non_numeric(self):
        with pytest.raises(ValueError, match="step must be a positive integer"):
            _parse_field("*/abc", "minute")

    def test_range_inverted(self):
        with pytest.raises(ValueError, match="out of bounds"):
            _parse_field("20-10", "minute")

    def test_range_out_of_bounds_high(self):
        with pytest.raises(ValueError, match="out of bounds"):
            _parse_field("0-60", "minute")

    def test_range_out_of_bounds_low(self):
        with pytest.raises(ValueError, match="out of bounds"):
            _parse_field("0-5", "dom")  # dom starts at 1

    def test_range_non_integer(self):
        with pytest.raises(ValueError, match="non-integer"):
            _parse_field("a-b", "minute")

    def test_range_step_zero(self):
        with pytest.raises(ValueError, match="Invalid step"):
            _parse_field("1-10/0", "minute")
