"""Git worktree helpers for isolated per-task workspaces."""

import os
import subprocess
from pathlib import Path

from crazypumpkin.framework.subprocess_util import run


def create_worktree(
    repo_path: str,
    branch_name: str,
    worktree_base_dir: str,
) -> str:
    """Create an isolated git worktree for an agent task.

    Args:
        repo_path: Path to the main git repository.
        branch_name: Branch name following the ``agent/<product-slug>/<task-slug>`` convention.
        worktree_base_dir: Directory under which the new worktree will be created.

    Returns:
        Absolute path to the created worktree directory.

    Raises:
        ValueError: If *branch_name* does not follow the required naming convention.
        RuntimeError: If the ``git worktree add`` command fails.
    """
    if not branch_name.startswith("agent/"):
        raise ValueError(
            f"Branch name must follow 'agent/<product-slug>/<task-slug>' convention, "
            f"got: {branch_name!r}"
        )

    parts = branch_name.split("/")
    if len(parts) < 3 or any(p == "" for p in parts):
        raise ValueError(
            f"Branch name must have at least three non-empty segments "
            f"('agent/<product-slug>/<task-slug>'), got: {branch_name!r}"
        )

    # Derive a filesystem-safe directory name from the branch name.
    worktree_dir_name = branch_name.replace("/", "-")
    worktree_path = str(Path(worktree_base_dir) / worktree_dir_name)

    os.makedirs(worktree_base_dir, exist_ok=True)

    cmd = ["git", "worktree", "add", "-b", branch_name, worktree_path]
    result = run(cmd, cwd=repo_path)

    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed (exit {result.returncode}): {result.stderr}"
        )

    return str(Path(worktree_path).resolve())
