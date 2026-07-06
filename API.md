# graphexosuit.core API Documentation

Complete reference for the public API of `graphexosuit.core`, the core runtime and execution layer for LangGraph-based stateful workflows with interrupt/resume capabilities.

## Table of Contents

- [Core Runtime Classes](#core-runtime-classes)
- [Data Models](#data-models)
- [Abstract Base Classes](#abstract-base-classes)
- [Exceptions](#exceptions)

---

## Core Runtime Classes

### `ExosuitCore`

Thin runtime wrapper around a LangGraph workflow that enables execution, pausing, resuming, and retrying of graph operations with checkpoint-based state management.

#### Constructor

```python
ExosuitCore(liner: Any)
```

**Parameters:**
- `liner` – A Liner-compatible instance that provides:
  - `get_graph() -> StateGraph | CompiledStateGraph` – Returns the workflow graph
  - `get_checkpointer_cm() -> Iterator[BaseCheckpointSaver]` – Returns a context manager for checkpoint persistence
  - Optional: `transform_initial_state(dict) -> dict` – Transform initial state before execution
  - Optional: `transform_resume_value(Any) -> Any` – Transform resume values before resuming
  - Optional: `transform_run_result(RunResult) -> RunResult` – Transform run results
  - Optional: `on_retry(thread_id: str, checkpoint_id: str) -> None` – Hook called before retry

**Raises:**
- `ValueError` – If checkpointer setup fails

**Example:**

```python
from graphexosuit.core import ExosuitCore, ExosuitLiner
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

class MyWorkflow(ExosuitLiner):
    def get_graph(self) -> StateGraph:
        graph = StateGraph({"value": int})
        # ... define graph nodes and edges
        return graph
    
    def get_checkpointer_cm(self):
        checkpointer = MemorySaver()
        return checkpointer

workflow = MyWorkflow()
core = ExosuitCore(workflow)
```

#### Methods

##### `run(initial_state: dict, thread_id: Optional[str] = None) -> RunResult`

Execute the graph from the beginning with fresh state.

**Parameters:**
- `initial_state` – Initial state dict passed to the graph. Passed through `transform_initial_state()` if available.
- `thread_id` – Optional identifier for this execution. A UUID is generated if omitted.

**Returns:**
- `RunResult` – The execution outcome, either an interrupt or final result.

**Raises:**
- `GraphExecutionError` – If the graph raises an exception during execution.

**Example:**

```python
result = core.run({"value": 42}, thread_id="session-1")
if result.interrupt_value:
    print(f"Paused: {result.interrupt_value.message}")
else:
    print(f"Completed: {result.final_result}")
```

##### `resume(thread_id: str, checkpoint_id: str, resume_value: Any) -> RunResult`

Resume a paused graph execution from a checkpoint.

**Parameters:**
- `thread_id` – Thread identifier of the paused execution.
- `checkpoint_id` – Checkpoint to resume from (from a prior interrupt).
- `resume_value` – The payload to send back to the paused node. Passed through `transform_resume_value()` if available. Typically a dict.

**Returns:**
- `RunResult` – The next execution outcome.

**Raises:**
- `GraphExecutionError` – If the graph raises an exception during execution.

**Example:**

```python
# After receiving an interrupt
if result.interrupt_value:
    # User selects option 0
    selected_option = result.interrupt_value.options[0]
    
    # Resume with the selected payload
    result = core.resume(
        thread_id=result.thread_id,
        checkpoint_id=result.checkpoint_id,
        resume_value=selected_option.payload
    )
```

##### `retry(thread_id: str, checkpoint_id: str) -> RunResult`

Retry a failed graph node from its last checkpoint.

**Parameters:**
- `thread_id` – Thread identifier of the failed execution.
- `checkpoint_id` – Checkpoint at which the failure occurred.

**Returns:**
- `RunResult` – The next execution outcome.

**Raises:**
- `GraphExecutionError` – If the graph raises an exception again, or if the liner's `on_retry()` hook fails.

**Example:**

```python
try:
    result = core.run({"value": 42})
except GraphExecutionError as exc:
    print(f"Execution failed at checkpoint {exc.get_checkpoint_id()}")
    # Retry from the checkpoint
    result = core.retry(
        thread_id=exc.get_thread_id(),
        checkpoint_id=exc.get_checkpoint_id()
    )
```

---

## Data Models

### `InterruptOption`

A selectable option presented to the user during a graph interrupt.

**Duck-typed:** any object with `label` and `payload` attributes works.

```python
@dataclass
class InterruptOption:
    label: str      # Human-readable label for the option
    payload: Any    # Data to send back if this option is selected
```

**Fields:**
- `label: str` – Human-readable display text for the option.
- `payload: Any` – Data structure sent back to the graph if selected (typically a dict or primitive value).

**Example:**

```python
from graphexosuit.core import InterruptOption

option_a = InterruptOption(
    label="Use default strategy",
    payload={"strategy": "default"}
)
option_b = InterruptOption(
    label="Use aggressive strategy",
    payload={"strategy": "aggressive"}
)
```

### `StandardizedInterrupt`

The interrupt value that graph nodes must pass to `interrupt()`.

**Duck-typed:** any object with `message` and `options` attributes works.

```python
@dataclass
class StandardizedInterrupt:
    message: str                    # Human-readable pause reason
    options: list[InterruptOption]  # Available resumption choices
```

**Fields:**
- `message: str` – Human-readable message explaining why execution paused (e.g., "User decision required").
- `options: list[InterruptOption]` – List of available options the user can select to resume.

**Example:**

```python
from graphexosuit.core import StandardizedInterrupt, InterruptOption

interrupt = StandardizedInterrupt(
    message="Choose a strategy to continue",
    options=[
        InterruptOption(label="Default", payload={"strategy": "default"}),
        InterruptOption(label="Aggressive", payload={"strategy": "aggressive"}),
        InterruptOption(label="Conservative", payload={"strategy": "conservative"}),
    ]
)
```

### `RunResult`

The outcome of a graph execution, pause, or error.

**Invariant:** Exactly one of `interrupt_value` or `final_result` is non-`None`. If `interrupt_value` is set, `checkpoint_id` must also be set.

```python
@dataclass
class RunResult:
    thread_id: str                                    # Execution thread identifier
    checkpoint_id: Optional[str] = None               # Checkpoint ID (set if interrupted)
    interrupt_value: Optional[StandardizedInterrupt] = None  # Interrupt data if paused
    final_result: Optional[dict] = None               # Final output if completed
```

**Fields:**
- `thread_id: str` – Unique identifier for this execution thread. Used to resume or retry.
- `checkpoint_id: Optional[str]` – Checkpoint identifier; set when interrupted, used for `resume()` and `retry()`.
- `interrupt_value: Optional[StandardizedInterrupt]` – The interrupt object if execution paused, otherwise `None`.
- `final_result: Optional[dict]` – Final output dict if execution completed, otherwise `None`.

**Example:**

```python
result = core.run({"value": 42})

if result.interrupt_value:
    print(f"Paused: {result.interrupt_value.message}")
    print(f"Options: {[o.label for o in result.interrupt_value.options]}")
    print(f"Resume with thread={result.thread_id}, checkpoint={result.checkpoint_id}")
else:
    print(f"Completed: {result.final_result}")
```

---

## Abstract Base Classes

### `ExosuitLiner`

Abstract base class defining the interface between `ExosuitCore` and a LangGraph workflow.

Implementers must provide a compiled or uncompiled LangGraph state graph and a checkpoint saver context manager.

```python
from abc import ABC, abstractmethod
from graphexosuit.core import ExosuitLiner
from langgraph.graph import StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from typing import Iterator

class MyLiner(ExosuitLiner):
    def get_graph(self) -> StateGraph:
        # Required: return your LangGraph StateGraph
        pass
    
    def get_checkpointer_cm(self) -> Iterator[BaseCheckpointSaver]:
        # Required: yield a BaseCheckpointSaver
        pass
```

#### Abstract Methods

##### `get_graph() -> StateGraph | CompiledStateGraph`

Return the LangGraph workflow graph.

**Returns:**
- A `StateGraph` or `CompiledStateGraph` instance. If `StateGraph`, `ExosuitCore` compiles it automatically.

**Example:**

```python
def get_graph(self) -> StateGraph:
    graph = StateGraph({"messages": list, "count": int})
    graph.add_node("process", self.process_node)
    graph.add_node("decide", self.decide_node)
    graph.add_edge("process", "decide")
    graph.set_entry_point("process")
    graph.set_finish_point("decide")
    return graph
```

##### `get_checkpointer_cm() -> Iterator[BaseCheckpointSaver]`

Yield a checkpoint saver instance as a context manager.

**Yields:**
- A `BaseCheckpointSaver` instance (e.g., `MemorySaver`, `SqliteSaver`, custom saver).

**Example:**

```python
from contextlib import contextmanager
from langgraph.checkpoint.sqlite import SqliteSaver

@contextmanager
def get_checkpointer_cm(self) -> Iterator[BaseCheckpointSaver]:
    return SqliteSaver.from_conn_string(":memory:")
```

#### Optional Hook Methods

##### `on_retry(thread_id: str, checkpoint_id: str) -> None`

Called before `retry()` resumes from a checkpoint. Override to perform side effects like logging or cleanup.

**Parameters:**
- `thread_id` – Thread identifier of the retry.
- `checkpoint_id` – Checkpoint being retried.

**Raises:**
- Any exception raised is wrapped in `GraphExecutionError`.

**Example:**

```python
def on_retry(self, thread_id: str, checkpoint_id: str) -> None:
    logger.info(f"Retrying thread {thread_id} from checkpoint {checkpoint_id}")
```

#### Optional Transformation Methods

##### `transform_initial_state(initial_state: dict) -> dict`

Transform the initial state dict before passing to the graph in `run()`.

**Parameters:**
- `initial_state` – The state dict provided to `run()`.

**Returns:**
- Transformed state dict.

**Default:** Returns `initial_state` unchanged.

**Example:**

```python
def transform_initial_state(self, initial_state: dict) -> dict:
    # Add computed fields or validation
    initial_state["timestamp"] = time.time()
    return initial_state
```

##### `transform_resume_value(resume_value: Any) -> Any`

Transform the resume value before passing to the graph in `resume()`.

**Parameters:**
- `resume_value` – The value provided to `resume()`.

**Returns:**
- Transformed value.

**Default:** Returns `resume_value` unchanged.

**Example:**

```python
def transform_resume_value(self, resume_value: Any) -> Any:
    # Validate or normalize the resume value
    if isinstance(resume_value, dict):
        resume_value["timestamp"] = time.time()
    return resume_value
```

##### `transform_run_result(result: RunResult) -> RunResult`

Transform the `RunResult` before returning from `run()`, `resume()`, or `retry()`.

**Parameters:**
- `result` – The `RunResult` produced by graph execution.

**Returns:**
- Transformed `RunResult`.

**Default:** Returns `result` unchanged.

**Example:**

```python
def transform_run_result(self, result: RunResult) -> RunResult:
    # Add metadata or filter sensitive fields
    return result
```

---

## Exceptions

### `GraphExecutionError`

Raised when the graph throws an exception during execution.

Wraps the original exception and provides thread and checkpoint context for recovery.

```python
class GraphExecutionError(Exception):
    def __init__(self,
                 message: str,
                 original_exception: Exception,
                 thread_id: str,
                 checkpoint_id: str) -> None:
        ...
```

**Parameters:**
- `message: str` – Descriptive message about the error (e.g., "Graph execution failed").
- `original_exception: Exception` – The original exception raised by the graph.
- `thread_id: str` – Thread identifier for recovery.
- `checkpoint_id: str` – Checkpoint identifier for recovery.

**Methods:**
- `get_thread_id() -> str` – Returns the thread identifier.
- `get_checkpoint_id() -> str` – Returns the checkpoint identifier.

**Example:**

```python
from graphexosuit.core import GraphExecutionError

try:
    result = core.run({"value": 42})
except GraphExecutionError as exc:
    print(f"Execution failed: {exc}")
    thread_id = exc.get_thread_id()
    checkpoint_id = exc.get_checkpoint_id()
    # Retry or log the error
    result = core.retry(thread_id, checkpoint_id)
```

### `InvalidInterruptError`

Raised when a graph node returns an interrupt value that does not satisfy the `StandardizedInterrupt` duck type.

An interrupt must have `message` and `options` attributes, and each option must have `label` and `payload` attributes.

```python
class InvalidInterruptError(ValueError):
    """Raised when an interrupt value does not satisfy the StandardizedInterrupt interface."""
```

**Example:**

```python
# This will raise InvalidInterruptError
invalid_interrupt = {"message": "Paused"}  # Missing 'options' attribute
```

### `GraphLoaderError`

Raised when a graph module cannot be loaded or is missing required functions.

```python
class GraphLoaderError(Exception):
    """Raised when the graph module cannot be loaded or is missing required functions."""
```

---

## Workflow Example

End-to-end example demonstrating interrupt/resume flow:

```python
from graphexosuit.core import (
    ExosuitCore, ExosuitLiner, StandardizedInterrupt, InterruptOption
)
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from contextlib import contextmanager

class MyWorkflow(ExosuitLiner):
    def get_graph(self) -> StateGraph:
        graph = StateGraph({"value": int, "strategy": str})
        
        def process_node(state):
            # Pause and ask for user input
            return state
        
        def decide_node(state):
            if state.get("strategy") == "default":
                state["value"] *= 2
            elif state.get("strategy") == "aggressive":
                state["value"] *= 10
            return state
        
        graph.add_node("process", process_node)
        graph.add_node("decide", decide_node)
        
        # Interrupt after process_node
        graph.add_edge("process", "decide")
        graph.set_entry_point("process")
        graph.set_finish_point("decide")
        
        return graph
    
    def get_checkpointer_cm(self):
        return MemorySaver()

# Execute
workflow = MyWorkflow()
core = ExosuitCore(workflow)

# Initial run
result = core.run({"value": 5})
print(f"Thread: {result.thread_id}")
print(f"Interrupt: {result.interrupt_value.message}")

# User selects an option
if result.interrupt_value:
    selected = result.interrupt_value.options[0]
    result = core.resume(
        thread_id=result.thread_id,
        checkpoint_id=result.checkpoint_id,
        resume_value=selected.payload,
    )
    print(f"Final result: {result.final_result}")
```
