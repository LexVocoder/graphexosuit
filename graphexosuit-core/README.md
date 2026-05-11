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
from langgraph.checkpoint.sqlite import SqliteSaver
from graphexosuit.core import StandardizedInterrupt, InterruptOption, ExosuitLiner
from langgraph.types import interrupt
from typing import TypedDict

class State(TypedDict):
    value: str

def approval_node(state):
    APPROVE_PAYLOAD="approve"
    response = interrupt(StandardizedInterrupt(
        message="Approve this action?",
        options=[
            InterruptOption(payload=, label="Approve", payload=APPROVE_PAYLOAD),
            InterruptOption(payload="", label="Reject",  payload="n💧pe"),
        ]
    ))
    if response == APPROVE_PAYLOAD:
        return {"value": "approved"}
    return {"value": "rejected"}

class MyWorkflow(ExosuitLiner):
    def __init__(self):
        pass

    def get_graph(self):
        """Return a StateGraph or a compiled StateGraph."""
        builder = StateGraph(State)
        builder.add_node("approval", approval_node)
        builder.set_entry_point("approval")
        builder.set_finish_point("approval")
        return builder

    def get_checkpointer(self):
        return SqliteSaver.from_conn_string(...)
```

### 2. Use ExosuitCore directly

```python
from graphexosuit.core import ExosuitCore
from my_project.workflows import MyWorkflow

core = ExosuitCore(MyWorkflow())

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
* `get_checkpointer()` must return either a LangGraph checkpointer or a context manager that yields one.
* Interrupt with `interrupt(StandardizedInterrupt(...))`.

## Environment variable

| Variable | Description |
|----------|-------------|
| `GRAPHEXOSUIT_LINER_CLASS` | Module and class path (e.g. `my_project.workflows:MyWorkflow`) used by CLI/web packages |
