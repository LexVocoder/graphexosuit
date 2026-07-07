"""Tests for graphexosuit.layer.backend."""

from __future__ import annotations

import time
from typing import Any, TypedDict

import pytest
from fastapi.testclient import TestClient
from langchain_core.stores import BaseStore

from graphexosuit.core import ExosuitLiner, InterruptOption, StandardizedInterrupt
from graphexosuit.layer.backend import create_app
from graphexosuit.layer.backend.transformers import transform_run_result, build_resume_url
from graphexosuit.layer.backend.error_responses import build_retry_url, error_response_500


# ---------------------------------------------------------------------------
# Simple in-memory execution data store for testing
# ---------------------------------------------------------------------------

class _InMemoryExecutionDataStore(BaseStore):
    """Simple in-memory implementation of BaseStore for testing."""
    
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
    
    def mget(self, keys: list[str]) -> list[Any | None]:
        """Get multiple values from the store."""
        return [self._data.get(key) for key in keys]
    
    def mset(self, key_value_pairs: list[tuple[str, Any]]) -> None:
        """Set multiple key-value pairs."""
        for key, value in key_value_pairs:
            self._data[key] = value
    
    def mdelete(self, keys: list[str]) -> None:
        """Delete multiple keys."""
        for key in keys:
            if key in self._data:
                del self._data[key]
    
    def yield_keys(self, pattern: str | None = None) -> Any:
        """Yield all keys, optionally filtered by pattern."""
        for key in self._data.keys():
            yield key

# ---------------------------------------------------------------------------
# Shared in-process graph setup (mirrors test_cli.py pattern)
# ---------------------------------------------------------------------------

class _State(TypedDict):
    value: str


_fail_call_count: dict[str, int] = {}


def _get_graph():
    from langgraph.graph import StateGraph
    from langgraph.types import interrupt

    builder = StateGraph(_State)

    def node(state: _State) -> _State:
        value = state["value"]
        if value == "interrupt_me":
            interrupt(
                StandardizedInterrupt(
                    message="Choose a strategy",
                    options=[
                        InterruptOption(label="Default", payload={"strategy": "default"}),
                        InterruptOption(label="Advanced", payload={"strategy": "advanced"}),
                    ],
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
    return builder.compile(checkpointer=_get_checkpointer())


from langgraph.checkpoint.memory import MemorySaver as _MemorySaver

_shared_checkpointer = _MemorySaver()


class _CheckpointerCM:
    """Minimal context manager wrapping a MemorySaver."""

    def __init__(self, checkpointer: Any) -> None:
        self._checkpointer = checkpointer

    def __enter__(self) -> Any:
        return self._checkpointer

    def __exit__(self, *_args: Any) -> None:
        pass  # MemorySaver needs no teardown


def _get_checkpointer() -> Any:
    return _shared_checkpointer


class _TestLiner(ExosuitLiner):
    """Minimal ExosuitLiner for use in tests."""

    def get_graph(self) -> Any:
        return _get_graph()

    def get_checkpointer_cm(self) -> Any:
        return _CheckpointerCM(_get_checkpointer())


def _make_client() -> TestClient:
    """Create a fresh TestClient backed by a new async app with in-memory execution data store."""
    execution_data_store = _InMemoryExecutionDataStore()
    app = create_app(_TestLiner(), execution_data_store)
    return TestClient(app, raise_server_exceptions=False)



# ===========================================================================
# Unit tests: create_app
# ===========================================================================

class TestCreateApp:
    def test_create_app_raises_on_invalid_liner(self) -> None:
        """create_app must propagate liner validation error at construction time."""
        store = _InMemoryExecutionDataStore()
        with pytest.raises(ValueError):
            create_app(None, store)  # type: ignore[arg-type]


# ===========================================================================
# Unit tests: error_responses
# ===========================================================================

class TestErrorResponses:
    def test_build_retry_url_format(self) -> None:
        """retry URL must contain thread_id and checkpoint_id as path segments."""
        url = build_retry_url("t-123", "ckpt-456")
        assert "/retry" in url
        assert "/thread/t-123/" in url
        assert "/checkpoint/ckpt-456/" in url

    def test_build_retry_url_encodes_special_chars(self) -> None:
        """Special characters in IDs must be percent-encoded."""
        url = build_retry_url("t/123", "ckpt 456")
        assert "t%2F123" in url and "t/123" not in url  # URL-encoded slash
        assert "ckpt+456" in url or "ckpt%20456" in url  # URL-encoded space

    def test_error_response_500_shape(self) -> None:
        """500 response must include error, thread_id, checkpoint_id, retry_url."""
        exc = RuntimeError("boom")
        body = error_response_500(exc, "t-1", "ckpt-1")
        assert body["error"] == "boom"
        assert body["thread_id"] == "t-1"
        assert body["checkpoint_id"] == "ckpt-1"
        assert "/retry" in body["retry_url"]

    def test_error_response_500_retry_url_contains_ids(self) -> None:
        """The retry_url inside a 500 response must embed the provided IDs."""
        body = error_response_500(RuntimeError("x"), "my-thread", "my-ckpt")
        assert "my-thread" in body["retry_url"]
        assert "my-ckpt" in body["retry_url"]


# ===========================================================================
# Unit tests: transformers
# ===========================================================================

class TestTransformers:
    def test_build_resume_url_encodes_payload(self) -> None:
        """build_resume_url must construct a properly formatted URL with encoded IDs."""
        url = build_resume_url("t-1", "ckpt-1")
        # URL should contain thread_id and checkpoint_id as path segments, not query params
        assert "/thread/t-1/checkpoint/ckpt-1/resume" in url
        # resume_value is NOT included in URL; sent in request body instead
        assert "resume_value" not in url

    def test_transform_paused_result_shape(self) -> None:
        """A paused RunResult must produce thread_id, checkpoint_id, interrupt_value."""
        from graphexosuit.core import RunResult

        result = RunResult(
            thread_id="t-1",
            checkpoint_id="ckpt-1",
            interrupt_value=StandardizedInterrupt(
                message="Choose",
                options=[InterruptOption(label="OK", payload={"x": 1})],
            ),
        )
        body = transform_run_result(result)
        assert body["thread_id"] == "t-1"
        assert body["checkpoint_id"] == "ckpt-1"
        iv = body["interrupt_value"]
        assert iv["message"] == "Choose"
        assert len(iv["options"]) == 1
        option = iv["options"][0]
        assert option["label"] == "OK"
        assert "resume_url" in option

    def test_transform_paused_excludes_payload(self) -> None:
        """Interrupt option payload must NOT appear in the transformed response."""
        from graphexosuit.core import RunResult

        result = RunResult(
            thread_id="t-2",
            checkpoint_id="ckpt-2",
            interrupt_value=StandardizedInterrupt(
                message="Msg",
                options=[InterruptOption(label="L", payload={"secret": "s3cr3t"})],
            ),
        )
        body = transform_run_result(result)
        option = body["interrupt_value"]["options"][0]
        assert "payload" not in option
        assert "secret" not in str(option.get("label", ""))

    def test_transform_paused_resume_url_format(self) -> None:
        """resume_url must contain properly formatted thread_id and checkpoint_id in path."""
        from graphexosuit.core import RunResult

        payload = {"strategy": "default"}
        result = RunResult(
            thread_id="t-3",
            checkpoint_id="ckpt-3",
            interrupt_value=StandardizedInterrupt(
                message="M",
                options=[InterruptOption(label="L", payload=payload)],
            ),
        )
        body = transform_run_result(result)
        resume_url = body["interrupt_value"]["options"][0]["resume_url"]
        # Verify URL contains correct path structure; resume_value not in URL
        assert "/thread/t-3/checkpoint/ckpt-3/resume" in resume_url
        assert "resume_value" not in resume_url

    def test_transform_completed_result_shape(self) -> None:
        """A completed RunResult must produce only thread_id and final_result."""
        from graphexosuit.core import RunResult

        result = RunResult(
            thread_id="t-4",
            final_result={"status": "done", "doc": "content"},
        )
        body = transform_run_result(result)
        assert body["thread_id"] == "t-4"
        assert body["final_result"] == {"status": "done", "doc": "content"}
        assert "interrupt_value" not in body
        assert "checkpoint_id" not in body

    def test_transform_non_serializable_final_result_uses_str(self) -> None:
        """Non-JSON-serializable values in final_result must be stringified, not raised."""
        from graphexosuit.core import RunResult

        class _Unserializable:
            def __repr__(self) -> str:
                return "CustomObject()"

        result = RunResult(
            thread_id="t-5",
            final_result={"obj": _Unserializable()},
        )
        body = transform_run_result(result)
        # The value is converted to its string representation
        assert body["final_result"]["obj"] == "CustomObject()"


# ===========================================================================
# Integration tests: POST /run (async endpoint)
# ===========================================================================

class TestRunEndpoint:
    def test_run_returns_202_with_thread_id_and_poll_url(self) -> None:
        """POST /run must return 202 with thread_id and poll_url."""
        client = _make_client()
        response = client.post("/run", json={"initial_state": {"value": "hello"}})
        assert response.status_code == 202
        data = response.json()
        assert "thread_id" in data
        assert "poll_url" in data
        assert data["poll_url"].startswith("/thread/")

    def test_run_background_execution_completes(self) -> None:
        """After POST /run, the background worker should eventually complete the execution."""
        client = _make_client()
        response = client.post("/run", json={"initial_state": {"value": "hello"}})
        assert response.status_code == 202
        thread_id = response.json()["thread_id"]
        
        # Poll until execution completes (with a timeout)
        for _ in range(20):
            poll_response = client.get(f"/thread/{thread_id}")
            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                if poll_data.get("status") == "completed":
                    assert poll_data["result"]["final_result"]["value"] == "hello_done"
                    # Verify output_lines exists and is a list
                    assert "output_lines" in poll_data
                    assert isinstance(poll_data["output_lines"], list)
                    return
            time.sleep(0.1)
        
        # If we get here, the execution timed out
        assert False, "Background execution did not complete within timeout"


# ===========================================================================
# Integration tests: GET /thread/{thread_id} (async polling)
# ===========================================================================

class TestGetThreadEndpoint:
    def test_get_thread_returns_404_for_nonexistent_thread(self) -> None:
        """GET /thread/{thread_id} must return 404 for nonexistent threads."""
        client = _make_client()
        response = client.get("/thread/nonexistent-thread-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_get_thread_returns_execution_data_after_completion(self) -> None:
        """GET /thread/{thread_id} must return execution data with all required fields."""
        client = _make_client()
        run_response = client.post("/run", json={"initial_state": {"value": "hello"}})
        thread_id = run_response.json()["thread_id"]
        
        # Wait for completion
        for _ in range(20):
            poll_response = client.get(f"/thread/{thread_id}")
            if poll_response.status_code == 200:
                data = poll_response.json()
                if data.get("status") == "completed":
                    assert data["thread_id"] == thread_id
                    assert "status" in data
                    assert "result" in data
                    assert "error" in data
                    assert "output_lines" in data
                    assert "created_at" in data
                    assert data["status"] == "completed"
                    assert data["result"] is not None
                    return
            time.sleep(0.1)
        
        assert False, "Thread did not complete within timeout"


# ===========================================================================
# Integration tests: POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume
# ===========================================================================

class TestResumeEndpointAsync:
    def test_resume_returns_202_after_interrupt(self) -> None:
        """POST /resume must return 202 immediately."""
        client = _make_client()
        
        # First, trigger an interrupt
        run_response = client.post("/run", json={"initial_state": {"value": "interrupt_me"}})
        thread_id = run_response.json()["thread_id"]
        
        # Wait for interrupt to occur
        for _ in range(20):
            poll_response = client.get(f"/thread/{thread_id}")
            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                if poll_data.get("status") == "paused":
                    result = poll_data.get("result")
                    if result and "checkpoint_id" in result:
                        checkpoint_id = result["checkpoint_id"]
                        
                        # Now resume
                        resume_response = client.post(
                            f"/thread/{thread_id}/checkpoint/{checkpoint_id}/resume",
                            json={"strategy": "default"}
                        )
                        assert resume_response.status_code == 202
                        resume_data = resume_response.json()
                        assert "thread_id" in resume_data
                        assert "poll_url" in resume_data
                        return
            time.sleep(0.1)
        
        assert False, "Interrupt did not occur within timeout"

    def test_resume_returns_404_for_nonexistent_thread(self) -> None:
        """POST /resume on nonexistent thread must return 404."""
        client = _make_client()
        response = client.post(
            "/thread/nonexistent/checkpoint/ckpt/resume",
            json={"strategy": "default"}
        )
        assert response.status_code == 404


# ===========================================================================
# Integration tests: POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry
# ===========================================================================

class TestRetryEndpointAsync:
    def test_retry_returns_202_after_error(self) -> None:
        """POST /retry must return 202 immediately."""
        _fail_call_count.clear()
        client = _make_client()
        
        # Trigger a failure
        run_response = client.post("/run", json={"initial_state": {"value": "fail_me"}})
        thread_id = run_response.json()["thread_id"]
        
        # Wait for error to occur
        for _ in range(20):
            poll_response = client.get(f"/thread/{thread_id}")
            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                if poll_data.get("status") == "error":
                    result = poll_data.get("error")
                    if result and "checkpoint_id" in result:
                        checkpoint_id = result["checkpoint_id"]
                        
                        # Now retry
                        retry_response = client.post(
                            f"/thread/{thread_id}/checkpoint/{checkpoint_id}/retry"
                        )
                        assert retry_response.status_code == 202
                        retry_data = retry_response.json()
                        assert "thread_id" in retry_data
                        assert "poll_url" in retry_data
                        return
            time.sleep(0.1)
        
        assert False, "Error did not occur within timeout"

    def test_retry_returns_404_for_nonexistent_thread(self) -> None:
        """POST /retry on nonexistent thread must return 404."""
        client = _make_client()
        response = client.post("/thread/nonexistent/checkpoint/ckpt/retry")
        assert response.status_code == 404

