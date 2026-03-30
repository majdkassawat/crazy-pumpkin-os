# Contributing to Crazy Pumpkin OS

Thank you for your interest in contributing to Crazy Pumpkin OS! This document explains how contributions are reviewed, what areas are open for contribution, and how to get started.

If this is your first time contributing, see [FIRST_CONTRIBUTION.md](FIRST_CONTRIBUTION.md) for a step-by-step walkthrough.

---

## Approval Tiers

All contributions go through a tiered review process based on what is being changed.

### Tier 1 — Auto-Approve

Changes that are low-risk and don't affect runtime behavior. These are reviewed quickly and can be merged with minimal discussion.

- Documentation updates (README, guides, docstrings)
- Test additions or improvements
- Code style and formatting fixes
- Typo corrections

### Tier 2 — Discussion Required

Changes that affect how agents behave or how the system orchestrates work. These require at least one maintainer review and may involve design discussion before merging.

- Agent logic (anything under `src/crazypumpkin/agents/`)
- Orchestrator and scheduler changes (`src/crazypumpkin/scheduler/`)
- Framework internals (`src/crazypumpkin/framework/`)
- LLM provider integrations (`src/crazypumpkin/llm/`)
- CLI behavior changes (`src/crazypumpkin/cli.py`)

### Tier 3 — Founder-Only

Changes that affect the project's legal standing, governance, or strategic direction. These require explicit approval from the project founder.

- License changes or additions
- Governance documents (CODE_OF_CONDUCT, CONTRIBUTING, SECURITY)
- Project branding and naming
- Organizational structure and decision-making processes

---

## Scope Boundaries

| Scope | Areas | Who Can Contribute |
|---|---|---|
| **Open** | Documentation, tests, plugins, examples | Everyone — community contributions welcome |
| **Closed** | Agent logic, orchestrator, scheduler, framework internals | Maintainers and approved contributors after Tier 2 review |
| **Proprietary** | Business logic, commercial integrations, deployment infrastructure | Internal team only — not open for external contributions |

---

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git

### Installation

1. Fork and clone the repository:

```bash
git clone https://github.com/<your-username>/crazy-pumpkin-os.git
cd crazy-pumpkin-os
```

2. Install the package in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

3. Run the test suite to verify your setup:

```bash
pytest
```

All tests should pass before you start making changes.

### Running Tests

```bash
# Run all tests with verbose output
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_agents.py -v

# Run tests matching a keyword
python -m pytest -k "test_config" -v
```

### Linting

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-format code
ruff format src/ tests/
```

### Type Checking

Run mypy to verify type annotations:

```bash
mypy src/crazypumpkin/ --ignore-missing-imports
```

---

## CI Pipeline

Every pull request triggers automated CI via **GitHub Actions**. The pipeline runs:

- **Tests** — `python -m pytest tests/ -v`
- **Linting** — `ruff check src/ tests/`
- **Formatting** — `ruff format --check src/ tests/`
- **Type checking** — `mypy src/crazypumpkin/ --ignore-missing-imports`

All checks must pass before a PR can be merged.

---

## Releasing

Releases follow a tag-based workflow:

1. Update the version in `pyproject.toml`.
2. Commit the version bump and merge to `main`.
3. Create a Git tag matching the version:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. Create a **GitHub Release** from the tag with release notes.
5. PyPI publishing is triggered automatically by the GitHub Release via CI.

---

## Submitting a Contribution

1. Create a branch for your change (`git checkout -b my-change`)
2. Make your changes, keeping commits focused and well-described
3. Ensure all tests pass (`pytest`)
4. Open a pull request against `main`
5. Fill in the PR template describing what changed and why

---

## Open Spec

This project uses the [Open Spec](https://github.com/open-spec/open-spec) specification format for design documents and specifications. When contributing specifications or architectural proposals, follow the Open Spec format. See the linked documentation for details.

## Code of Conduct

All contributors are expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE). See [LICENSE.md](LICENSE.md) for the full licensing model.
