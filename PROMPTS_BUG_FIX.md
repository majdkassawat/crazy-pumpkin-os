# Bug Fix Prompt Template

Use this structured prompt when contributing a bug fix to Crazy Pumpkin OS.

## Prompt

```
You are fixing a bug in Crazy Pumpkin OS.

Issue: [paste issue title and description]

Steps:
1. Read the issue description and understand the expected vs actual behavior
2. Find the relevant source file(s) in src/crazypumpkin/
3. Read the existing code to understand the current implementation
4. Reproduce the bug by reading the test suite for related functionality
5. Implement the fix — minimal changes only
6. Write a test that verifies the fix (in tests/)
7. Run: python -m pytest tests/ -v --tb=short
8. Ensure ALL tests pass (not just your new test)
9. Commit with message: "Fix: [brief description of what was fixed]"
10. Open a PR referencing the issue number

Rules:
- Use Edit/Write tools — do not output code as text
- Keep changes minimal — fix the bug, nothing else
- Do not refactor surrounding code
- Include a test that would have caught this bug
- Follow existing code style and patterns
- Follow [Open Spec](https://github.com/open-spec/open-spec) format for any specification artifacts
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and approval tiers.
