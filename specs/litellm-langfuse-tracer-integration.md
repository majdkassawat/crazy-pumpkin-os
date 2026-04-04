# Spec: Integrate LangfuseTracer into LiteLLMProvider cost recording

**Status:** Implemented
**Files changed:** `src/crazypumpkin/llm/litellm_provider.py`, `src/crazypumpkin/observability/cost.py`, `src/crazypumpkin/observability/tracing.py`
**Tests:** `tests/test_litellm_cost_integration.py`

---

## Summary

Every LLM call made through `LiteLLMProvider` must be traced to Langfuse (when a tracer is configured) by flowing cost data through `observability.cost.CostTracker.record()`, which internally calls `LangfuseTracer.trace_llm_call()`.

## Architecture

```
LiteLLMProvider._record_cost_from_response(model, response, agent_name)
  -> CostTracker.record(agent_name, model, prompt_tokens, completion_tokens, cost_usd, product)
       -> get_tracer()  [returns LangfuseTracer | None]
       -> tracer.trace_llm_call(
              agent_name=agent_name,
              model=model,
              prompt_tokens=prompt_tokens,
              completion_tokens=completion_tokens,
              cost_usd=cost_usd,
              product=product,          # default: "crazy-pumpkin-os"
          )
```

## File-by-file specification

### 1. `src/crazypumpkin/observability/tracing.py`

**Class:** `LangfuseTracer`

```python
class LangfuseTracer:
    def __init__(self, client: Any) -> None:
        self._client = client

    def trace_llm_call(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        product: str = "crazy-pumpkin-os",
    ) -> None:
        """Send a single LLM call trace to Langfuse."""
        self._client.generation(
            name=f"{product}/{agent_name}",
            model=model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            metadata={"cost_usd": cost_usd, "product": product},
        )
```

**Module-level helpers:**

| Function | Signature | Purpose |
|---|---|---|
| `configure_tracer` | `(client: Any) -> LangfuseTracer` | Set the global `_tracer` singleton |
| `get_tracer` | `() -> Optional[LangfuseTracer]` | Return global tracer or `None` |
| `reset_tracer` | `() -> None` | Clear the global tracer (for tests) |

### 2. `src/crazypumpkin/observability/cost.py`

**Class:** `CostTracker`

**Method `record()`** — after appending the `CostRecord` and updating spend aggregates, call the tracer:

```python
def record(
    self,
    agent_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    product: str = "crazy-pumpkin-os",
) -> CostRecord:
    rec = CostRecord(
        agent_name=agent_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        product=product,
    )
    self._records.append(rec)
    self._product_spend[product] += cost_usd
    self._agent_spend[agent_name] += cost_usd
    self._product_agent_spend[product][agent_name] += cost_usd

    tracer = get_tracer()
    if tracer is not None:
        tracer.trace_llm_call(
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            product=product,
        )
        self._synced_count = len(self._records)

    return rec
```

**Method `export_to_langfuse()`** — batch-sends any records that were created while the tracer was `None`:

```python
def export_to_langfuse(self) -> int:
    tracer = get_tracer()
    if tracer is None:
        return 0
    unsynced = self._records[self._synced_count:]
    for rec in unsynced:
        tracer.trace_llm_call(
            agent_name=rec.agent_name,
            model=rec.model,
            prompt_tokens=rec.prompt_tokens,
            completion_tokens=rec.completion_tokens,
            cost_usd=rec.cost_usd,
            product=rec.product,
        )
    count = len(unsynced)
    self._synced_count = len(self._records)
    return count
```

### 3. `src/crazypumpkin/llm/litellm_provider.py`

**Method `_record_cost_from_response()`** — extracts usage from the LiteLLM response and delegates to `CostTracker.record()`:

```python
def _record_cost_from_response(
    self,
    model: str,
    response: object,
    agent_name: str = "unknown",
) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    try:
        cost_usd = litellm.completion_cost(completion_response=response)
    except Exception:
        cost_usd = 0.0
    tracker = self.cost_tracker or get_cost_tracker()
    tracker.record(
        agent_name=agent_name,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
```

Called from `call()`, `call_json()`, and `call_multi_turn()` with `agent_name` derived from the `agent` or `agent_name` parameter.

## Acceptance criteria

1. **`LangfuseTracer.trace_llm_call()` receives all six parameters.** The call includes `agent_name`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, and `product`. The `product` parameter defaults to `"crazy-pumpkin-os"`.

2. **Tracing is conditional.** When no tracer is configured (`get_tracer()` returns `None`), no tracing call is made and no error is raised.

3. **Tracing happens inside `CostTracker.record()`.** The Langfuse call is made as part of cost recording, not in the LLM provider directly. This keeps the provider decoupled from the tracing subsystem.

4. **Batch export covers gaps.** `CostTracker.export_to_langfuse()` sends records that were created before a tracer was configured. After export, `_synced_count` equals `len(self._records)`.

5. **Agent name flows end-to-end.** The `agent` or `agent_name` parameter from `LiteLLMProvider.call()` / `call_json()` / `call_multi_turn()` is passed through `_record_cost_from_response()` to `CostTracker.record()` to `tracer.trace_llm_call()`. Default is `"unknown"`.

6. **No usage = no record.** If the LiteLLM response has `usage=None`, neither cost recording nor tracing occurs.

7. **Cost fallback on error.** If `litellm.completion_cost()` raises, `cost_usd` defaults to `0.0` and the record (including trace) still proceeds.

8. **All 16 tests in `tests/test_litellm_cost_integration.py` pass.**
