# graphexosuitweb

FastAPI web service for [graphexosuit](../graphexosuit) — execute, pause, resume, and retry LangGraph workflows over HTTP.

## Installation

```bash
pip install graphexosuitweb
```

## Configuration

```bash
export LANGGRAPH_GRAPH_MODULE=my_project.workflows
```

## Running the server

```bash
uvicorn graphexosuitweb.app:app --host 0.0.0.0 --port 8000
```

## Endpoints

### `POST /run`

```json
{ "input": { "value": "start" }, "thread_id": "optional-id" }
```

### `POST /resume`

Query parameters: `thread_id`, `checkpoint_id`, `resume_id`, `payload` (optional JSON string).

### `POST /retry`

Query parameters: `thread_id`, `checkpoint_id`.

All endpoints return a `RunResult` JSON object.  GET requests to `/resume` and `/retry` return HTTP 405.
