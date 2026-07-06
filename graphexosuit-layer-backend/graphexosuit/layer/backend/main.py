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
import io
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
    execution data including status, result, error, and captured stdout/stderr.

    Thread execution data is stored in execution_data_store under namespace (thread_id, "__graphexosuit__")
    with fields: stdout_lines, stderr_lines, status, result, error, created_at.
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
    
    # ## Helper functions for thread execution data management
    
    def _store_dict(namespace: str, data: dict[str, Any]) -> None:
        """Store all key-value pairs from a dictionary in the execution_data_store.
        
        Prefixes each key with the namespace and a "." before storing.
        
        Args:
            namespace: The namespace prefix for all keys.
            data: Dictionary of key-value pairs to store.
        """
        prefixed_data = {f"{namespace}.{key}": value for key, value in data.items()}
        execution_data_store.mset(list(prefixed_data.items()))
    
    def _load_dict(namespace: str, keys: list[str]) -> dict[str, Any]:
        """Load a dictionary from the execution_data_store for the given keys.
        
        Prefixes each key with the namespace and a "." before retrieving.
        
        Args:
            namespace: The namespace prefix for all keys.
            keys: List of keys (without namespace prefix) to retrieve from the store.
            
        Returns:
            Dictionary mapping each unprefixed key to its value in the store.
        """
        prefixed_keys = [f"{namespace}.{key}" for key in keys]
        values_list = execution_data_store.mget(prefixed_keys)
        return dict(zip(keys, values_list)) if values_list else {}
    
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
        existing_data = _load_dict(thread_id, ["created_at"])
        if existing_data.get("created_at") is not None:
            # Already initialized; preserve the existing created_at
            return
        
        # Initialize new execution data with current timestamp
        initial_data = {
            "stdout_lines": [],
            "stderr_lines": [],
            "status": "running",
            "result": None,
            "error": None,
            "created_at": now_iso,
        }
        _store_dict(thread_id, initial_data)
    
    def _get_thread_execution_data(thread_id: str) -> dict[str, Any]:
        """Retrieve thread execution data for a thread.
        
        Returns an empty execution data dict if the thread has not been initialized.
        
        Args:
            thread_id: The thread identifier to retrieve execution data for.
            
        Returns:
            The execution data dict with keys: stdout_lines, stderr_lines, status,
            result, error, created_at. Returns empty dict if not found.
        """
        keys = [
            "stdout_lines",
            "stderr_lines",
            "status",
            "result",
            "error",
            "created_at",
        ]
        loaded_data = _load_dict(thread_id, keys)
        
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

        Redirects sys.stdout and sys.stderr during execution so that any text
        printed by graph nodes is captured and appended to the thread's persisted
        stdout_lines / stderr_lines execution data fields. On success, stores the full
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
        namespace = (thread_id, "__graphexosuit__")

        # ## Capture stdout/stderr produced during graph execution
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        # execution_result and execution_error are mutually exclusive outcomes
        execution_result: RunResult | None = None
        execution_error: GraphExecutionError | ThreadNotFound | None = None

        try:
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
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
            execution_error = graph_error
        except ThreadNotFound as thread_not_found:
            execution_error = thread_not_found

        # ## Append captured lines to persisted execution data (always, even on error)
        captured_stdout_lines = stdout_buffer.getvalue().splitlines()
        captured_stderr_lines = stderr_buffer.getvalue().splitlines()

        execution_data = _get_thread_execution_data(thread_id)
        updated_stdout_lines = (execution_data.get("stdout_lines") or []) + captured_stdout_lines
        updated_stderr_lines = (execution_data.get("stderr_lines") or []) + captured_stderr_lines

        # Prepare updates dict with all fields to persist
        updates: dict[str, Any] = {
            "stdout_lines": updated_stdout_lines,
            "stderr_lines": updated_stderr_lines,
        }

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
        _store_dict(thread_id, updates)
    
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
        stdout_lines, stderr_lines, and created_at. Returns 404 if the thread
        does not exist.
        
        Returns:
            200 OK: {thread_id, status, result, error, stdout_lines, stderr_lines, created_at}
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
                "thread_id": thread_id,
                "created_at": execution_data.get("created_at"),
                "status": execution_data.get("status"),
                "error": execution_data.get("error"),
                "result": execution_data.get("result"),
                "stdout_lines": execution_data.get("stdout_lines", []),
                "stderr_lines": execution_data.get("stderr_lines", []),
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

