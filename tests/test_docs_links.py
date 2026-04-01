"""Tests that all .md files referenced in docs/index.md exist on disk,
and that key documentation files contain the expected sections."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Root of the repository
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_md_links(text: str) -> list[str]:
    """Return all Markdown link targets ending in .md from *text*."""
    return re.findall(r'\[.*?\]\(([^)]+\.md)\)', text)


# ---------------------------------------------------------------------------
# Test: every .md link in index.md points to an existing file
# ---------------------------------------------------------------------------


class TestDocsIndexLinks:
    """Verify that docs/index.md references only existing .md files."""

    def test_index_exists(self):
        assert (DOCS_DIR / "index.md").is_file(), "docs/index.md must exist"

    def test_all_linked_md_files_exist(self):
        """Every .md link in index.md must point to an existing file."""
        index_text = (DOCS_DIR / "index.md").read_text(encoding="utf-8")
        links = _extract_md_links(index_text)
        assert links, "docs/index.md should contain at least one .md link"

        missing = []
        for link in links:
            target = DOCS_DIR / link
            if not target.is_file():
                missing.append(link)

        assert not missing, (
            f"docs/index.md references files that do not exist: {missing}"
        )

    @pytest.mark.parametrize("filename", [
        "QUICKSTART.md",
        "plugin-guide.md",
        "ci-cd-guide.md",
    ])
    def test_known_docs_exist(self, filename: str):
        """Specific doc files that must be present."""
        assert (DOCS_DIR / filename).is_file(), f"docs/{filename} must exist"

    def test_ci_cd_guide_linked_in_index(self):
        index_text = (DOCS_DIR / "index.md").read_text(encoding="utf-8")
        links = _extract_md_links(index_text)
        assert "ci-cd-guide.md" in links, (
            "docs/index.md must link to ci-cd-guide.md"
        )


# ---------------------------------------------------------------------------
# Test: docs/ci-cd-guide.md has required sections
# ---------------------------------------------------------------------------


class TestCiCdGuide:
    """Verify that docs/ci-cd-guide.md exists and contains all required sections."""

    @pytest.fixture()
    def guide_text(self) -> str:
        path = DOCS_DIR / "ci-cd-guide.md"
        assert path.is_file(), "docs/ci-cd-guide.md must exist"
        return path.read_text(encoding="utf-8")

    def test_overview_section(self, guide_text: str):
        assert re.search(r'^##\s+Overview', guide_text, re.MULTILINE), (
            "ci-cd-guide.md must have an '## Overview' section"
        )

    def test_setup_section(self, guide_text: str):
        assert re.search(r'^##\s+Setup', guide_text, re.MULTILINE), (
            "ci-cd-guide.md must have a '## Setup' section"
        )

    def test_setup_explains_oidc(self, guide_text: str):
        assert "trusted publisher" in guide_text.lower() or "oidc" in guide_text.lower(), (
            "Setup section must explain PyPI trusted publisher / OIDC configuration"
        )

    def test_usage_section(self, guide_text: str):
        assert re.search(r'^##\s+Usage', guide_text, re.MULTILINE), (
            "ci-cd-guide.md must have a '## Usage' section"
        )

    def test_tutorial_section(self, guide_text: str):
        assert re.search(r'^##\s+Tutorial', guide_text, re.MULTILINE), (
            "ci-cd-guide.md must have a '## Tutorial' section"
        )

    def test_tutorial_has_release_workflow(self, guide_text: str):
        """Tutorial must include a step-by-step release workflow."""
        assert "git tag" in guide_text, (
            "Tutorial should include 'git tag' step"
        )
        assert "git push --tags" in guide_text, (
            "Tutorial should include 'git push --tags' step"
        )
        assert "GitHub Release" in guide_text or "Publish release" in guide_text, (
            "Tutorial should mention creating a GitHub Release"
        )

    def test_troubleshooting_section(self, guide_text: str):
        assert re.search(r'^##\s+Troubleshooting', guide_text, re.MULTILINE), (
            "ci-cd-guide.md must have a '## Troubleshooting' section"
        )

    def test_troubleshooting_covers_oidc_failure(self, guide_text: str):
        assert "OIDC" in guide_text or "oidc" in guide_text, (
            "Troubleshooting should cover OIDC authentication failure"
        )

    def test_troubleshooting_covers_build_errors(self, guide_text: str):
        assert "Build Error" in guide_text or "build error" in guide_text or "python -m build" in guide_text, (
            "Troubleshooting should cover build errors"
        )

    def test_troubleshooting_covers_test_failures(self, guide_text: str):
        assert "Test Failure" in guide_text or "test failure" in guide_text or "Tests pass locally but fail" in guide_text, (
            "Troubleshooting should cover test failures in CI"
        )
