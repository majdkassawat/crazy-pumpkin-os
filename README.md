# Crazy Pumpkin OS

**Autonomous AI Company Operating System** — install, configure, and run your own AI-powered software company.

Crazy Pumpkin OS is a multi-agent framework where AI agents collaborate to plan, develop, review, and ship software autonomously. You provide the goals, they do the work.

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

## Quick Start

```bash
pip install crazypumpkin
crazypumpkin init
crazypumpkin run
```

Open `http://localhost:8500` to see the dashboard.

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

## Status

**v0.1 (in development)** — Core pipeline with Strategist, Developer, Reviewer, Ops.

Built by [Crazy Pumpkin](https://github.com/majdkassawat/crazy-pumpkin-framework) — an autonomous AI company that builds itself.

## License

Apache-2.0
