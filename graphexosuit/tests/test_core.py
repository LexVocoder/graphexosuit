"""Tests for graphexosuit.core."""

from __future__ import annotations

import pytest
from typing import TypedDict
from unittest.mock import MagicMock

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from graphexosuit.core import (
    ExosuitCore,
    InterruptOption,
    ResumeValue,
    RunResult,
    StandardizedInterrupt,
    _validate_run_result,
    _validate_interrupt_value,
    _validate_resume_value,
)


# ---------------------------------------------------------------------------
# Helpers: minimal LangGraph workflows
# ---------------------------------------------------------------------------

class SimpleState(TypedDict):
    value: str


def _simple_graph() -> StateGraph:
    """Graph that runs to completion immediately."""
    builder = StateGraph(SimpleState)

    def node(state: SimpleState) -> dict:
        return {"value": state["value"] + "_done"}

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder


def _interrupt_graph() -> StateGraph:
    """Graph that pauses on the first run and completes after resume."""
    builder = StateGraph(SimpleState)

    def node(state: SimpleState) -> dict:
        val = interrupt(
            StandardizedInterrupt(
                message="Approve?",
                options=[InterruptOption(id="approve", label="Approve")],
            )
        )
        return {"value": val.id}

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder


def _error_graph() -> StateGraph:
    """Graph that raises on first invocation."""
    builder = StateGraph(SimpleState)
    call_count = {"n": 0}

    def node(state: SimpleState) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first attempt failed")
        return {"value": "recovered"}

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder


def _make_core(graph_fn) -> ExosuitCore:
    return ExosuitCore(graph_fn(), MemorySaver())


# ---------------------------------------------------------------------------
# RunResult validation
# ---------------------------------------------------------------------------

class TestRunResultValidation:
    def test_completed_valid(self):
        r = RunResult(completed=True, thread_id="t1", result={"x": 1})
        assert r.completed

    def test_completed_with_error_raises(self):
        with pytest.raises(ValueError, match="incompatible"):
            RunResult(completed=True, thread_id="t1", error="oops")

    def test_completed_with_paused_raises(self):
        with pytest.raises(ValueError, match="incompatible"):
            RunResult(completed=True, thread_id="t1", paused=True)

    def test_paused_valid(self):
        iv = StandardizedInterrupt(message="m", options=[])
        r = RunResult(
            completed=False, thread_id="t1", paused=True,
            interrupt_value=iv, checkpoint_id="cid"
        )
        assert r.paused

    def test_paused_missing_interrupt_value_raises(self):
        with pytest.raises(ValueError, match="interrupt_value"):
            RunResult(
                completed=False, thread_id="t1", paused=True,
                checkpoint_id="cid"
            )

    def test_paused_missing_checkpoint_id_raises(self):
        iv = StandardizedInterrupt(message="m", options=[])
        with pytest.raises(ValueError, match="checkpoint_id"):
            RunResult(
                completed=False, thread_id="t1", paused=True,
                interrupt_value=iv
            )

    def test_error_valid(self):
        r = RunResult(completed=False, thread_id="t1", error="boom")
        assert r.error == "boom"

    def test_error_missing_raises(self):
        with pytest.raises(ValueError, match="error"):
            RunResult(completed=False, thread_id="t1")


# ---------------------------------------------------------------------------
# Interrupt / ResumeValue validation helpers
# ---------------------------------------------------------------------------

class TestValidationHelpers:
    def test_valid_interrupt(self):
        iv = StandardizedInterrupt(
            message="msg",
            options=[InterruptOption(id="x", label="X")]
        )
        _validate_interrupt_value(iv)  # should not raise

    def test_interrupt_missing_message(self):
        obj = MagicMock(spec=["options"])
        with pytest.raises(ValueError, match="message"):
            _validate_interrupt_value(obj)

    def test_interrupt_missing_options(self):
        obj = MagicMock(spec=["message"])
        with pytest.raises(ValueError, match="message"):
            _validate_interrupt_value(obj)

    def test_interrupt_option_missing_id(self):
        bad_option = MagicMock(spec=["label"])
        iv = MagicMock()
        iv.message = "m"
        iv.options = [bad_option]
        with pytest.raises(ValueError, match="'id' and 'label'"):
            _validate_interrupt_value(iv)

    def test_valid_resume_value(self):
        rv = ResumeValue(id="approve", payload=None)
        _validate_resume_value(rv)  # should not raise

    def test_resume_value_missing_id(self):
        obj = MagicMock(spec=["payload"])
        with pytest.raises(ValueError, match="'id' and 'payload'"):
            _validate_resume_value(obj)

    def test_resume_value_missing_payload(self):
        obj = MagicMock(spec=["id"])
        with pytest.raises(ValueError, match="'id' and 'payload'"):
            _validate_resume_value(obj)


# ---------------------------------------------------------------------------
# ExosuitCore.run
# ---------------------------------------------------------------------------

class TestExosuitCoreRun:
    def test_run_to_completion(self):
        core = _make_core(_simple_graph)
        result = core.run({"value": "hello"})
        assert result.completed
        assert not result.paused
        assert result.error is None
        assert result.result == {"value": "hello_done"}

    def test_run_generates_thread_id(self):
        core = _make_core(_simple_graph)
        result = core.run({"value": "x"})
        assert result.thread_id  # non-empty string

    def test_run_uses_provided_thread_id(self):
        core = _make_core(_simple_graph)
        result = core.run({"value": "x"}, thread_id="my-thread")
        assert result.thread_id == "my-thread"

    def test_run_pauses_on_interrupt(self):
        core = _make_core(_interrupt_graph)
        result = core.run({"value": "start"})
        assert not result.completed
        assert result.paused
        assert result.interrupt_value is not None
        assert result.interrupt_value.message == "Approve?"
        assert result.checkpoint_id is not None

    def test_run_error_returns_error_result(self):
        core = _make_core(_error_graph)
        result = core.run({"value": "start"})
        assert not result.completed
        assert not result.paused
        assert "first attempt failed" in result.error


# ---------------------------------------------------------------------------
# ExosuitCore.resume
# ---------------------------------------------------------------------------

class TestExosuitCoreResume:
    def _paused_core(self):
        core = _make_core(_interrupt_graph)
        run_result = core.run({"value": "start"}, thread_id="t-resume")
        assert run_result.paused
        return core, run_result

    def test_resume_completes(self):
        core, run_result = self._paused_core()
        rv = ResumeValue(id="approve", payload=None)
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, rv)
        assert result.completed
        assert result.result == {"value": "approve"}

    def test_resume_invalid_resume_value(self):
        core, run_result = self._paused_core()
        bad = MagicMock(spec=["id"])  # missing payload
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, bad)
        assert not result.completed
        assert "ResumeValue" in result.error


# ---------------------------------------------------------------------------
# ExosuitCore.retry
# ---------------------------------------------------------------------------

class TestExosuitCoreRetry:
    def test_retry_recovers(self):
        core = _make_core(_error_graph)
        # First call: error
        err_result = core.run({"value": "start"}, thread_id="t-retry")
        assert err_result.error
        # Retry
        result = core.retry(err_result.thread_id, err_result.checkpoint_id)
        assert result.completed
        assert result.result == {"value": "recovered"}

    def test_retry_no_failed_node(self):
        core = _make_core(_simple_graph)
        run_result = core.run({"value": "x"}, thread_id="t-no-retry")
        # A completed run has no pending node — retry should report an error
        result = core.retry(run_result.thread_id, run_result.checkpoint_id)
        assert not result.completed
        assert result.error


# ---------------------------------------------------------------------------
# ExosuitCore compile responsibility
# ---------------------------------------------------------------------------

class TestExosuitCoreCompile:
    def test_accepts_uncompiled_graph(self):
        """ExosuitCore must accept an uncompiled StateGraph and compile it."""
        uncompiled = _simple_graph()
        # Should NOT be a CompiledStateGraph yet
        from langgraph.graph.state import CompiledStateGraph
        assert not isinstance(uncompiled, CompiledStateGraph)

        core = ExosuitCore(uncompiled, MemorySaver())
        result = core.run({"value": "test"})
        assert result.completed
