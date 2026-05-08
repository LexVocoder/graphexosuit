"""FastAPI application for graphexosuit."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from graphexosuit import ExosuitCore, load_liner
from graphexosuit.core import RunResult

# --------------------------------------------------------------------------
# Lazily initialise the ExosuitCore from the environment variable.
# This is done once on first request to allow the module to be imported
# without GRAPHEXOSUIT_LINER_CLASS being set (e.g., during testing).
# --------------------------------------------------------------------------

_core: Optional[ExosuitCore] = None


def _get_core() -> ExosuitCore:
    global _core
    if _core is None:
        liner = load_liner()
        _core = ExosuitCore(liner)
    return _core


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    # Startup
    yield
    # Shutdown
    global _core
    if _core is not None:
        _core.close()


app = FastAPI(
    title="graphexosuitweb",
    description="HTTP interface for executing LangGraph workflows via graphexosuit.",
    lifespan=lifespan,
)


def _result_response(result: RunResult) -> JSONResponse:
    content = asdict(result)
    if (result.interrupt_value is not None):
        # Format resume values as URLs
        interrupt_prime = {}
        interrupt_prime["message"] = result.interrupt_value.message
        interrupt_prime["options"] = []
        for option in result.interrupt_value.options:
            params = {
                'thread_id': result.thread_id,
                'checkpoint_id': result.checkpoint_id,
                'resume_value': json.dumps(option.payload),
            }

            url = f"/resume?{urlencode(params)}"

            interrupt_prime["options"].append({
                "label": option.label,
                "url": url,
            })

        content["interrupt_value"] = interrupt_prime

    if (result.error_message is not None):
        # Format retry URL
        params = {
            'thread_id': result.thread_id,
            'checkpoint_id': result.checkpoint_id,
        }
        url = f"/retry?{urlencode(params)}"
        content["retry_url"] = url

    return JSONResponse(content=content)


# --------------------------------------------------------------------------
# Request / response models
# --------------------------------------------------------------------------

class RunRequest(BaseModel):
    input: dict
    thread_id: Optional[str] = None


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.post("/run")
async def run_endpoint(body: RunRequest) -> JSONResponse:
    """Execute the graph from the beginning."""
    core = _get_core()
    result = core.run(body.input, thread_id=body.thread_id)
    return _result_response(result)


@app.api_route("/resume", methods=["GET"])
async def resume_get() -> JSONResponse:
    return JSONResponse(
        status_code=405,
        content={
            "detail": (
                "Resume requires POST. Use POST /resume with "
                "thread_id, checkpoint_id, and resume_value in query parameters."
            )
        },
    )


@app.post("/resume")
async def resume_endpoint(
    thread_id: str,
    checkpoint_id: str,
    resume_value: str,
) -> JSONResponse:
    """Resume a paused graph execution."""
    try:
        resume_value_parsed = json.loads(resume_value)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=422,
            content={"detail": "resume_value must be valid JSON"},
        )

    core = _get_core()
    result = core.resume(thread_id, checkpoint_id, resume_value_parsed)
    return _result_response(result)


@app.api_route("/retry", methods=["GET"])
async def retry_get() -> JSONResponse:
    return JSONResponse(
        status_code=405,
        content={
            "detail": (
                "Retry requires POST. Use POST /retry with "
                "thread_id and checkpoint_id in query parameters."
            )
        },
    )


@app.post("/retry")
async def retry_endpoint(thread_id: str, checkpoint_id: str) -> JSONResponse:
    """Retry the failed node of a graph execution."""
    core = _get_core()
    result = core.retry(thread_id, checkpoint_id)
    return _result_response(result)
