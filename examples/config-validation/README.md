# Config Validation Tutorial

This tutorial walks you through validating a Crazy Pumpkin OS configuration file and using environment variable overrides.

## Prerequisites

- Python 3.11+
- Crazy Pumpkin OS installed (`pip install -e .` from the repo root)

## Part 1: Validate a Config File

### Step 1: Create a config file

Create a `config.yaml` in your project directory:

```yaml
company:
  name: "My AI Company"

agents:
  - name: "developer"
    role: execution
    description: "Writes code"
  - name: "reviewer"
    role: reviewer
    description: "Reviews code"

dashboard:
  port: 8500
  host: "127.0.0.1"

pipeline:
  cycle_interval: 30
```

### Step 2: Run `cpos doctor` to verify

```bash
cpos doctor
```

Expected output:

```
  [PASS] Python 3.11 >= 3.11
  ...
  [PASS] config schema valid
  Env overrides: none active
All checks passed.
```

### Step 3: Introduce an error

Edit `config.yaml` and remove the required `agents` section:

```yaml
company:
  name: "My AI Company"

dashboard:
  port: 8500
```

### Step 4: Run `cpos doctor` again

```bash
cpos doctor
```

Expected output now includes:

```
  [FAIL] config schema invalid: Required field 'agents' is missing
```

### Step 5: Fix it

Restore the `agents` section:

```yaml
company:
  name: "My AI Company"

agents:
  - name: "developer"
    role: execution
```

Run `cpos doctor` — it should pass again.

### Step 6: Try a typo

Add a misspelled field:

```yaml
dashboard:
  prot: 8500
```

Run `cpos doctor`. The validator will warn:

```
WARNING at dashboard.prot: Unknown field 'prot'. Did you mean 'port'?
```

## Part 2: Environment Variable Overrides

### Step 1: Set an environment variable

Override the dashboard port via an env var:

```bash
# Linux/macOS
export CPOS_DASHBOARD__PORT=9000

# Windows (PowerShell)
$env:CPOS_DASHBOARD__PORT = "9000"

# Windows (cmd)
set CPOS_DASHBOARD__PORT=9000
```

### Step 2: Verify with `cpos doctor`

```bash
cpos doctor
```

The output will show the active override:

```
  Env overrides: CPOS_DASHBOARD__PORT=9000 -> dashboard.port
```

### Step 3: Override a nested value

```bash
export CPOS_LLM__DEFAULT_PROVIDER=openai
```

This sets `config["llm"]["default_provider"]` to `"openai"`.

### Step 4: Override a boolean

```bash
export CPOS_VOICE__ENABLED=true
```

The value is automatically coerced to `True` (Python bool) because the existing field type is `bool`.

### Step 5: List all active overrides programmatically

```python
from crazypumpkin.config.env_override import list_active_overrides

config = {"dashboard": {"port": 8500}, "voice": {"enabled": False}}
overrides = list_active_overrides(config)
for env_var, config_path, value in overrides:
    print(f"{env_var} -> {config_path} = {value!r}")
```

### Step 6: Clean up

Unset the env vars when done:

```bash
# Linux/macOS
unset CPOS_DASHBOARD__PORT
unset CPOS_LLM__DEFAULT_PROVIDER
unset CPOS_VOICE__ENABLED

# Windows (PowerShell)
Remove-Item Env:CPOS_DASHBOARD__PORT
```

## Part 3: Run the Demo Script

A runnable demo script is included in this directory:

```bash
python examples/config-validation/demo.py
```

This script loads a sample config, validates it, applies env overrides, and prints the results. See `demo.py` for the full source code.

## Further Reading

- [Config Validation Reference](../../docs/CONFIG_VALIDATION.md) — full schema table, coercion rules, and extension guide.
- Run `cpos init` to generate a starter config file.
- Run `cpos doctor` at any time to check your setup.
