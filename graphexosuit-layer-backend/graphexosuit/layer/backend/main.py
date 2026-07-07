"""graphexosuit.layer.backend.main - Async FastAPI application factory for graphexosuit.

Responsibilities:
  - Expose ``create_app(liner, execution_data_store)`` factory that wires a Liner and BaseStore
    into an async FastAPI app with background workers and polling-based result retrieval.
  - Define four REST endpoints: POST /run, GET /thread/{thread_id},
    POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume,
    POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry.
  - Spawn background worker threads to execute graph operations asynchronously.
  - Capture stdout/stderr from background graph executions and persist to execution data store.
  - Handle GraphExecutionError and ThreadNotFound in background workers; surface via execution data.
  - Provide polling interface (GET /thread/{thread_id}) for clients to retrieve results and status.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from langchain_core.stores import BaseStore
from urllib.parse import quote

from graphexosuit.core import (
    ExosuitCore,
    GraphExecutionError,
    RunResult,
    ThreadNotFound,
)
from graphexosuit.core.liner_validator import validate_liner
from graphexosuit.layer.backend.batch_key_value_store import BatchKeyValueStore
from graphexosuit.layer.backend.streaming_text_capture import StreamingTextCapture

# ## Module-level logger
# Thread-safe by default in CPython; format includes timestamp and level for
# easy filtering in production log aggregators.
logger = logging.getLogger(__name__)








def create_app(liner: Any, execution_data_store: BaseStore) -> FastAPI:
    """Create and return a FastAPI application for graphexosuit-layer-restservice.

    Instantiates ExosuitCore with the provided Liner and creates a FastAPI app
    with four endpoints that manage async graph execution via background worker threads.
    All POST endpoints spawn background workers and return 202 immediately with
    thread_id and poll_url. The GET /thread/{thread_id} endpoint returns thread
    execution data including status, result, error, and captured output (stdout/stderr combined).

    Thread execution data is stored in execution_data_store under namespace (thread_id, "__graphexosuit__")
    with fields: output_lines, status, result, error, created_at.
    The created_at timestamp is initialized when execution data is first created and
    is never reset.

    Args:
        liner: A Liner instance providing get_graph() and get_checkpointer_cm().
        execution_data_store: A langchain_core.stores.BaseStore for persisting thread execution data.

    Returns:
        A configured FastAPI application with four endpoints:
        - POST /run: Start a new graph execution
        - GET /thread/{thread_id}: Poll execution status and results
        - POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume: Resume paused execution
        - POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry: Retry failed execution

    Raises:
        ValueError: If *liner* is None or missing required interface methods.
    """
    # Validate the liner before instantiating ExosuitCore
    validate_liner(liner)

    # ## Instantiate ExosuitCore with the Liner
    core = ExosuitCore(liner)
    
    # ## Create FastAPI app
    fastapi_app = FastAPI(
        title="graphexosuit REST service",
        description="Async REST API for LangGraph graph execution via graphexosuit.core.",
    )
    
    # ## Initialize the batch key-value store for thread execution data
    execution_batch_store = BatchKeyValueStore(execution_data_store)
    
    def _build_poll_url(thread_id: str) -> str:
        """Build a poll URL from a thread ID with proper URI encoding.
        
        Args:
            thread_id: The thread identifier to encode in the URL.
            
        Returns:
            A poll URL string with properly encoded thread_id.
        """
        return f"/thread/{quote(thread_id, safe='')}"
    
    def _init_thread_execution_data(thread_id: str) -> None:
        """Initialize thread execution data for a thread if it doesn't already exist (idempotent).
        
        Sets up the initial execution data structure with empty stdout/stderr, status
        "running", and created_at timestamp. If execution data already exists, this is
        a no-op to preserve the original created_at value.
        
        Args:
            thread_id: The thread identifier to initialize execution data for.
        """
        now_iso = datetime.now(timezone.utc).isoformat() + "Z"

        # Try to retrieve existing created_at to check if already initialized
        existing_data = execution_batch_store.get(thread_id, ["created_at"])
        if existing_data.get("created_at") is not None:
            # Already initialized; preserve the existing created_at
            return
        
        # Initialize new execution data with current timestamp
        initial_data = {
            "output_lines": [],
            "status": "running",
            "result": None,
            "error": None,
            "created_at": now_iso,
        }
        execution_batch_store.put(thread_id, initial_data)
    
    def _get_thread_execution_data(thread_id: str) -> dict[str, Any]:
        """Retrieve thread execution data for a thread.
        
        Returns an empty execution data dict if the thread has not been initialized.
        
        Args:
            thread_id: The thread identifier to retrieve execution data for.
            
        Returns:
            The execution data dict with keys: output_lines, status,
            result, error, created_at. Returns empty dict if not found.
        """
        keys = [
            "output_lines",
            "status",
            "result",
            "error",
            "created_at",
        ]
        loaded_data = execution_batch_store.get(thread_id, keys)
        
        # If no keys were found, return empty dict
        if not loaded_data or all(v is None for v in loaded_data.values()):
            return {}
        
        # Assemble dict from retrieved values
        return loaded_data
    
    
    def _capture_and_run_worker(
        thread_id: str,
        operation: Literal["run", "resume", "retry"],
        initial_state: Any | None = None,
        checkpoint_id: str | None = None,
        resume_value: Any | None = None,
    ) -> None:
        """Background worker function that executes a graph operation and updates execution data.

        Streams sys.stdout and sys.stderr during execution line-by-line so that any text
        printed by graph nodes is persisted immediately to the thread's execution data,
        providing real-time heartbeat updates to polling clients. On success, stores the full
        RunResult as a dict and sets status to "paused" (interrupt) or "completed".
        On GraphExecutionError or ThreadNotFound, stores the error dict and sets
        status to "error".

        Args:
            thread_id: The thread identifier for this execution.
            operation: One of "run", "resume", or "retry".
            initial_state: Required for "run" operation; the initial state dict.
            checkpoint_id: Required for "resume" and "retry"; the checkpoint ID.
            resume_value: Required for "resume"; the value to resume with.
        """
        # ## Create streaming capture objects for stdout/stderr
        # Both stdout and stderr stream to the same output_lines field for unified visibility
        stdout_capture = StreamingTextCapture(thread_id, "output_lines", execution_batch_store.get, execution_batch_store.put)
        stderr_capture = StreamingTextCapture(thread_id, "output_lines", execution_batch_store.get, execution_batch_store.put)

        # execution_result and execution_error are mutually exclusive outcomes
        execution_result: RunResult | None = None
        execution_error: GraphExecutionError | ThreadNotFound | None = None

        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                if operation == "run":
                    execution_result = core.run(initial_state or {}, thread_id=thread_id)
                elif checkpoint_id is None:
                    raise ValueError(f"checkpoint_id is required for {operation!r} operation")
                elif operation == "resume":
                    execution_result = core.resume(thread_id, checkpoint_id, resume_value)
                elif operation == "retry":
                    execution_result = core.retry(thread_id, checkpoint_id)
                else:
                    # Guard against programming errors; operation is validated at call sites
                    raise ValueError(
                        f"Unknown operation: {operation!r}; expected 'run', 'resume', or 'retry'"
                    )

        except GraphExecutionError as graph_error:
            # Log stack trace and error details for debugging; surface only message in execution data
            logger.exception(
                "GraphExecutionError in %s operation for thread %s: %s",
                repr(operation),
                repr(thread_id),
                graph_error,
                exc_info=graph_error,
            )
            execution_error = graph_error

        except ThreadNotFound as thread_not_found:
            execution_error = thread_not_found

        except Exception as exn:
            logger.exception("Unexpected exception in %s operation for thread %s: %s", repr(operation), repr(thread_id), exn, exc_info=exn)

        # ## Flush any remaining buffered output lines from the capture streams
        stdout_capture.close()
        stderr_capture.close()

        # Prepare updates dict with status and result/error information
        updates: dict[str, Any] = {}

        if isinstance(execution_error, GraphExecutionError):
            updates["status"] = "error"
            updates["error"] = {
                "message": str(execution_error),
                "checkpoint_id": execution_error.get_checkpoint_id(),
                "thread_id": execution_error.get_thread_id(),
            }
        elif isinstance(execution_error, ThreadNotFound):
            # ThreadNotFound means the core cannot locate the thread or checkpoint;
            # surface this as an "error" status so the caller can react via polling.
            updates["status"] = "error"
            updates["error"] = {
                "message": str(execution_error),
                "checkpoint_id": execution_error.checkpoint_id,
                "thread_id": execution_error.thread_id,
            }
        elif execution_result is not None:
            updates["status"] = "paused" if execution_result.interrupt_value is not None else "completed"
            updates["result"] = asdict(execution_result)

        # Persist all updates as individual keys
        execution_batch_store.put(thread_id, updates)
    
    # ## Define the four endpoints
    
    @fastapi_app.post("/run")
    async def run_endpoint(
        body: dict = Body(...),
    ) -> JSONResponse:
        """POST /run endpoint: Start a new graph execution.
        
        Accepts a JSON body with 'initial_state' key and spawns a background worker
        thread to execute the graph. Returns 202 (Accepted) with thread_id and
        poll_url immediately.
        
        Returns:
            202 Accepted: {thread_id, poll_url}
        """
        initial_state = body.get("initial_state")
        thread_id = str(uuid.uuid4())
        
        # Initialize execution data for this thread
        _init_thread_execution_data(thread_id)
        
        # Spawn background worker thread
        worker_thread = threading.Thread(
            target=_capture_and_run_worker,
            kwargs={
                "thread_id": thread_id,
                "operation": "run",
                "initial_state": initial_state,
            },
            daemon=True,
        )
        worker_thread.start()
        
        poll_url = _build_poll_url(thread_id)
        
        return JSONResponse(
            status_code=202,
            content={
                "thread_id": thread_id,
                "poll_url": poll_url,
            },
        )
    
    @fastapi_app.get("/thread/{thread_id}")
    async def get_thread_endpoint(thread_id: str) -> JSONResponse:
        """GET /thread/{thread_id} endpoint: Poll execution status and results.
        
        Returns execution data for the specified thread including status, result, error,
        output_lines, and created_at. Returns 404 if the thread does not exist.
        
        Returns:
            200 OK: {thread_id, status, result, error, output_lines, created_at}
            404 Not Found: If thread does not exist
        """
        execution_data = _get_thread_execution_data(thread_id)
        
        if not execution_data:
            # Thread not found
            return JSONResponse(
                status_code=404,
                content={"error": f"Thread {thread_id!r} not found"},
            )
        
        return JSONResponse(
            status_code=200,
            content={
                "created_at": execution_data.get("created_at"),
                "status": execution_data.get("status"),
                "error": execution_data.get("error"),
                "result": execution_data.get("result"),
                "output_lines": execution_data.get("output_lines", []),
            },
        )
    
    @fastapi_app.post("/thread/{thread_id}/checkpoint/{checkpoint_id}/resume")
    async def resume_endpoint(
        thread_id: str,
        checkpoint_id: str,
        resume_value: Any = Body(...),
    ) -> JSONResponse:
        """POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume endpoint.
        
        Resume a paused graph execution from the specified checkpoint with the
        provided resume_value. Spawns a background worker thread and returns
        202 (Accepted) immediately with thread_id and poll_url.
        
        Returns:
            202 Accepted: {thread_id, poll_url}
            404 Not Found: If thread or checkpoint does not exist
        """
        execution_data = _get_thread_execution_data(thread_id)
        
        if not execution_data:
            # Thread not found
            return JSONResponse(
                status_code=404,
                content={"error": f"Thread {thread_id!r} not found"},
            )
        
        # Spawn background worker thread for resume
        worker_thread = threading.Thread(
            target=_capture_and_run_worker,
            kwargs={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "operation": "resume",
                "resume_value": resume_value,
            },
            daemon=True,
        )
        worker_thread.start()
        
        poll_url = _build_poll_url(thread_id)
        
        return JSONResponse(
            status_code=202,
            content={
                "thread_id": thread_id,
                "poll_url": poll_url,
            },
        )
    
    @fastapi_app.post("/thread/{thread_id}/checkpoint/{checkpoint_id}/retry")
    async def retry_endpoint(
        thread_id: str,
        checkpoint_id: str,
    ) -> JSONResponse:
        """POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry endpoint.
        
        Retry a failed graph node from its last checkpoint. Spawns a background
        worker thread and returns 202 (Accepted) immediately with thread_id and
        poll_url.
        
        Returns:
            202 Accepted: {thread_id, poll_url}
            404 Not Found: If thread or checkpoint does not exist
        """
        execution_data = _get_thread_execution_data(thread_id)
        
        if not execution_data:
            # Thread not found
            return JSONResponse(
                status_code=404,
                content={"error": f"Thread {thread_id!r} not found"},
            )
        
        # Spawn background worker thread for retry
        worker_thread = threading.Thread(
            target=_capture_and_run_worker,
            kwargs={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "operation": "retry",
            },
            daemon=True,
        )
        worker_thread.start()
        
        poll_url = _build_poll_url(thread_id)
        
        return JSONResponse(
            status_code=202,
            content={
                "thread_id": thread_id,
                "poll_url": poll_url,
            },
        )

    return fastapi_app

