# Agent Contributor Onboarding

Welcome, AI agent! Crazy Pumpkin OS accepts contributions from both human and AI contributors. This guide explains how AI agents can contribute effectively.

## Supported Agents

Any AI coding agent can contribute, including:
- Claude (Anthropic) — via Claude Code, API, or Agent SDK
- GPT (OpenAI) — via ChatGPT, Codex, or API
- Other coding agents — as long as they can produce valid PRs

## Contribution Workflow

The workflow is identical to human contributors:

1. **Fork** the repository
2. **Clone** your fork locally
3. **Create a branch** for your changes
4. **Make changes** — use Edit/Write tools, not text descriptions
5. **Run tests** — `python -m pytest tests/ -v --tb=short`
6. **Commit** with a clear message
7. **Push** and open a Pull Request
8. **Follow the PR template** checklist

## What's Open for Agents

- Bug fixes (see issues labeled `bug`)
- Documentation improvements (labeled `documentation`)
- Test coverage (labeled `good-first-issue`)
- Plugin development (see [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) when available)

## Prompt Templates

Use these structured prompts for common contribution types:

| Task | Prompt File |
|------|-------------|
| Bug fixes | [PROMPTS_BUG_FIX.md](PROMPTS_BUG_FIX.md) |
| Documentation | [PROMPTS_DOCUMENTATION.md](PROMPTS_DOCUMENTATION.md) |
| Plugin development | [PROMPTS_PLUGIN_DEVELOPMENT.md](PROMPTS_PLUGIN_DEVELOPMENT.md) |
| First contribution | [PROMPTS_FIRST_CONTRIBUTION.md](PROMPTS_FIRST_CONTRIBUTION.md) |

## Self-Testing Before Submission

Before opening a PR, verify:

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run the full test suite
python -m pytest tests/ -v --tb=short

# Verify import works
python -c "import crazypumpkin; print('OK')"
```

All tests must pass. PRs with failing tests will be rejected.

## Guidelines

- Read [CONTRIBUTING.md](CONTRIBUTING.md) for scope boundaries and approval tiers
- Keep changes minimal and focused — one logical change per PR
- Include tests for new functionality
- Do not modify core agent logic without discussion (Tier 2)
- Agree to MIT licensing via the PR template checkbox
