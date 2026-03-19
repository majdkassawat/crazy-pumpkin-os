"""Safe file I/O helpers for Windows environments.

Windows Defender and Search Indexer can transiently lock files
immediately after creation, causing WinError 1920. This module
provides write wrappers with atomic temp-file writes and retry.
"""

from __future__ import annotations

import logging
import os
import random
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("crazypumpkin.io")

_MAX_RETRIES = 8
_BASE_DELAY = 0.3  # seconds
_MAX_DELAY = 10.0  # seconds — cap per-attempt delay


def safe_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text to *path* atomically with retry on transient Windows file-lock errors.

    Strategy: write to a temp file in the same directory (ensures same
    filesystem volume), then use os.replace() for an atomic rename.
    This eliminates the window where Windows Defender or Search Indexer
    can lock the target file during creation.

    Retries up to _MAX_RETRIES times with exponential backoff.
    Re-raises after all retries are exhausted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        fd = None
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=".kw_"
            )
            os.write(fd, content.encode(encoding))
            os.close(fd)
            fd = None
            os.replace(tmp_path, str(path))
            return
        except OSError as exc:
            last_exc = exc
            # Clean up temp file on failure
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            if getattr(exc, 'winerror', None) not in (1920, 32) and not isinstance(exc, PermissionError):
                raise
            if attempt < _MAX_RETRIES:
                delay = min(_MAX_DELAY, _BASE_DELAY * (2 ** attempt) * (0.75 + random.random() * 0.5))
                logger.debug(
                    "Transient file lock on %s (attempt %d/%d, retrying in %.2fs): %s",
                    path, attempt + 1, _MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
    logger.error("Failed to write %s after %d attempts: %s", path, _MAX_RETRIES + 1, last_exc)
    raise last_exc  # type: ignore[misc]


def safe_read_text(path: Path, encoding: str = "utf-8", errors: str | None = None) -> str:
    """Read text from *path* with retry on transient Windows file-lock errors.

    Retries up to _MAX_RETRIES times with exponential backoff.
    Re-raises after all retries are exhausted.

    Pass *errors* (e.g. ``"replace"``) to tolerate encoding issues in
    non-UTF-8 files while still getting retry-on-lock behaviour.
    """
    last_exc: Exception | None = None
    kwargs: dict = {"encoding": encoding}
    if errors is not None:
        kwargs["errors"] = errors
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return path.read_text(**kwargs)
        except OSError as exc:
            last_exc = exc
            if getattr(exc, 'winerror', None) not in (1920, 32) and not isinstance(exc, PermissionError):
                raise
            if attempt < _MAX_RETRIES:
                delay = min(_MAX_DELAY, _BASE_DELAY * (2 ** attempt) * (0.75 + random.random() * 0.5))
                logger.debug(
                    "Transient file lock on %s (attempt %d/%d, retrying in %.2fs): %s",
                    path, attempt + 1, _MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
    logger.error("Failed to read %s after %d attempts: %s", path, _MAX_RETRIES + 1, last_exc)
    raise last_exc  # type: ignore[misc]
