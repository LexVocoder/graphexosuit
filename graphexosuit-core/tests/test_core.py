"""Tests for graphexosuit.core."""

from __future__ import annotations

import pytest
from typing import Any, TypedDict
from unittest.mock import MagicMock

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from graphexosuit.core import (
    ExosuitCore,
    InterruptOption,
    RunResult,
    StandardizedInterrupt,
    ExosuitLiner,
    _validate_interrupt_value,
    InvalidInterruptError,
    GraphExecutionError,
)
from graphexosuit.core.liner_validator import validate_liner


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
                options=[InterruptOption(label="Approve", payload={})],
            )
        )
        # If we reach here, we were resumed and interrupt() returned the resume value
        return {"value": "approved", "_resume_done": True}

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


def _invalid_interrupt_graph() -> StateGraph:
    """Graph that returns an interrupt with invalid shape (missing attributes)."""
    builder = StateGraph(SimpleState)

    def node(state: SimpleState) -> dict:
        # Return an invalid interrupt object (missing 'message' and 'options')
        invalid_interrupt = MagicMock(spec=["id"])
        return interrupt(invalid_interrupt)

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder


# Helper: simple context manager wrapper for checkpointer
class _CheckpointerContextManager:
    """Simple context manager wrapper for a checkpointer."""
    def __init__(self, checkpointer):
        self._checkpointer = checkpointer
    
    def __enter__(self):
        return self._checkpointer
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # No cleanup needed for MemorySaver


# Helper to create a TestLiner that properly compiles graphs
def _make_core(uncompiled_graph_thunk, precompile=True) -> ExosuitCore:
    """Create ExosuitCore with a graph and checkpointer.
    
    Parameters
    ----------
    uncompiled_graph_thunk:
        Callable that returns a StateGraph.
    precompile:
        If True, the graph is compiled before being passed to ExosuitCore.
        If False, the raw StateGraph is passed (for testing that ExosuitCore compiles it automatically).
    """
    checkpointer = MemorySaver()
    graph = uncompiled_graph_thunk()
    if precompile:
        return ExosuitCore(
            graph=graph.compile(checkpointer=checkpointer),
            checkpointer_cm=_CheckpointerContextManager(checkpointer),
        )
    else:
        return ExosuitCore(
            graph=graph,
            checkpointer_cm=_CheckpointerContextManager(checkpointer),
        )


# ---------------------------------------------------------------------------
# RunResult validation
# ---------------------------------------------------------------------------

class TestRunResultValidation:
    def test_completed_valid(self):
        r = RunResult(thread_id="t1", final_result={"x": 1})
        assert r.final_result is not None

    def test_completion_result_with_interrupt_raises(self):
        iv = StandardizedInterrupt(message="m", options=[])
        with pytest.raises(ValueError, match="exactly one"):
            RunResult(
                thread_id="t1",
                interrupt_value=iv,
                final_result={"x": 1},
                checkpoint_id="cid"
            )

    def test_paused_valid(self):
        iv = StandardizedInterrupt(message="m", options=[])
        r = RunResult(
            thread_id="t1",
            interrupt_value=iv,
            checkpoint_id="cid"
        )
        assert r.interrupt_value is not None

    def test_paused_missing_checkpoint_id_raises(self):
        iv = StandardizedInterrupt(message="m", options=[])
        with pytest.raises(ValueError, match="checkpoint_id"):
            RunResult(thread_id="t1", interrupt_value=iv)

    def test_no_terminal_state_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            RunResult(thread_id="t1")


# ---------------------------------------------------------------------------
# Interrupt validation helpers
# ---------------------------------------------------------------------------

class TestValidationHelpers:
    def test_valid_interrupt(self):
        iv = StandardizedInterrupt(
            message="msg",
            options=[InterruptOption(label="X", payload={})]
        )
        _validate_interrupt_value(iv)  # should not raise

    def test_interrupt_missing_message(self):
        obj = MagicMock(spec=["options"])
        with pytest.raises(InvalidInterruptError, match="message"):
            _validate_interrupt_value(obj)

    def test_interrupt_missing_options(self):
        obj = MagicMock(spec=["message"])
        with pytest.raises(InvalidInterruptError, match="message"):
            _validate_interrupt_value(obj)

    def test_interrupt_option_missing_payload(self):
        bad_option = MagicMock(spec=["label"])
        iv = MagicMock()
        iv.message = "m"
        iv.options = [bad_option]
        with pytest.raises(InvalidInterruptError, match="'label' and 'payload'"):
            _validate_interrupt_value(iv)




# ---------------------------------------------------------------------------
# ExosuitCore.run
# ---------------------------------------------------------------------------

class TestExosuitCoreRun:
    def test_run_to_completion(self):
        core = _make_core(_simple_graph)
        result = core.run({"value": "hello"})
        assert result.final_result is not None
        assert result.interrupt_value is None
        assert result.final_result == {"value": "hello_done"}

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
        assert result.final_result is None
        assert result.interrupt_value is not None
        assert result.interrupt_value.message == "Approve?"
        assert result.checkpoint_id is not None

    def test_run_error_raises_graph_execution_error(self):
        core = _make_core(_error_graph)
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"})
        
        error = exc_info.value
        assert "Graph execution failed" in str(error)
        assert error.__cause__ is not None
        assert isinstance(error.__cause__, RuntimeError)
        assert "first attempt failed" in str(error.__cause__)
        assert error.get_thread_id() is not None

    def test_run_invalid_interrupt_raises_graph_execution_error(self):
        core = _make_core(_invalid_interrupt_graph)
        # Invalid interrupt causes serialization error during checkpoint save,
        # which is then wrapped in GraphExecutionError
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"})
        
        error = exc_info.value
        assert error.get_thread_id() is not None
        # The original error is a serialization error from msgpack
        assert "Type is not msgpack serializable" in str(error.__cause__)

    def test_run_passes_initial_state_to_invoke_unchanged(self):
        """initial_state is forwarded to _invoke without modification."""
        core = _make_core(_simple_graph)
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(initial_state, config):
            captured_args["initial_state"] = initial_state
            captured_args["config"] = config
            return original_invoke(initial_state, config)
        
        core._invoke = mock_invoke
        
        input_state = {"value": "test"}
        result = core.run(input_state)
        
        assert captured_args["initial_state"] == input_state


# ---------------------------------------------------------------------------
# ExosuitCore.resume
# ---------------------------------------------------------------------------

class TestExosuitCoreResume:
    def _paused_core(self):
        core = _make_core(_interrupt_graph)
        run_result = core.run({"value": "start"}, thread_id="t-resume")
        assert run_result.interrupt_value is not None
        return core, run_result

    def test_resume_completes(self):
        core, run_result = self._paused_core()
        assert run_result.checkpoint_id is not None
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, {})
        # Resume should succeed without error
        assert result.thread_id == run_result.thread_id
        assert result.checkpoint_id is not None

    def test_resume_with_dict_payload(self):
        core, run_result = self._paused_core()
        assert run_result.checkpoint_id is not None
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, {"key": "value"})
        assert result.final_result is not None

    def test_resume_passes_resume_value_as_command_to_invoke(self):
        """resume_value is wrapped in a Command and forwarded to _invoke unchanged."""
        core, run_result = self._paused_core()
        assert run_result.checkpoint_id is not None
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(initial_state, config):
            captured_args["initial_state"] = initial_state
            captured_args["config"] = config
            return original_invoke(initial_state, config)
        
        core._invoke = mock_invoke
        
        resume_value = {"key": "value"}
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, resume_value)
        
        # Verify the initial_state passed to _invoke is a Command with the original resume_value
        assert isinstance(captured_args["initial_state"], Command)
        assert captured_args["initial_state"].resume == resume_value


# ---------------------------------------------------------------------------
# ExosuitCore.retry
# ---------------------------------------------------------------------------

class TestExosuitCoreRetry:
    def test_retry_recovers(self):
        core = _make_core(_error_graph)
        # First call: error
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"}, thread_id="t-retry")
        
        # Extract checkpoint from the exception for retry
        err = exc_info.value
        checkpoint_id = err.get_checkpoint_id()

        # Retry with the checkpoint from the error
        result = core.retry(err.get_thread_id(), checkpoint_id)
        assert result.final_result is not None
        assert result.final_result == {"value": "recovered"}

    def test_retry_graph_executes_again_and_recovers(self):
        """When retry is called, graph executes again and can recover from errors."""
        core = _make_core(_error_graph)
        
        # First call: error
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"}, thread_id="t-get-state-error")
        
        err = exc_info.value
        checkpoint_id = err.get_checkpoint_id()
        
        # On retry, the error graph will succeed on second execution (call_count is now 2)
        result = core.retry(err.get_thread_id(), checkpoint_id)
        
        # Verify the graph recovered
        assert result.final_result is not None
        assert result.final_result == {"value": "recovered"}


# ---------------------------------------------------------------------------
# ExosuitCore._build_run_result
# ---------------------------------------------------------------------------

class TestExosuitCoreBuildRunResult:
    def test_build_run_result_returns_correct_values(self):
        """Test _build_run_result constructs and returns the expected RunResult."""
        core = _make_core(_simple_graph)

        result = core._build_run_result(
            thread_id="t1", final_result={"value": "test"}
        )

        assert result.final_result == {"value": "test"}
        assert result.thread_id == "t1"
        assert result.interrupt_value is None


# ---------------------------------------------------------------------------
# ExosuitCore compile responsibility
# ---------------------------------------------------------------------------

class TestExosuitCoreCompile:
    def test_accepts_precompiled_graph(self):
        """ExosuitCore must accept a pre-compiled graph."""
        checkpointer = MemorySaver()
        compiled = _simple_graph().compile(checkpointer=checkpointer)

        core = ExosuitCore(
            graph=compiled,
            checkpointer_cm=_CheckpointerContextManager(checkpointer),
        )
        result = core.run({"value": "test"})
        assert result.final_result is not None
        assert result.final_result == {"value": "test_done"}

    def test_accepts_uncompiled_state_graph(self):
        """ExosuitCore accepts and compiles an uncompiled StateGraph."""
        checkpointer = MemorySaver()
        core = ExosuitCore(
            graph=_simple_graph(),
            checkpointer_cm=_CheckpointerContextManager(checkpointer),
        )
        result = core.run({"value": "test"})
        assert result.final_result is not None
        assert result.final_result == {"value": "test_done"}

    def test_uncompiled_state_graph_compiles_with_correct_checkpointer(self):
        """ExosuitCore compiles uncompiled StateGraph using the correct checkpointer."""
        checkpointer = MemorySaver()
        core_with_interrupt = ExosuitCore(
            graph=_interrupt_graph(),
            checkpointer_cm=_CheckpointerContextManager(checkpointer),
        )
        result = core_with_interrupt.run({"value": "start"}, thread_id="t1")
        
        # Should pause with a checkpoint
        assert result.interrupt_value is not None
        assert result.checkpoint_id is not None


# ---------------------------------------------------------------------------
# Helpers: double-interrupt graph (regression for stale checkpoint_id)
# ---------------------------------------------------------------------------

class DoubleInterruptState(TypedDict):
    step: int


def _double_interrupt_graph() -> StateGraph:
    """Graph with two sequential interrupt nodes: interrupt1 → interrupt2 → END.

    Used to exercise the stale-checkpoint regression: when resume() hits a
    *second* interrupt, _extract_checkpoint_id must return the checkpoint
    created by that second interrupt, not the one from the first.
    """
    builder = StateGraph(DoubleInterruptState)

    def node_interrupt1(state: DoubleInterruptState) -> dict:
        interrupt(
            StandardizedInterrupt(
                message="First approval needed",
                options=[InterruptOption(label="Approve", payload="approved")],
            )
        )
        return {"step": state["step"] + 1}

    def node_interrupt2(state: DoubleInterruptState) -> dict:
        interrupt(
            StandardizedInterrupt(
                message="Second approval needed",
                options=[InterruptOption(label="Approve", payload="approved")],
            )
        )
        return {"step": state["step"] + 1}

    builder.add_node("node_interrupt1", node_interrupt1)
    builder.add_node("node_interrupt2", node_interrupt2)
    builder.set_entry_point("node_interrupt1")
    builder.add_edge("node_interrupt1", "node_interrupt2")
    builder.add_edge("node_interrupt2", END)
    return builder


# ---------------------------------------------------------------------------
# Double-interrupt regression tests
# ---------------------------------------------------------------------------

class TestDoubleInterruptRegression:
    """Regression tests for the stale checkpoint_id bug.

    Before the fix, resume() returned the *first* interrupt's checkpoint_id
    even after hitting a second interrupt, causing an infinite re-interruption
    loop on subsequent resumes.
    """

    def _run_to_first_interrupt(self):
        """Return (core, r1) where r1 is paused at node_interrupt1."""
        core = _make_core(_double_interrupt_graph)
        r1 = core.run({"step": 0}, thread_id="double-interrupt-thread")
        assert r1.interrupt_value is not None, "Expected pause at node_interrupt1"
        assert "First" in r1.interrupt_value.message
        return core, r1

    def test_resume_after_first_interrupt_pauses_at_second(self):
        """resume() from interrupt1 must pause at interrupt2, not loop back."""
        core, r1 = self._run_to_first_interrupt()
        assert r1.checkpoint_id is not None

        r2 = core.resume(r1.thread_id, r1.checkpoint_id, "approved")
        assert r2.interrupt_value is not None, "Expected pause at node_interrupt2"
        assert "Second" in r2.interrupt_value.message

    def test_resume_after_first_interrupt_returns_distinct_checkpoint_id(self):
        """The checkpoint_id returned after hitting interrupt2 must differ from interrupt1's.

        This is the direct observable symptom of the bug: both runs returned the
        same checkpoint_id, making it impossible to resume from the correct position.
        """
        core, r1 = self._run_to_first_interrupt()
        assert r1.checkpoint_id is not None

        r2 = core.resume(r1.thread_id, r1.checkpoint_id, "approved")
        assert r2.checkpoint_id != r1.checkpoint_id, (
            "checkpoint_id after the second interrupt must not equal the first interrupt's "
            "checkpoint_id — the bug caused them to be identical"
        )

    def test_resume_from_second_interrupt_completes_graph(self):
        """Resuming from interrupt2's checkpoint_id must complete the graph, not re-run interrupt1.

        With the bug, step would be 1 (interrupt1 re-ran) instead of 2 (both
        interrupts executed exactly once in order).
        """
        core, r1 = self._run_to_first_interrupt()
        assert r1.checkpoint_id is not None

        r2 = core.resume(r1.thread_id, r1.checkpoint_id, "approved")
        assert r2.checkpoint_id is not None

        r3 = core.resume(r2.thread_id, r2.checkpoint_id, "approved")
        assert r3.final_result is not None, "Graph should have completed"
        assert r3.final_result.get("step") == 2, (
            f"Expected step=2 (both interrupts ran once), got step={r3.final_result.get('step')}. "
            "node_interrupt1 likely re-ran due to the stale checkpoint_id bug."
        )

    def test_resume_from_second_interrupt_does_not_repeat_first_interrupt(self):
        """After resuming from interrupt2, the graph must not re-trigger interrupt1's message."""
        core, r1 = self._run_to_first_interrupt()
        assert r1.checkpoint_id is not None

        r2 = core.resume(r1.thread_id, r1.checkpoint_id, "approved")
        assert r2.checkpoint_id is not None

        r3 = core.resume(r2.thread_id, r2.checkpoint_id, "approved")
        # If interrupt1 re-ran, r3 would have an interrupt_value with "First" in the message.
        assert r3.interrupt_value is None, (
            "Graph should have completed, but got another interrupt. "
            "node_interrupt1 likely re-ran due to the stale checkpoint_id bug. "
            f"Interrupt message: {r3.interrupt_value.message if r3.interrupt_value else 'N/A'}"
        )


# ===========================================================================
# Unit tests: liner_validator
# ===========================================================================

class TestLinerValidator:
    """Tests for the liner_validator module."""

    def test_valid_liner_passes(self) -> None:
        """A fully-conformant Liner must not raise."""
        class _TestLiner(ExosuitLiner):
            def get_graph(self) -> Any:
                return _simple_graph().compile(checkpointer=MemorySaver())

            def get_checkpointer_cm(self) -> Any:
                return _CheckpointerContextManager(MemorySaver())

        validate_liner(_TestLiner())

    def test_none_liner_raises_value_error(self) -> None:
        """None must be rejected with a descriptive message."""
        with pytest.raises(ValueError, match="must not be None"):
            validate_liner(None)

    def test_missing_get_graph_raises(self) -> None:
        """A Liner without get_graph must be rejected."""
        class _NoGraph:
            def get_checkpointer_cm(self) -> Any:
                return None

        with pytest.raises(ValueError, match="get_graph"):
            validate_liner(_NoGraph())

    def test_missing_get_checkpointer_cm_raises(self) -> None:
        """A Liner without get_checkpointer_cm must be rejected."""
        class _NoCheckpointer:
            def get_graph(self) -> Any:
                return None

        with pytest.raises(ValueError, match="get_checkpointer_cm"):
            validate_liner(_NoCheckpointer())

    def test_non_callable_method_raises(self) -> None:
        """Attributes that are not callable must be treated as missing."""
        class _BadLiner:
            get_graph = "not_a_function"

            def get_checkpointer_cm(self) -> Any:
                return None

        with pytest.raises(ValueError, match="get_graph"):
            validate_liner(_BadLiner())

