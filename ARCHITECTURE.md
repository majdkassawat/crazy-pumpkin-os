# Architecture

Crazy Pumpkin OS is an autonomous AI company operating system built on a
multi-agent architecture. Thirteen specialized agents are organized into four
functional layers plus a shared service layer. Each agent has a single
responsibility and communicates through an event-driven pipeline that moves work
from high-level goals to merged pull requests.

---

## Layers and Agents

### Strategic Layer

Transforms business intent into actionable plans.

**Victor — CEO**
Victor is the founder-facing executive agent. He ingests company-level goals
from the goals inbox and GitHub issues, prioritizes the product backlog, and
decides which initiatives to pursue. Victor ensures that the company's
autonomous activity stays aligned with the founder's vision and can veto or
reprioritize work at any time.

**Luna — Product Manager**
Luna translates Victor's high-level directives into concrete product
requirements. She maintains the product roadmap, writes acceptance criteria for
each initiative, and coordinates cross-product priorities when the company
manages multiple repositories.

**Scout — Market Intelligence**
Scout gathers external context that informs strategic decisions. He monitors
competitor activity, community feedback, and market signals, then feeds
structured intelligence summaries to Victor and Luna so that product direction
reflects real-world conditions.

**Sage — Strategist**
Sage decomposes approved goals into developer-ready task trees. She analyzes
each goal, determines the technical approach, estimates scope, and produces an
ordered list of tasks with clear inputs and outputs that the execution layer can
pick up immediately.

### Execution Layer

Turns task specifications into working code.

**Nova — Developer**
Nova is a general-purpose software developer. She reads task specifications,
writes production code, creates tests, and iterates until the implementation
satisfies the acceptance criteria. Nova has full tool access: file read/write,
shell commands, and code search.

**Bolt — Developer**
Bolt is a second developer agent that operates in parallel with Nova. He has
the same capabilities and tool access, allowing the company to execute multiple
tasks concurrently and reduce pipeline latency.

**Atlas — Architect**
Atlas provides architecture oversight for the execution layer. He reviews
structural decisions, ensures new code fits the existing system design, and
handles infrastructure-level fixes that require cross-cutting changes across
multiple modules or configuration files.

### Review Layer

Guards quality before code reaches the main branch.

**Rex — Reviewer**
Rex performs code review on every completed task. He checks correctness,
adherence to project conventions, test coverage, and potential regressions.
Rex either approves the work for merging or returns it to the developer with
specific, actionable feedback.

**Triton — Triage**
Triton diagnoses failures that occur anywhere in the pipeline. When a task is
rejected, a test suite fails, or an agent produces invalid output, Triton
analyzes the root cause, classifies the failure, and routes a targeted fix-task
to the appropriate agent rather than blindly retrying.

### Operations Layer

Keeps the autonomous pipeline healthy.

**Pulse — Ops**
Pulse monitors the runtime health of the entire agent pipeline. He detects
stuck tasks, stalled agents, and resource anomalies, then triggers corrective
actions such as task reassignment or escalation to the founder.

**Darwin — Evolution**
Darwin analyzes historical performance data — success rates, failure patterns,
and cycle times — to propose structural improvements to the agent organization.
He can recommend adding, removing, or reconfiguring agents to improve the
company's overall throughput and quality.

### Service Layer

Shared infrastructure agents that other agents call as utilities.

**Octo — GitHub + Git**
Octo centralizes all version-control operations. He manages git branching,
commits, pull request creation, and GitHub API interactions so that no other
agent needs to invoke git or GitHub commands directly.

**Wing — Telegram**
Wing handles all outbound and inbound Telegram communication. He sends
notifications to the founder, relays status updates, and receives commands
through the Telegram bot interface.

---

## Goal-to-Merge Flow

The following diagram shows how work moves from a founder's goal to a merged
pull request, with service agents annotated at their interaction points.

```
 GOAL INPUT
 ══════════
 Founder writes a goal file          GitHub issue is opened
       │                                      │
       └──────────────┬───────────────────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Victor  (CEO)   │◄──── Scout (Market Intel)
            │  prioritizes     │        provides external context
            │  the backlog     │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  Luna  (PM)      │
            │  writes product  │
            │  requirements    │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  Sage (Strategy) │
            │  decomposes goal │
            │  into tasks      │
            └────────┬─────────┘
                     │
              ┌──────┴──────┐
              │             │
              ▼             ▼
      ┌──────────────┐ ┌──────────────┐
      │ Nova (Dev)   │ │ Bolt (Dev)   │    Atlas (Architect)
      │ implements   │ │ implements   │◄── reviews structure,
      │ task A       │ │ task B       │    handles infra fixes
      └──────┬───────┘ └──────┬───────┘
              │             │         │
              │  ┌──────────┘         │
              │  │   Octo (Git/GH) ◄──┘
              │  │   manages branches,
              │  │   commits, PRs
              ▼  ▼
      ┌──────────────────┐
      │  Rex (Reviewer)  │
      │  code review     │
      └──┬──────────┬────┘
         │          │
     approved    rejected
         │          │
         │          ▼
         │  ┌──────────────────┐
         │  │ Triton (Triage)  │
         │  │ diagnoses root   │──── routes fix-task back
         │  │ cause            │     to Nova, Bolt, or Atlas
         │  └──────────────────┘
         │
         ▼
 ┌────────────────┐     Octo (Git/GH)
 │  MERGED PR     │◄─── creates PR, merges
 └────────────────┘
         │
         │   Wing (Telegram) ──── notifies founder
         │
         ▼
 ┌────────────────────────────────────────────┐
 │  OPERATIONS (always running)               │
 │                                            │
 │  Pulse (Ops)     — monitors pipeline       │
 │  Darwin (Evol)   — optimizes organization  │
 └────────────────────────────────────────────┘
```

### Flow Summary

1. **Goal input** — The founder drops a goal file or opens a GitHub issue.
2. **Strategic planning** — Victor prioritizes, Luna refines requirements,
   Scout supplies market context, and Sage decomposes the goal into tasks.
3. **Parallel execution** — Nova and Bolt implement tasks concurrently while
   Atlas oversees architectural consistency.
4. **Version control** — Octo manages all git and GitHub operations on behalf
   of the execution agents.
5. **Review gate** — Rex reviews every completed task. Approved work proceeds
   to merge; rejected work is routed to Triton for triage.
6. **Triage loop** — Triton diagnoses failures and routes targeted fix-tasks
   back to the appropriate execution agent.
7. **Merge and notify** — Octo merges the approved PR and Wing notifies the
   founder via Telegram.
8. **Continuous operations** — Pulse monitors pipeline health and Darwin
   analyzes performance trends to evolve the organization over time.
