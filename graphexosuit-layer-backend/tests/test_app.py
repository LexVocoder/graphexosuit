"""Tests for graphexosuitweb FastAPI endpoints."""

from __future__ import annotations

import json
import sys
import types as _types
from typing import Any, TypedDict

import pytest
from httpx import AsyncClient, ASGITransport

from graphexosuit.core import ExosuitLiner


# ---------------------------------------------------------------------------
# Fixture: minimal in-process graph module with Liner-compatible class
# ---------------------------------------------------------------------------

class _State(TypedDict):
    value: str


# Separate fail counters per thread scenario
_fail_call_count: dict[str, int] = {}


def _get_graph(checkpointer: Any):
    from langgraph.graph import StateGraph
    from langgraph.types import interrupt
    from graphexosuit.core import StandardizedInterrupt, InterruptOption

    builder = StateGraph(_State)

    def node(state):
        value = state["value"]
        if value == "interrupt_me":
            val = interrupt(
                StandardizedInterrupt(
                    message="Choose",
                    options=[InterruptOption(label="OK", payload={})],
                )
            )
            return {"value": "resumed"}
        if value == "fail_me":
            _fail_call_count[value] = _fail_call_count.get(value, 0) + 1
            if _fail_call_count[value] == 1:
                raise RuntimeError("deliberate failure")
        return {"value": value + "_done"}

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder.compile(checkpointer=checkpointer)


from langgraph.checkpoint.memory import MemorySaver as _MemorySaver
_shared_checkpointer = _MemorySaver()


class _CheckpointerContextManager:
    """Simple context manager wrapper for a checkpointer."""
    def __init__(self, checkpointer):
        self._checkpointer = checkpointer
    
    def __enter__(self):
        return self._checkpointer
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # No cleanup needed for MemorySaver


def _get_checkpointer():
    return _shared_checkpointer


class _TestLiner(ExosuitLiner):
    """Liner-compatible class for testing."""

    def get_graph(self) -> Any:
        return _get_graph(self.get_checkpointer_cm().__enter__())

    def get_checkpointer_cm(self) -> Any:
        return _CheckpointerContextManager(_get_checkpointer())


_FAKE_MODULE = "fake_web_graph_module"
_fake_mod = _types.ModuleType(_FAKE_MODULE)
setattr(_fake_mod, "_TestLiner", _TestLiner)
sys.modules[_FAKE_MODULE] = _fake_mod


# ---------------------------------------------------------------------------
# App fixture: reset global _core between tests
# ---------------------------------------------------------------------------

import os
import graphexosuit.layer.backend.app as _web_app_module


@pytest.fixture(autouse=True)
def reset_core(monkeypatch):
    """Ensure a fresh ExosuitCore per test by resetting the module-level singleton."""
    monkeypatch.setenv("GRAPHEXOSUIT_LINER_CLASS", f"{_FAKE_MODULE}:_TestLiner")
    _web_app_module._core = None
    yield
    _web_app_module._core = None


@pytest.fixture
async def client():
    from graphexosuit.layer.backend.app import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

class TestRunEndpoint:
    async def test_run_to_completion(self, client: AsyncClient):
        resp = await client.post("/run", params={"initial_state": json.dumps({"value": "hello"})})
        assert resp.status_code == 200
        data = resp.json()
        assert data["final_result"] is not None
        assert data["final_result"]["value"] == "hello_done"

    async def test_run_with_thread_id(self, client: AsyncClient):
        resp = await client.post(
            "/run", params={"initial_state": json.dumps({"value": "hello"}), "thread_id": "my-thread"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "my-thread"

    async def test_run_pauses_on_interrupt(self, client: AsyncClient):
        resp = await client.post(
            "/run",
            params={"initial_state": json.dumps({"value": "interrupt_me"}), "thread_id": "web-pause"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkpoint_id"] is not None
        assert data["interrupt_value"] is not None
        assert data["interrupt_value"]["message"] == "Choose"


# ---------------------------------------------------------------------------
# POST /resume
# ---------------------------------------------------------------------------

class TestResumeEndpoint:
    async def _get_paused(self, client: AsyncClient):
        resp = await client.post(
            "/run",
            params={"initial_state": json.dumps({"value": "interrupt_me"}), "thread_id": "web-resume"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["interrupt_value"] is not None
        return data["thread_id"], data["checkpoint_id"]

    async def test_resume_completes(self, client: AsyncClient):
        thread_id, checkpoint_id = await self._get_paused(client)
        resp = await client.post(
            "/resume",
            params={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "resume_value": "{}",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Resume should complete without errors
        assert data["thread_id"] == thread_id

    async def test_resume_with_payload(self, client: AsyncClient):
        import json
        thread_id, checkpoint_id = await self._get_paused(client)
        resp = await client.post(
            "/resume",
            params={
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "resume_value": json.dumps({"extra": "data"}),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == thread_id

    async def test_resume_invalid_payload(self, client: AsyncClient):
        resp = await client.post(
            "/resume",
            params={
                "thread_id": "t",
                "checkpoint_id": "c",
                "resume_value": "not-json",
            },
        )
        assert resp.status_code == 422

    async def test_get_resume_returns_405(self, client: AsyncClient):
        resp = await client.get("/resume")
        assert resp.status_code == 405
        assert "POST" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /retry
# ---------------------------------------------------------------------------

class TestRetryEndpoint:
    async def test_retry_recovers(self, client: AsyncClient):
        # First run fails
        resp = await client.post(
            "/run",
            params={"initial_state": json.dumps({"value": "fail_me"}), "thread_id": "web-retry"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_message"] is not None

        resp2 = await client.post(
            "/retry",
            params={
                "thread_id": data["thread_id"],
                "checkpoint_id": data["checkpoint_id"],
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["final_result"] is not None

    async def test_get_retry_returns_405(self, client: AsyncClient):
        resp = await client.get("/retry")
        assert resp.status_code == 405
        assert "POST" in resp.json()["detail"]
