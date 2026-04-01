"""Shared pytest configuration — ensure src/ is on sys.path for imports."""

import os
import sys
from pathlib import Path

# Set a stable JWT secret for the test suite before any dashboard imports.
os.environ.setdefault("CP_JWT_SECRET", "test-secret-do-not-use-in-production")

# Make 'src/' importable so that 'crazypumpkin.*' resolves for all test files.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
