# Spec: Add trace_span and shutdown methods to LangfuseTracer

**Status:** Ready for development
**File to modify:** `src/crazypumpkin/observability/tracing.py`
**Test file to create:** `tests/test_tracer_span_shutdown.py`

---

## Summary

Add two methods to `LangfuseTracer`: `trace_span()` for recording arbitrary named spans (non-LLM operations like tool calls, retrieval steps, or agent orchestration phases), and `shutdown()` for flushing pending traces and cleanly closing the Langfuse client connection.

## File-by-file specification

### 1. `src/crazypumpkin/observability/tracing.py`

**Class:** `LangfuseTracer`

Add the following two methods after the existing `trace_llm_call()` method:

#### Method: `trace_span`

```python
def trace_span(
    self,
    name: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    input_data: Optional[Any] = None,
    output_data: Optional[Any] = None,
) -> None:
    """Record a named span (non-LLM operation) in Langfuse.

    Use this for tracing tool calls, retrieval steps, agent
    orchestration phases, or any operation that is not a direct
    LLM generation.

    Args:
        name: Identifier for the span (e.g. ``"retrieval/fetch_docs"``).
        metadata: Arbitrary key-value pairs attached to the span.
        input_data: The input payload of the operation (any JSON-serialisable value).
        output_data: The output/result of the operation (any JSON-serialisable value).
    """
    self._client.trace(
        name=name,
        metadata=metadata or {},
        input=input_data,
        output=output_data,
    )
```

**Behaviour:**
- Calls `self._client.trace()` with the four keyword arguments shown above.
- When `metadata` is `None`, passes an empty dict `{}` to `self._client.trace()`.
- `input_data` and `output_data` are forwarded as-is (may be `None`).
- Does not return any value.

#### Method: `shutdown`

```python
def shutdown(self) -> None:
    """Flush pending traces and shut down the Langfuse client.

    Call this during application teardown to ensure all buffered
    traces are sent before the process exits. After calling
    ``shutdown()``, the tracer should not be used for further
    tracing calls.
    """
    self._client.flush()
    self._client.shutdown()
```

**Behaviour:**
- Calls `self._client.flush()` first to send all buffered/pending traces.
- Then calls `self._client.shutdown()` to release resources and close the connection.
- Does not return any value.
- After `shutdown()` the tracer instance is considered unusable for further calls.

### 2. `src/crazypumpkin/observability/__init__.py`

No changes required. `LangfuseTracer` is already exported; the new methods are instance methods and need no additional exports.

### 3. `tests/test_tracer_span_shutdown.py` (new file)

Create a test file with the following test cases using `unittest.mock.MagicMock` for the Langfuse client:

| Test function | What it verifies |
|---|---|
| `test_trace_span_all_params` | `trace_span("op", metadata={"k": "v"}, input_data={"q": "hi"}, output_data={"a": "bye"})` calls `client.trace(name="op", metadata={"k": "v"}, input={"q": "hi"}, output={"a": "bye"})` exactly once. |
| `test_trace_span_defaults` | `trace_span("op")` calls `client.trace(name="op", metadata={}, input=None, output=None)` — verifies `None` metadata becomes `{}`. |
| `test_trace_span_metadata_none_becomes_empty_dict` | Explicit `trace_span("op", metadata=None)` passes `metadata={}` to client. |
| `test_shutdown_calls_flush_then_shutdown` | `shutdown()` calls `client.flush()` then `client.shutdown()` in that order. Use `mock.call_args_list` or `mock.assert_has_calls` to verify ordering. |
| `test_shutdown_flush_called_before_shutdown` | Verify `client.flush` is called before `client.shutdown` (ordering matters — use `unittest.mock.call` ordering). |

## Acceptance criteria

1. **`LangfuseTracer.trace_span()` has the exact signature shown above.** All parameters after `name` are keyword-only (enforced by `*`). Types: `name: str`, `metadata: Optional[dict[str, Any]]`, `input_data: Optional[Any]`, `output_data: Optional[Any]`. Return type: `None`.

2. **`trace_span()` calls `self._client.trace()` with correct parameter mapping.** `name` maps to `name`, `metadata` maps to `metadata` (defaulting `None` to `{}`), `input_data` maps to `input`, `output_data` maps to `output`.

3. **`LangfuseTracer.shutdown()` has the exact signature `(self) -> None`.** No parameters beyond `self`.

4. **`shutdown()` calls `self._client.flush()` then `self._client.shutdown()` in that order.** Both calls must happen; flush must precede shutdown.

5. **Both methods have docstrings** as specified above.

6. **All existing tests continue to pass.** The new methods are additive; no existing method signatures or behaviour change.

7. **All new tests in `tests/test_tracer_span_shutdown.py` pass** when run with `python -m pytest tests/test_tracer_span_shutdown.py -v`.

## Non-goals

- This spec does not add `trace_span` calls to any existing code paths (e.g., agent lifecycle, tool execution). That is a separate task.
- This spec does not wire `shutdown()` into application teardown hooks. That is a separate task.
- No changes to `CostTracker` or `LiteLLMProvider`.
