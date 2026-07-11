# graphexosuit

Core Python package for the Exosuit LangGraph runtime ecosystem.

`graphexosuit` wraps arbitrary [LangGraph](https://github.com/langchain-ai/langgraph) workflows and provides a standardised runtime interface for executing, pausing, resuming, and retrying graph-based applications.

## Installation

```bash
uv pip install graphexosuit
```

## Testing

Run automated tests using uv:

```bash
uv run pytest tests/
```

To run tests with verbose output:

```bash
uv run pytest tests/ -v
```

## Quick start

### 1. Create and compile your graph

```python
# my_project/workflows.py
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from graphexosuit.core import StandardizedInterrupt, InterruptOption
from langgraph.types import interrupt
from typing import TypedDict

class State(TypedDict):
    value: str

def approval_node(state):
    APPROVE_PAYLOAD="approve"
    response = interrupt(StandardizedInterrupt(
        message="Approve this action?",
        options=[
            InterruptOption(label="Approve", payload=APPROVE_PAYLOAD),
            InterruptOption(label="Reject",  payload="reject"),
        ]
    ))
    if response == APPROVE_PAYLOAD:
        return {"value": "approved"}
    return {"value": "rejected"}

def build_graph():
    """Return a compiled StateGraph."""
    builder = StateGraph(State)
    builder.add_node("approval", approval_node)
    builder.set_entry_point("approval")
    builder.set_finish_point("approval")
    return builder.compile(checkpointer=SqliteSaver.from_conn_string(...))
```
```

### 2. Use ExosuitCore directly

```python
from graphexosuit.core import ExosuitCore
from my_project.workflows import build_graph
from contextlib import contextmanager

# Wrap your checkpointer in a context manager
@contextmanager
def get_checkpointer_cm():
    from langgraph.checkpoint.sqlite import SqliteSaver
    yield SqliteSaver.from_conn_string(...)

core = ExosuitCore(graph=build_graph(), checkpointer_cm=get_checkpointer_cm())

# Run
result = core.run({"value": "start"}, thread_id="thread-1")

# If paused, resume
if result.paused:
    rv = { ... }
    result = core.resume(result.thread_id, result.checkpoint_id, rv)

print(result)
```

## Key types

| Type | Description |
|------|-------------|
| `ExosuitCore` | Main orchestrator: accepts graph, drives execution |
| `RunResult` | Outcome of any graph invocation |
| `StandardizedInterrupt` | Value passed to `interrupt()` by graph nodes |
| `InterruptOption` | A selectable choice within an interrupt |

## Graph developer contract

* `get_graph()` must return a `StateGraph` or a compiled `StateGraph`.
* `get_checkpointer_cm()` must return a context manager that yields a LangGraph checkpointer ("Saver").
* Interrupt with `interrupt(StandardizedInterrupt(...))`.
