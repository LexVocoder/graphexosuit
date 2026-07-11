# graphexosuit-layer-backend

FastAPI backend for [graphexosuit](https://github.com/graphexosuit/graphexosuit) LangGraph workflows.

## Overview

`graphexosuit-layer-backend` exposes a production-ready REST API around `graphexosuit.core`.
Clients inject a compiled LangGraph and checkpointer context manager at construction time; the backend handles parameter
parsing, serialization, error mapping, and logging.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run` | Start a new graph execution |
| `GET` | `/thread/{thread_id}` | Poll execution status and results |
| `POST` | `/thread/{thread_id}/checkpoint/{checkpoint_id}/resume` | Resume a paused execution |
| `POST` | `/thread/{thread_id}/checkpoint/{checkpoint_id}/retry` | Retry a failed graph node |

All endpoints use a **polling model** with background workers. POST endpoints return `202 Accepted` immediately with a thread ID and poll URL.

## Quick Start

```python
from my_app.workflows import build_graph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.stores import InMemoryStore
from graphexosuit.layer.backend import create_app
from contextlib import contextmanager
import uvicorn

@contextmanager
def get_checkpointer_cm():
    yield MemorySaver()

graph = build_graph()
execution_data_store = InMemoryStore()
app = create_app(graph=graph, checkpointer_cm=get_checkpointer_cm(), execution_data_store=execution_data_store)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## API Reference

### `POST /run`

Start a new graph execution. Returns immediately with a thread ID that can be polled for results.

**Request body (JSON):**

```json
{
  "initial_state": { "key": "value", "..." : "..." }
}
```

**Response (202 Accepted):**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "poll_url": "/thread/550e8400-e29b-41d4-a716-446655440000"
}
```

### `GET /thread/{thread_id}`

Poll execution status and retrieve results. Returns execution data for the specified thread including status, result, error, and captured output.

**Response (200 OK):**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "final_state": { "document": "...", "status": "approved" },
    "interrupt_value": null
  },
  "error": null,
  "stdout_lines": ["Processing document...", "..."],
  "stderr_lines": [],
  "created_at": "2026-07-06T12:34:56.789Z"
}
```

**Status values:**
- `"running"` – Execution is ongoing
- `"completed"` – Execution finished successfully without interrupts
- `"paused"` – Execution paused at an interrupt node
- `"error"` – Execution failed with an error

**Response (404 Not Found):** If thread does not exist
```json
{
  "error": "Thread '550e8400-e29b-41d4-a716-446655440000' not found"
}
```

### `POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume`

Resume a paused graph execution from the specified checkpoint. Returns immediately; poll the `/thread/{thread_id}` endpoint to check results.

**Request body (JSON):**

The resume value to forward to the paused node (shape depends on the workflow):
```json
{
  "strategy": "default"
}
```

**Response (202 Accepted):**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "poll_url": "/thread/550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (404 Not Found):** If thread does not exist

### `POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry`

Retry a failed graph node from its last checkpoint. Returns immediately; poll the `/thread/{thread_id}` endpoint to check results.

**Response (202 Accepted):**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "poll_url": "/thread/550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (404 Not Found):** If thread or checkpoint does not exist

## Error Responses

| HTTP Status | Cause |
|-------------|-------|
| `404` | Thread or checkpoint not found |
| `422` | FastAPI parameter validation failure |

When a graph execution encounters an error, it is stored in the thread execution data. Retrieve it via `GET /thread/{thread_id}` and inspect the `error` and `status` fields.

## Code Structure

```
graphexosuit-layer-backend/
├── pyproject.toml
├── README.md
├── graphexosuit/
│   └── layer/
│       └── backend/
│           ├── __init__.py          # Re-exports create_app
│           ├── main.py              # FastAPI app factory and endpoints
│           ├── transformers.py      # RunResult → JSON dict
│           ├── error_responses.py   # Error response builders
│           └── requirements.txt     # Runtime dependencies
└── tests/
    └── test_backend.py
```

## Installation

```bash
pip install graphexosuit-layer-backend
# or with uv:
uv add graphexosuit-layer-backend
```

Install runtime server:

```bash
pip install uvicorn
```
