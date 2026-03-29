"""Git worktree helpers for isolated per-task workspaces."""

import os
import subprocess
from pathlib import Path

from crazypumpkin.framework.models import DeliveryConfig, DeliveryMode
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


def commit_and_push(
    worktree_path: str,
    files: list[str],
    commit_message: str,
    author_name: str,
    author_email: str,
    remote: str = "origin",
) -> None:
    """Stage files, commit with author attribution, and push the branch.

    Args:
        worktree_path: Path to the git worktree directory.
        files: List of file paths (relative to worktree) to stage.
        commit_message: Commit message text.
        author_name: Name for the ``--author`` git flag.
        author_email: Email for the ``--author`` git flag.
        remote: Git remote name to push to (default ``origin``).

    Raises:
        RuntimeError: If any git command (add, commit, or push) fails.
    """
    # Stage files
    add_cmd = ["git", "add", "--"] + list(files)
    result = run(add_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git add failed (exit {result.returncode}): {result.stderr}"
        )

    # Commit with author attribution
    author = f"{author_name} <{author_email}>"
    commit_cmd = [
        "git", "commit",
        "--author", author,
        "-m", commit_message,
    ]
    result = run(commit_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git commit failed (exit {result.returncode}): {result.stderr}"
        )

    # Detect current branch
    branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    result = run(branch_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git rev-parse failed (exit {result.returncode}): {result.stderr}"
        )
    branch = result.stdout.strip()

    # Push to remote
    push_cmd = ["git", "push", remote, branch]
    result = run(push_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git push failed (exit {result.returncode}): {result.stderr}"
        )


def deliver(
    worktree_path: str,
    config: DeliveryConfig,
    title: str,
    body: str,
) -> str:
    """Deliver committed work via PR or direct push.

    Args:
        worktree_path: Path to the git worktree with committed changes.
        config: Delivery configuration controlling the mode.
        title: PR title (used only in pull_request mode).
        body: PR body text (used only in pull_request mode).

    Returns:
        The URL of the created PR (pull_request mode) or the pushed branch name (direct_push mode).

    Raises:
        RuntimeError: If any git or gh command fails.
    """
    if config.delivery_mode == DeliveryMode.PULL_REQUEST:
        return _deliver_pull_request(worktree_path, title, body)
    elif config.delivery_mode == DeliveryMode.DIRECT_PUSH:
        return _deliver_direct_push(worktree_path)
    else:
        raise ValueError(f"Unknown delivery mode: {config.delivery_mode!r}")


def _deliver_pull_request(worktree_path: str, title: str, body: str) -> str:
    """Create a pull request using the ``gh`` CLI."""
    # Detect the current branch to use as --head
    branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    result = run(branch_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git rev-parse failed (exit {result.returncode}): {result.stderr}"
        )
    head_branch = result.stdout.strip()

    pr_cmd = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--head", head_branch,
    ]
    result = run(pr_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr create failed (exit {result.returncode}): {result.stderr}"
        )
    return result.stdout.strip()


def _deliver_direct_push(worktree_path: str) -> str:
    """Merge the current branch into the default branch and push."""
    # Detect the current feature branch
    branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    result = run(branch_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git rev-parse failed (exit {result.returncode}): {result.stderr}"
        )
    feature_branch = result.stdout.strip()

    # Detect the default branch via the remote HEAD
    default_cmd = ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"]
    result = run(default_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to detect default branch (exit {result.returncode}): {result.stderr}"
        )
    default_branch = result.stdout.strip().removeprefix("origin/")

    # Checkout the default branch
    checkout_cmd = ["git", "checkout", default_branch]
    result = run(checkout_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git checkout failed (exit {result.returncode}): {result.stderr}"
        )

    # Merge the feature branch
    merge_cmd = ["git", "merge", feature_branch]
    result = run(merge_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git merge failed (exit {result.returncode}): {result.stderr}"
        )

    # Push the default branch
    push_cmd = ["git", "push", "origin", default_branch]
    result = run(push_cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise RuntimeError(
            f"git push failed (exit {result.returncode}): {result.stderr}"
        )

    return default_branch
