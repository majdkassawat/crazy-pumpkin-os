import os
import re
from pathlib import Path

import pytest

from crazypumpkin.framework.paths import get_project_root, resolve_path


class TestResolvePath:
    def test_expands_tilde(self, tmp_path):
        result = resolve_path("~/somedir/file.txt", tmp_path)
        assert result == Path.home().joinpath("somedir", "file.txt").resolve()

    def test_substitutes_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_TEST_VAR", "replaced")
        result = resolve_path("${MY_TEST_VAR}/file.txt", tmp_path)
        expected = (tmp_path / "replaced" / "file.txt").resolve()
        assert result == expected

    def test_unset_env_var_left_literal(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UNSET_VAR_XYZ_999", raising=False)
        result = resolve_path("${UNSET_VAR_XYZ_999}/file.txt", tmp_path)
        expected = (tmp_path / "${UNSET_VAR_XYZ_999}" / "file.txt").resolve()
        assert result == expected

    def test_relative_resolved_against_project_root(self, tmp_path):
        result = resolve_path("subdir/file.txt", tmp_path)
        expected = (tmp_path / "subdir" / "file.txt").resolve()
        assert result == expected

    def test_absolute_path_unchanged(self, tmp_path):
        if os.name == "nt":
            abs_path = "C:/absolute/path/file.txt"
        else:
            abs_path = "/absolute/path/file.txt"
        result = resolve_path(abs_path, tmp_path)
        assert result == Path(abs_path).resolve()
        assert result.is_absolute()

    def test_returns_absolute_path(self, tmp_path):
        result = resolve_path("relative/path", tmp_path)
        assert result.is_absolute()


class TestGetProjectRoot:
    def test_finds_config_in_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "config.yaml").write_text("test: true")
        monkeypatch.chdir(tmp_path)
        assert get_project_root() == tmp_path.resolve()

    def test_finds_config_in_ancestor(self, tmp_path, monkeypatch):
        (tmp_path / "config.yaml").write_text("test: true")
        child = tmp_path / "a" / "b" / "c"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        assert get_project_root() == tmp_path.resolve()

    def test_raises_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError, match=re.escape(str(tmp_path))):
            get_project_root()
