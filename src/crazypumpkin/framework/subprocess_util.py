"""Cross-platform subprocess wrapper that suppresses console windows on Windows."""

import subprocess
import sys


def run(cmd, *, cwd=None, timeout=120, capture_output=True, text=True, **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, adding CREATE_NO_WINDOW on Windows to prevent flashing consoles."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", 0x08000000)
    return subprocess.run(
        cmd, cwd=cwd, timeout=timeout, capture_output=capture_output, text=text, **kwargs
    )
