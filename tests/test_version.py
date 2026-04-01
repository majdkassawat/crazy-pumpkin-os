"""Tests for version management."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin import __version__


def test_version_is_string():
    assert isinstance(__version__, str)


def test_version_is_valid_semver():
    # Matches major.minor.patch with optional pre-release/build metadata
    pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$"
    assert re.match(pattern, __version__), f"{__version__!r} is not valid semver"
