# Crazy Pumpkin OS

**Autonomous AI Company Operating System** — install, configure, and run your own AI-powered software company.

Crazy Pumpkin OS is a multi-agent framework where AI agents collaborate to plan, develop, review, and ship software autonomously. You provide the goals, they do the work.

> **⚠️ Alpha — Not Production-Tested**
>
> Crazy Pumpkin OS is in early development (v0.1). The codebase has **not been tested
> in production environments** and should be treated as experimental. APIs, configuration
> formats, and agent behaviors may change without notice between releases.
>
> We publish it openly so the community can explore, contribute, and help shape the
> direction — but **do not rely on it for critical workloads yet**.

## What it does

Drop a goal file like:
```
Add user authentication
Build email/password login with JWT tokens and a registration page
```

The company takes over:
1. **Strategist** breaks the goal into concrete tasks
2. **Developer** writes the code (with full tool access: read, edit, write, grep, bash)
3. **Reviewer** checks quality and correctness
4. **Ops** monitors for stuck tasks and failures
5. All work is tracked in a live web dashboard

## Quickstart

Get up and running in under 5 minutes.

### 1. Install

```bash
pip install crazypumpkin
```

### 2. Set your API key

Crazy Pumpkin OS needs an LLM provider. Set one of these environment variables:

```bash
# Anthropic (default)
export ANTHROPIC_API_KEY="sk-ant-..."

# Or OpenAI
export OPENAI_API_KEY="sk-..."
```

On Windows, use `set` instead of `export`.

### 3. Initialize your AI company

```bash
cp init
```

This launches an interactive wizard that creates your project directory with a `config.yaml`, `.env`, and a `goals/` inbox. See [`examples/default.json`](examples/default.json) for a sample configuration.

### 4. Run the pipeline

```bash
cp run
```

The agents will pick up any goals in the `goals/` directory and begin working. Expected output:

```
[Strategist] Breaking goal into tasks...
[Developer]  Executing task 1/3 — writing code...
[Reviewer]   Reviewing changes...
[Ops]        Pipeline cycle complete.
```

### 5. Open the dashboard

Open `http://localhost:8500` in your browser to see the live org chart, agent timeline, and project tracking.

## Architecture

```
Founder (you)
  │
  ├─ Goals inbox (goals/*.goal files)
  ├─ Voice chat (real-time conversation with the company)
  ├─ Telegram / Slack / Discord notifications
  │
  ▼
┌─────────────────────────────────────┐
│  STRATEGIC LAYER                    │
│  CEO · Product Manager · Evolution  │
│  Market Intel · Strategist          │
├─────────────────────────────────────┤
│  EXECUTION LAYER                    │
│  Developer · Architect              │
├─────────────────────────────────────┤
│  REVIEW LAYER                       │
│  Reviewer · Governance              │
├─────────────────────────────────────┤
│  OPERATIONS LAYER                   │
│  Ops · Triage · Framework Doctor    │
└─────────────────────────────────────┘
```

## Features

- **Multi-agent collaboration** — 13 specialized agents with distinct roles
- **Self-evolution** — the Evolution agent can restructure the organization autonomously
- **Self-healing** — Triage diagnoses failures, Architect designs fixes, Ops detects stuck tasks
- **Multi-product** — manage multiple repos/products from a single company
- **Live dashboard** — real-time org chart, agent timeline, project tracking
- **Voice interface** — talk to your company in real-time (OpenAI Realtime API)
- **Pluggable LLM providers** — Anthropic, OpenAI, Ollama (local models)
- **Pluggable notifications** — Telegram, Slack, Discord, webhooks
- **Config-driven** — YAML configuration, no code changes needed
- **Cross-platform** — Windows, macOS, Linux

## Contributing

We welcome contributions from both humans and AI agents!

- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines and approval tiers
- [FIRST_CONTRIBUTION.md](FIRST_CONTRIBUTION.md) — Step-by-step first PR walkthrough
- [AGENT_ONBOARDING.md](AGENT_ONBOARDING.md) — Guide for AI agent contributors
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture overview
- [API_DOCS.md](API_DOCS.md) — API reference
- [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) — Build and submit plugins
- [ROADMAP.md](ROADMAP.md) — Public roadmap
- [Good first issues](https://github.com/majdkassawat/crazy-pumpkin-os/labels/good-first-issue) — Start here

## Community

- [GitHub Discussions](https://github.com/majdkassawat/crazy-pumpkin-os/discussions) — Questions, ideas, RFCs
- [Project Board](https://github.com/users/majdkassawat/projects/3) — Track progress
- [Security Policy](SECURITY.md) — Report vulnerabilities privately
- [Code of Conduct](CODE_OF_CONDUCT.md) — Community standards

## Status

**v0.1 — Alpha (in development, untested in production)**

Core pipeline with Strategist, Developer, Reviewer, and Ops agents is functional but has not been validated in real-world production use. Expect breaking changes, incomplete features, and rough edges. Contributions and bug reports are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

Built by [Crazy Pumpkin](https://github.com/majdkassawat) — an autonomous AI company that builds itself.

## License

[MIT](LICENSE) — See [LICENSE.md](LICENSE.md) for details on the split licensing model.
