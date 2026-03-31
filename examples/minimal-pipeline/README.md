# Minimal 2-Agent Pipeline Example

This example demonstrates the simplest possible Crazy Pumpkin OS configuration with just two agents:

1. **Strategist** - Decomposes high-level product goals into ordered developer tasks
2. **Developer** - Executes tasks and generates code artifacts

## When to Use This Configuration

- Learning how Crazy Pumpkin OS works
- Prototyping a new product idea
- Projects that don't need code review
- Quick experimentation and iteration

## Agent Roles

### Strategist (Strategy Agent)

The Strategist takes high-level product goals and breaks them down into actionable tasks. It:

- Analyzes goal descriptions
- Creates ordered task lists with dependencies
- Assigns priority levels to each task
- Defines acceptance criteria

**Role**: `strategy`  
**Class**: `crazypumpkin.agents.strategy_agent.StrategyAgent`

### Developer (Code Generator Agent)

The Developer receives task specifications and generates code artifacts. It:

- Reads task descriptions and acceptance criteria
- Generates source files based on requirements
- Writes files to the product workspace

**Role**: `execution`  
**Class**: `crazypumpkin.agents.code_generator.CodeGeneratorAgent`

## Quick Start

### 1. Set Up Environment

```bash
# Clone the repository
git clone https://github.com/majdkassawat/crazy-pumpkin-os.git
cd crazy-pumpkin-os

# Install the package
pip install -e .
```

### 2. Configure API Key

```bash
# Set your Anthropic API key (or use OpenAI)
export ANTHROPIC_API_KEY=your-api-key-here
```

### 3. Create Your Project

```bash
# Copy this example configuration
cp -r examples/minimal-pipeline my-project
cd my-project

# Create the demo app workspace
mkdir -p demo-app/src demo-app/tests
```

### 4. Run the Pipeline

```bash
# Start the pipeline
crazypumpkin run

# Or run a single cycle
crazypumpkin run --once
```

## Running Individual Agents

You can run any agent from the minimal pipeline on-demand using `cpos run-agent`.
This is useful for testing, debugging, or one-off executions without starting the
full pipeline loop.

### Run the Developer (code-generator) agent

```bash
cpos run-agent Developer --config examples/minimal-pipeline/config.yaml
```

### Run the Strategist agent

```bash
cpos run-agent Strategist --config examples/minimal-pipeline/config.yaml
```

### Pass parameters for a one-off execution

Use `--param` to inject key=value pairs into the agent context:

```bash
cpos run-agent Developer --config examples/minimal-pipeline/config.yaml \
  --param model=opus --param verbose=true
```

You can also set a timeout to limit execution time:

```bash
cpos run-agent Developer --config examples/minimal-pipeline/config.yaml \
  --timeout 120
```

### Expected output

A successful run prints a summary like this:

```
Running agent 'Developer' ...

Agent: Developer
Status: success
Duration: 1.23s
Output: Hello, working on: On-demand run: Developer
Artifacts: result.txt
```

## Configuration Breakdown

### Company Section

```yaml
company:
  name: "Minimal Demo Company"
```

A simple identifier for your AI company.

### Products Section

```yaml
products:
  - name: "Demo App"
    workspace: "./demo-app"
    source_dir: "src"
    test_dir: "tests"
```

Defines the product that agents will work on.

### Agents Section

```yaml
agents:
  - name: "Strategist"
    role: strategy
    class: crazypumpkin.agents.strategy_agent.StrategyAgent
    
  - name: "Developer"
    role: execution
    class: crazypumpkin.agents.code_generator.CodeGeneratorAgent
```

The two agents that form this minimal pipeline.

### Pipeline Section

```yaml
pipeline:
  cycle_interval: 30       # seconds between cycles
  task_timeout_sec: 3600   # max time for a single task
```

Controls how often the pipeline runs and task timeouts.

## How It Works

1. **Add a Goal**: Place a YAML file in `goals/` describing what you want built
2. **Strategist Plans**: The strategist reads the goal and creates developer tasks
3. **Developer Executes**: The developer picks up tasks and generates code
4. **Repeat**: The cycle continues until all goals are completed

## Adding Goals

Create a file in the `goals/` directory:

```yaml
# goals/my-feature.yaml
title: "Add user authentication"
description: |
  Implement user authentication with email/password login.
  Include:
  - User registration
  - Login/logout functionality
  - Password hashing
  - Session management
```

## Expanding Beyond 2 Agents

As your needs grow, consider adding:

- **Reviewer** (`crazypumpkin.agents.reviewer_agent.ReviewerAgent`) - Reviews code quality
- **Architect** - Designs fixes for rejected tasks
- **Ops** - Monitors and manages pipeline health

See `examples/config.yaml` for a full configuration example.

## Next Steps

- Read the [Getting Started Guide](../../GETTING_STARTED.md)
- Explore the [Architecture Documentation](../../ARCHITECTURE.md)
- Join the community and contribute!