# First Contribution Prompt Template

Use this simplified prompt for your first contribution to Crazy Pumpkin OS.

## Prompt

```
You are making your first contribution to Crazy Pumpkin OS, an open-source
autonomous AI company framework.

Steps:
1. Read CONTRIBUTING.md to understand the rules
2. Look at open issues labeled "good-first-issue" on GitHub
3. Pick one issue and read it carefully
4. Fork and clone the repository
5. Create a branch: git checkout -b fix/issue-description
6. Install: pip install -e ".[dev]"
7. Make the minimal change needed to address the issue
8. Run tests: python -m pytest tests/ -v --tb=short
9. If tests pass, commit: git commit -m "Fix: brief description"
10. Push and open a PR following the PR template

Tips:
- Start small — documentation or test improvements are great first PRs
- Read existing code before writing new code
- Ask questions in the issue if anything is unclear
- One logical change per PR — don't bundle unrelated fixes
```
