"""Tests for crazypumpkin.framework.subprocess_util."""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure src/ is importable when the package is not installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.subprocess_util import run


def test_run_returns_completed_process():
    """run() returns a subprocess.CompletedProcess object."""
    result = run([sys.executable, "-c", "print('hello')"])
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.stdout.strip() == "hello"
    assert result.returncode == 0


def test_run_passes_cwd(tmp_path):
    """run() forwards the cwd keyword to subprocess.run."""
    result = run(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
    # Resolve both to handle symlinks / short-path differences on Windows
    assert os.path.realpath(result.stdout.strip()) == os.path.realpath(str(tmp_path))


def test_run_passes_timeout():
    """run() forwards the timeout keyword to subprocess.run."""
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1)


def test_run_passes_arbitrary_kwargs():
    """run() forwards arbitrary kwargs to subprocess.run."""
    env = {"MY_TEST_VAR": "pumpkin123"}
    # Need to pass enough env for the subprocess to work on Windows
    if sys.platform == "win32":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    result = run(
        [sys.executable, "-c", "import os; print(os.environ.get('MY_TEST_VAR', ''))"],
        env=env,
    )
    assert result.returncode == 0
    assert "pumpkin123" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only behaviour")
def test_run_sets_creation_flags_on_windows():
    """On Windows, CREATE_NO_WINDOW flag is set by default."""
    with mock.patch("crazypumpkin.framework.subprocess_util.subprocess.run") as mocked:
        mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        run(["echo", "hi"])
        _, kwargs = mocked.call_args
        assert kwargs.get("creationflags") == 0x08000000


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only behaviour")
def test_run_does_not_override_explicit_creationflags():
    """If caller supplies creationflags, run() does not overwrite them."""
    with mock.patch("crazypumpkin.framework.subprocess_util.subprocess.run") as mocked:
        mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        run(["echo", "hi"], creationflags=0)
        _, kwargs = mocked.call_args
        assert kwargs.get("creationflags") == 0
