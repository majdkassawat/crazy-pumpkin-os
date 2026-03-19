"""
Agent lock — mutex for git operations and shared resources.

Prevents concurrent git operations by multiple agents.
Uses atomic file creation with PID tracking and stale detection.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("crazypumpkin.lock")

STALE_THRESHOLD = 1800  # 30 minutes


class AgentLock:
    """Context manager for exclusive agent operations.

    Usage:
        with AgentLock("developer", lock_path=Path("data/.agent_lock"), timeout=120) as lock:
            if lock.acquired:
                # do git ops
    """

    def __init__(self, agent_name: str, lock_path: Path, timeout: int = 120):
        self.agent_name = agent_name
        self.lock_path = Path(lock_path)
        self.timeout = timeout
        self.acquired = False

    def __enter__(self) -> AgentLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout

        while time.time() < deadline:
            # Try to remove stale locks first
            self._cleanup_stale()

            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                lock_data = json.dumps({
                    "agent": self.agent_name,
                    "pid": os.getpid(),
                    "acquired_at": time.time(),
                })
                os.write(fd, lock_data.encode())
                os.close(fd)
                self.acquired = True
                logger.debug("Lock acquired by %s", self.agent_name)
                return self
            except FileExistsError:
                time.sleep(3)

        logger.warning("Lock timeout for %s after %ds", self.agent_name, self.timeout)
        return self

    def __exit__(self, *args) -> None:
        if self.acquired:
            try:
                self.lock_path.unlink(missing_ok=True)
                logger.debug("Lock released by %s", self.agent_name)
            except OSError as e:
                logger.error("Failed to release lock: %s", e)
            self.acquired = False

    def _cleanup_stale(self) -> None:
        """Remove lock if it's stale (too old or held by dead process)."""
        if not self.lock_path.exists():
            return
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            acquired_at = data.get("acquired_at", 0)
            pid = data.get("pid", 0)

            # Stale by time
            if time.time() - acquired_at > STALE_THRESHOLD:
                logger.warning("Removing stale lock (age: %.0fs, agent: %s)",
                               time.time() - acquired_at, data.get("agent"))
                self.lock_path.unlink(missing_ok=True)
                return

            # Stale by dead process
            if pid and not self._pid_alive(pid):
                logger.warning("Removing lock held by dead process (pid=%d)", pid)
                self.lock_path.unlink(missing_ok=True)

        except (json.JSONDecodeError, OSError):
            # Corrupt lock file — remove it
            logger.warning("Removing corrupt lock file")
            self.lock_path.unlink(missing_ok=True)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Check if a process is still running."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
