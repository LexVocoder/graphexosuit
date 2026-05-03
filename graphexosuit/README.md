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

### 1. Create your graph module

```python
# my_project/workflows.py
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from graphexosuit import StandardizedInterrupt, InterruptOption
from langgraph.types import interrupt
from typing import TypedDict

class State(TypedDict):
    value: str

def approval_node(state):
    response = interrupt(StandardizedInterrupt(
        message="Approve this action?",
        options=[
            InterruptOption(id="approve", label="Approve", payload=None),
            InterruptOption(id="reject",  label="Reject",  payload=None),
        ]
    ))
    if response.id == "approve":
        return {"value": "approved"}
    return {"value": "rejected"}

def get_graph():
    """Return an *uncompiled* StateGraph — Exosuit compiles it."""
    builder = StateGraph(State)
    builder.add_node("approval", approval_node)
    builder.set_entry_point("approval")
    builder.set_finish_point("approval")
    return builder

def get_checkpointer():
    return MemorySaver()
```

### 2. Use ExosuitCore directly

```python
from graphexosuit import ExosuitCore, ResumeValue
from my_project.workflows import get_graph, get_checkpointer

core = ExosuitCore(get_graph(), get_checkpointer())

# Run
result = core.run({"value": "start"}, thread_id="thread-1")

# If paused, resume
if result.paused:
    rv = ResumeValue(id="approve", payload=None)
    result = core.resume(result.thread_id, result.checkpoint_id, rv)

print(result)
```

## Key types

| Type | Description |
|------|-------------|
| `ExosuitCore` | Main orchestrator: accepts uncompiled graph, compiles it, drives execution |
| `RunResult` | Outcome of any graph invocation |
| `StandardizedInterrupt` | Value passed to `interrupt()` by graph nodes |
| `InterruptOption` | A selectable choice within an interrupt |
| `ResumeValue` | The selected option sent back when resuming |

## Graph developer contract

* `get_graph()` must return an **uncompiled** `StateGraph` — Exosuit calls `.compile()`.
* `get_checkpointer()` must return a LangGraph checkpointer.
* Interrupt with `interrupt(StandardizedInterrupt(...))`.
* The return value of `interrupt()` is a `ResumeValue` (duck-typed).

## Environment variable

| Variable | Description |
|----------|-------------|
| `LANGGRAPH_GRAPH_MODULE` | Dotted module path (e.g. `my_project.workflows`) used by CLI/web packages |
