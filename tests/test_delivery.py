"""Tests for crazypumpkin.framework.delivery."""

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.delivery import create_worktree


# --- validation tests ---

class TestBranchNameValidation:
    """create_worktree rejects branch names that don't match the convention."""

    def test_rejects_name_without_agent_prefix(self, tmp_path):
        with pytest.raises(ValueError, match="agent/"):
            create_worktree(str(tmp_path), "feature/foo/bar", str(tmp_path / "wt"))

    def test_rejects_name_with_too_few_segments(self, tmp_path):
        with pytest.raises(ValueError, match="three non-empty"):
            create_worktree(str(tmp_path), "agent/only-one", str(tmp_path / "wt"))

    def test_rejects_name_with_empty_segments(self, tmp_path):
        with pytest.raises(ValueError, match="three non-empty"):
            create_worktree(str(tmp_path), "agent//task", str(tmp_path / "wt"))

    def test_accepts_valid_three_segment_name(self, tmp_path):
        """A well-formed name passes validation (git call is mocked)."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            create_worktree(
                str(tmp_path), "agent/my-product/my-task", str(tmp_path / "wt")
            )
            mocked.assert_called_once()

    def test_accepts_deeper_nesting(self, tmp_path):
        """Extra segments beyond three are allowed."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            create_worktree(
                str(tmp_path), "agent/prod/task/sub", str(tmp_path / "wt")
            )
            mocked.assert_called_once()


# --- git invocation tests ---

class TestGitWorktreeCommand:
    """create_worktree invokes git correctly and handles results."""

    def test_calls_git_worktree_add(self, tmp_path):
        repo = str(tmp_path / "repo")
        base = str(tmp_path / "wt")
        branch = "agent/slug/task"

        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            create_worktree(repo, branch, base)

            args, kwargs = mocked.call_args
            cmd = args[0]
            assert cmd[0] == "git"
            assert cmd[1] == "worktree"
            assert cmd[2] == "add"
            assert "-b" in cmd
            assert branch in cmd
            assert kwargs["cwd"] == repo

    def test_returns_resolved_worktree_path(self, tmp_path):
        base = str(tmp_path / "wt")
        branch = "agent/slug/task"
        expected_dir = "agent-slug-task"

        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            result = create_worktree(str(tmp_path), branch, base)

        assert expected_dir in result
        assert Path(result).is_absolute()

    def test_raises_runtime_error_on_failure(self, tmp_path):
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="fatal: something went wrong"
            )
            with pytest.raises(RuntimeError, match="git worktree add failed"):
                create_worktree(
                    str(tmp_path), "agent/p/t", str(tmp_path / "wt")
                )

    def test_creates_base_dir_if_missing(self, tmp_path):
        base = tmp_path / "nested" / "wt"
        assert not base.exists()

        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            create_worktree(str(tmp_path), "agent/p/t", str(base))

        assert base.exists()
