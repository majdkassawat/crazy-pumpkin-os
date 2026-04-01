# Spec: Add Agentic Tool-Use Loop to DeveloperAgent.execute

## Status: Implemented

## Overview

Replace the single `client.messages.create()` call in `DeveloperAgent.execute()` with an agentic loop that processes `tool_use` content blocks, executes tool requests, and feeds `tool_result` messages back to the model until it signals `end_turn` or a maximum iteration count is reached.

## Target File

`src/crazypumpkin/agents/developer_agent.py` — class `DeveloperAgent`, method `execute()`

## Current Behavior (Before)

The base class `ClaudeSDKAgent.execute()` in `src/crazypumpkin/framework/agent.py` makes a single `client.messages.create()` call. It passes tool definitions via `_build_tools()` but never inspects `response.stop_reason` for `"tool_use"` and never sends `tool_result` messages back. If the model requests a tool call, those blocks are silently ignored.

## Required Behavior (After)

### 1. Agentic Loop Structure

`DeveloperAgent.execute()` must wrap the `client.messages.create()` call in a loop that:

- Iterates up to `max_iterations = 10` times.
- On each iteration, calls `client.messages.create(**create_kwargs)`.
- Collects all text blocks from `response.content` into `all_content_parts: list[str]`.
- Appends the full assistant message (with `response.content` as-is) to `self._history`.
- Checks `response.stop_reason`:
  - If **not** `"tool_use"` → break out of the loop (model is done).
  - If `"tool_use"` → process tool-use blocks (step 2), then continue the loop.

### 2. Processing tool_use Blocks

For each block in `response.content` where `block.type == "tool_use"`:

- Extract `block.input` as `tool_input`.
- Read `command = tool_input.get("command", "")` and `file_path = tool_input.get("file_path", "")`.
- **Path-traversal guard**: If `file_path` is non-empty, resolve it to an absolute path (joining with `repo_root` if relative). Verify the resolved path starts with the normalized `repo_root`. If it does not:
  - Append a `tool_result` with `is_error: True` and message `"Error: path '<file_path>' is outside the repository root."`.
  - Skip to the next block (do **not** record an artifact).
- **Artifact recording**: If `command` is one of `"write"`, `"create"`, `"str_replace"`, `"insert"` AND `file_path` is non-empty, add `file_path` to the `artifacts` dict with value `"created/modified"`.
- Append a successful `tool_result` with `content: "OK"`.

### 3. tool_result Message Format

Each tool result is a dict with these keys:

```python
{
    "type": "tool_result",
    "tool_use_id": block.id,    # from the tool_use block
    "content": "OK",            # or error message string
    "is_error": True,           # only present on errors
}
```

All tool results for one iteration are collected into a list and appended to `self._history` as:

```python
{"role": "user", "content": tool_results}
```

Then `create_kwargs["messages"]` is updated to `list(self._history)` before the next iteration.

### 4. User Message Format

The user message must include `repo_root` from context:

```python
repo_root: str = context.get("repo_root", ".")
```

The prompt must contain:
- `"Repository root: {repo_root}"`
- Task title, description, and acceptance criteria
- Instructions to list changed files in a JSON block: `{"files_changed": ["path/to/file.py"]}`

### 5. Fallback Artifact Extraction

After the loop completes, if `artifacts` is empty (no tool_use blocks produced write operations), fall back to `_extract_artifacts(content)` which parses the `files_changed` JSON block from the model's text output using regex.

### 6. max_tokens

Set `max_tokens` to `16384` (increased from base class default of `4096`) to give the model room for multi-turn tool use.

## Acceptance Criteria

1. **Loop iterates on tool_use**: When `response.stop_reason == "tool_use"`, the method processes tool blocks and calls `client.messages.create()` again with tool results appended.
2. **Loop terminates on end_turn**: When `response.stop_reason != "tool_use"`, the loop breaks.
3. **Loop terminates at max_iterations**: After 10 iterations, the loop exits regardless of stop_reason.
4. **Path traversal blocked**: A `tool_use` block with `file_path` outside `repo_root` produces an error `tool_result` and is NOT added to `artifacts`.
5. **Write artifacts recorded**: `tool_use` blocks with `command` in `{write, create, str_replace, insert}` add the file_path to `artifacts`.
6. **Fallback regex extraction**: If no tool-use artifacts were recorded, `_extract_artifacts()` parses a `files_changed` JSON block from the text content.
7. **History preserved**: After execution, `self._history` contains the user message, all assistant turns, and all tool_result turns.
8. **Returns TaskOutput**: The method returns `TaskOutput(content=..., artifacts=...)`.

## Test File

`tests/test_developer_agent_loop.py` — must cover:

- `test_execute_with_tool_use_produces_artifacts`: Two API calls (tool_use → end_turn), artifact recorded, `call_count == 2`.
- `test_execute_no_tool_use_falls_back_to_regex`: Single API call with `files_changed` JSON, artifacts via regex.
- `test_execute_no_artifacts_returns_empty`: Plain text response, empty artifacts dict.
- `test_execute_path_traversal_blocked`: File path outside repo_root → `is_error: True`, not in artifacts.

## Non-Goals

- Actually executing file I/O (read/write) on disk — tool results return `"OK"` without performing real operations. Real tool execution is a separate concern.
- Bash tool execution — `bash` permission remains `False`.
- Streaming responses — not in scope.
