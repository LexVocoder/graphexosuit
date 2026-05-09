# graphexosuit-layer-backend

FastAPI web service for [graphexosuit-core](../graphexosuit-core) — execute, resume, and retry LangGraph workflows over HTTP.

## Installation

```bash
pip install graphexosuit-layer-backend
```

## Configuration

```bash
export GRAPHEXOSUIT_LINER_CLASS=my_project.workflows:MyLiner
```

## Running the server

```bash
graphexosuitweb
# or alternatively:
uvicorn graphexosuit.layer.backend.app:app --host 0.0.0.0 --port 8000
```

## Endpoints

### `POST /run`

Query parameters: `initial_state` (required JSON string), `thread_id` (optional).

### `POST /resume`

Query parameters: `thread_id` (required), `checkpoint_id` (required), `resume_value` (required JSON string).

### `POST /retry`

Query parameters: `thread_id` (required), `checkpoint_id` (required).

All endpoints return a `RunResult` JSON object. GET requests to `/resume` and `/retry` return HTTP 405, because they are not guaranteed to be idempotent.
