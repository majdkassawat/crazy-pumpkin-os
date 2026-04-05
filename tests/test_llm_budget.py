"""Tests for BudgetEnforcer singleton in crazypumpkin.llm."""

from __future__ import annotations

import pytest

from crazypumpkin.llm import base as llm_base
from crazypumpkin.llm import get_default_enforcer, set_default_enforcer
from crazypumpkin.observability.budget import BudgetEnforcer


@pytest.fixture(autouse=True)
def _reset_enforcer():
    """Ensure module-level enforcer is cleared before and after each test."""
    llm_base._default_enforcer = None
    yield
    llm_base._default_enforcer = None


def test_importable_from_llm_package():
    """get_default_enforcer and set_default_enforcer are importable from crazypumpkin.llm."""
    from crazypumpkin.llm import get_default_enforcer as gde, set_default_enforcer as sde

    assert callable(gde)
    assert callable(sde)


def test_default_enforcer_is_none_initially():
    """get_default_enforcer returns None before any enforcer is set."""
    assert get_default_enforcer() is None


def test_set_then_get_enforcer():
    """set_default_enforcer sets the singleton; get_default_enforcer returns it."""
    enforcer = BudgetEnforcer()
    set_default_enforcer(enforcer)
    assert get_default_enforcer() is enforcer


def test_set_replaces_previous():
    """Setting a new enforcer replaces the previous one."""
    e1 = BudgetEnforcer()
    e2 = BudgetEnforcer()
    set_default_enforcer(e1)
    set_default_enforcer(e2)
    assert get_default_enforcer() is e2
    assert get_default_enforcer() is not e1
