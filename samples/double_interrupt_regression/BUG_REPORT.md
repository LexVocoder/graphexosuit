# Bug: `resume()` returns stale `checkpoint_id` when graph hits a second interrupt

## Summary

When a graph hits a **second** `interrupt()` during a `resume()` call,
`ExosuitCore.resume()` returns a `RunResult` whose `checkpoint_id` still points
to the **first** interrupt's checkpoint. Resuming from that stale `checkpoint_id`
re-executes from the first interrupt node instead of the second, causing an
infinite re-interruption loop.

## Root cause

`_extract_checkpoint_id` is called after `invoke()` completes, but it is passed
the **original** `config` that was used to start the invocation — which contains
the old `checkpoint_id`:

```python
# runtime.py
def _extract_checkpoint_id(graph: Any, config: RunnableConfig) -> str:
    state = graph.get_state(config)   # ← config still has old checkpoint_id
    return state.config["configurable"].get("checkpoint_id", "unknown")
```

When `get_state` receives a config with an explicit `checkpoint_id`, LangGraph
returns the state **at that specific checkpoint**, not the latest one. So the
returned `checkpoint_id` is the one that was passed in, not the one just created
by the new interrupt.

**Fix:** strip `checkpoint_id` from the config before calling `get_state`, so
LangGraph returns the latest state for the thread:

```python
def _extract_checkpoint_id(graph: Any, config: RunnableConfig) -> str:
    """Return the latest checkpoint ID from the graph state."""
    latest_config = {
        "configurable": {
            "thread_id": config["configurable"]["thread_id"],
        }
    }
    state = graph.get_state(latest_config)
    return state.config["configurable"].get("checkpoint_id", "unknown")
```

## Reproduction

A self-contained reproducer is in `checkpoint_bug_graph.py` in the
`llm-orchestration` repo. Run with:

```
uv run checkpoint_bug_graph.py
```

The graph has this structure:

```
node_setup → node_work → node_interrupt1 → node_more_work → node_interrupt2 → node_done
```

**Run 1** (initial): graph pauses at `node_interrupt1`. Returns `checkpoint_id = A`.

**Run 2** (resume from A): `node_interrupt1` resumes, graph continues to
`node_interrupt2` and pauses. Returns `checkpoint_id = A` (stale — should be B).

**Run 3** (resume from A again, since that's all we have): `node_interrupt1`
re-runs instead of `node_interrupt2` resuming. Graph never reaches `node_done`.

### Observed output

```
checkpoint_after_interrupt1 = 1f150634-1d3d-6571-8002-ee324bf8400b
checkpoint_after_interrupt2 = 1f150634-1d3d-6571-8002-ee324bf8400b   ← same!

❌ BUG CONFIRMED: r2.checkpoint_id == r1.checkpoint_id
```

## Affected code

`graphexosuit-core/graphexosuit/core/runtime.py`, function `_extract_checkpoint_id`.

The same function is called from both the interrupt path and the error path inside
`_invoke`, so the fix covers both cases.
