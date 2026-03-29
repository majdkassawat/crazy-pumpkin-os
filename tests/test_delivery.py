"""Tests for crazypumpkin.framework.delivery."""

import importlib
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.delivery import commit_and_push, create_worktree, deliver

_models = importlib.import_module("crazypumpkin.framework.models")
DeliveryConfig = _models.DeliveryConfig
DeliveryMode = _models.DeliveryMode


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


# --- commit_and_push tests ---

class TestCommitAndPush:
    """commit_and_push stages, commits with author, and pushes."""

    def _ok(self, **overrides):
        defaults = {"args": [], "returncode": 0, "stdout": "main\n", "stderr": ""}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def _fail(self, **overrides):
        defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "fatal: error"}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def test_stages_commits_and_pushes(self, tmp_path):
        """Happy path: all three git commands succeed."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._ok()
            commit_and_push(
                str(tmp_path), ["a.py", "b.py"],
                "feat: add stuff", "Bot", "bot@example.com", "origin",
            )
            assert mocked.call_count == 4  # add, commit, rev-parse, push

    def test_git_add_command(self, tmp_path):
        """git add is called with the correct files."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._ok()
            commit_and_push(
                str(tmp_path), ["x.py"],
                "msg", "A", "a@b.com",
            )
            add_call = mocked.call_args_list[0]
            cmd = add_call[0][0]
            assert cmd[:3] == ["git", "add", "--"]
            assert "x.py" in cmd

    def test_commit_uses_author_flag(self, tmp_path):
        """git commit includes --author with correct format."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._ok()
            commit_and_push(
                str(tmp_path), ["f.py"],
                "msg", "Nova", "nova@cp.dev",
            )
            commit_call = mocked.call_args_list[1]
            cmd = commit_call[0][0]
            assert "--author" in cmd
            idx = cmd.index("--author")
            assert cmd[idx + 1] == "Nova <nova@cp.dev>"

    def test_push_uses_detected_branch(self, tmp_path):
        """git push uses the branch name from rev-parse."""
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(),  # add
                self._ok(),  # commit
                self._ok(stdout="agent/prod/task\n"),  # rev-parse
                self._ok(),  # push
            ]
            commit_and_push(
                str(tmp_path), ["f.py"],
                "msg", "A", "a@b.com", "upstream",
            )
            push_call = mocked.call_args_list[3]
            cmd = push_call[0][0]
            assert cmd == ["git", "push", "upstream", "agent/prod/task"]

    def test_raises_on_add_failure(self, tmp_path):
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._fail()
            with pytest.raises(RuntimeError, match="git add failed"):
                commit_and_push(
                    str(tmp_path), ["f.py"],
                    "msg", "A", "a@b.com",
                )

    def test_raises_on_commit_failure(self, tmp_path):
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [self._ok(), self._fail()]
            with pytest.raises(RuntimeError, match="git commit failed"):
                commit_and_push(
                    str(tmp_path), ["f.py"],
                    "msg", "A", "a@b.com",
                )

    def test_raises_on_push_failure(self, tmp_path):
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(),  # add
                self._ok(),  # commit
                self._ok(stdout="main\n"),  # rev-parse
                self._fail(),  # push
            ]
            with pytest.raises(RuntimeError, match="git push failed"):
                commit_and_push(
                    str(tmp_path), ["f.py"],
                    "msg", "A", "a@b.com",
                )

    def test_cwd_is_worktree_path(self, tmp_path):
        """All git commands run inside the worktree directory."""
        wt = str(tmp_path / "my-worktree")
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._ok()
            commit_and_push(wt, ["f.py"], "msg", "A", "a@b.com")
            for call in mocked.call_args_list:
                assert call[1]["cwd"] == wt


# --- deliver() tests ---

class TestDeliverPullRequest:
    """deliver() in pull_request mode creates a PR via gh CLI."""

    def _ok(self, **overrides):
        defaults = {"args": [], "returncode": 0, "stdout": "", "stderr": ""}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def _fail(self, **overrides):
        defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "fatal: error"}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def test_calls_gh_pr_create_with_title_body_head(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.PULL_REQUEST)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="agent/prod/task\n"),  # rev-parse
                self._ok(stdout="https://github.com/org/repo/pull/42\n"),  # gh pr create
            ]
            result = deliver(str(tmp_path), config, "My PR", "PR body text")

            assert result == "https://github.com/org/repo/pull/42"

            # Check gh pr create call
            pr_call = mocked.call_args_list[1]
            cmd = pr_call[0][0]
            assert cmd[0] == "gh"
            assert cmd[1] == "pr"
            assert cmd[2] == "create"
            assert "--title" in cmd
            assert cmd[cmd.index("--title") + 1] == "My PR"
            assert "--body" in cmd
            assert cmd[cmd.index("--body") + 1] == "PR body text"
            assert "--head" in cmd
            assert cmd[cmd.index("--head") + 1] == "agent/prod/task"

    def test_raises_on_rev_parse_failure(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.PULL_REQUEST)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.return_value = self._fail()
            with pytest.raises(RuntimeError, match="git rev-parse failed"):
                deliver(str(tmp_path), config, "t", "b")

    def test_raises_on_gh_pr_create_failure(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.PULL_REQUEST)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="feat-branch\n"),  # rev-parse
                self._fail(),  # gh pr create
            ]
            with pytest.raises(RuntimeError, match="gh pr create failed"):
                deliver(str(tmp_path), config, "t", "b")

    def test_cwd_is_worktree_path(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.PULL_REQUEST)
        wt = str(tmp_path / "wt")
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="branch\n"),
                self._ok(stdout="url\n"),
            ]
            deliver(wt, config, "t", "b")
            for call in mocked.call_args_list:
                assert call[1]["cwd"] == wt


class TestDeliverDirectPush:
    """deliver() in direct_push mode pushes directly without creating a PR."""

    def _ok(self, **overrides):
        defaults = {"args": [], "returncode": 0, "stdout": "", "stderr": ""}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def _fail(self, **overrides):
        defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "fatal: error"}
        defaults.update(overrides)
        return subprocess.CompletedProcess(**defaults)

    def test_merges_and_pushes_to_default_branch(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.DIRECT_PUSH)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="agent/prod/task\n"),    # rev-parse HEAD
                self._ok(stdout="origin/main\n"),         # rev-parse origin/HEAD
                self._ok(),                               # checkout main
                self._ok(),                               # merge
                self._ok(),                               # push
            ]
            result = deliver(str(tmp_path), config, "ignored", "ignored")

            assert result == "main"
            assert mocked.call_count == 5

            # Verify checkout
            checkout_call = mocked.call_args_list[2]
            assert checkout_call[0][0] == ["git", "checkout", "main"]

            # Verify merge
            merge_call = mocked.call_args_list[3]
            assert merge_call[0][0] == ["git", "merge", "agent/prod/task"]

            # Verify push
            push_call = mocked.call_args_list[4]
            assert push_call[0][0] == ["git", "push", "origin", "main"]

    def test_raises_on_checkout_failure(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.DIRECT_PUSH)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="feat\n"),        # rev-parse HEAD
                self._ok(stdout="origin/main\n"), # rev-parse origin/HEAD
                self._fail(),                     # checkout fails
            ]
            with pytest.raises(RuntimeError, match="git checkout failed"):
                deliver(str(tmp_path), config, "t", "b")

    def test_raises_on_merge_failure(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.DIRECT_PUSH)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="feat\n"),
                self._ok(stdout="origin/main\n"),
                self._ok(),       # checkout
                self._fail(),     # merge fails
            ]
            with pytest.raises(RuntimeError, match="git merge failed"):
                deliver(str(tmp_path), config, "t", "b")

    def test_raises_on_push_failure(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.DIRECT_PUSH)
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="feat\n"),
                self._ok(stdout="origin/main\n"),
                self._ok(),       # checkout
                self._ok(),       # merge
                self._fail(),     # push fails
            ]
            with pytest.raises(RuntimeError, match="git push failed"):
                deliver(str(tmp_path), config, "t", "b")

    def test_cwd_is_worktree_path(self, tmp_path):
        config = DeliveryConfig(delivery_mode=DeliveryMode.DIRECT_PUSH)
        wt = str(tmp_path / "wt")
        with mock.patch("crazypumpkin.framework.delivery.run") as mocked:
            mocked.side_effect = [
                self._ok(stdout="feat\n"),
                self._ok(stdout="origin/main\n"),
                self._ok(),
                self._ok(),
                self._ok(),
            ]
            deliver(wt, config, "t", "b")
            for call in mocked.call_args_list:
                assert call[1]["cwd"] == wt
