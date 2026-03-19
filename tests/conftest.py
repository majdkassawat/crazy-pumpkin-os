"""Shared pytest configuration — ensure src/ is on sys.path for imports."""

import sys
from pathlib import Path

# Make 'src/' importable so that 'crazypumpkin.*' resolves for all test files.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
