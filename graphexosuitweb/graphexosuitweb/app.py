"""FastAPI application for graphexosuit."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from graphexosuit import ExosuitCore, ResumeValue, load_liner

app = FastAPI(
    title="graphexosuitweb",
    description="HTTP interface for executing LangGraph workflows via graphexosuit.",
)

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


def _result_response(result) -> JSONResponse:
    content = json.loads(json.dumps(asdict(result), default=str))
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
                "thread_id, checkpoint_id, and resume_id in query parameters."
            )
        },
    )


@app.post("/resume")
async def resume_endpoint(
    thread_id: str,
    checkpoint_id: str,
    resume_id: str,
    payload: Optional[str] = None,
) -> JSONResponse:
    """Resume a paused graph execution."""
    payload_data: Optional[dict] = None
    if payload is not None:
        try:
            payload_data = json.loads(payload)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=422,
                content={"detail": "payload must be valid JSON"},
            )

    core = _get_core()
    resume_value = ResumeValue(id=resume_id, payload=payload_data)
    result = core.resume(thread_id, checkpoint_id, resume_value)
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
