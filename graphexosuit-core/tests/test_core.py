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
    _validate_run_result,
    _validate_interrupt_value,
    InvalidInterruptError,
    GraphExecutionError,
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
    """Create ExosuitCore with a TestLiner.
    
    Parameters
    ----------
    uncompiled_graph_thunk:
        Callable that returns a StateGraph.
    precompile:
        If True, get_graph() returns a pre-compiled graph.
        If False, get_graph() returns the raw StateGraph (for testing that ExosuitCore compiles it automatically).
    """
    checkpointer = MemorySaver()
    
    class TestLiner:
        def get_graph(self) -> Any:
            graph = uncompiled_graph_thunk()
            if precompile:
                # Return pre-compiled graph
                return graph.compile(checkpointer=checkpointer)
            else:
                # Return raw StateGraph (ExosuitCore will compile it)
                return graph

        def get_checkpointer_cm(self) -> Any:
            return _CheckpointerContextManager(checkpointer)

    return ExosuitCore(TestLiner())


# ---------------------------------------------------------------------------
# RunResult validation
# ---------------------------------------------------------------------------

class TestRunResultValidation:
    def test_completed_valid(self):
        r = RunResult(thread_id="t1", final_result={"x": 1})
        assert r.final_result is not None

    def test_completion_result_with_error_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            RunResult(thread_id="t1", error_message="oops", final_result={"x": 1})

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

    def test_error_valid(self):
        r = RunResult(thread_id="t1", error_message="boom", checkpoint_id="cid")
        assert r.error_message == "boom"

    def test_error_missing_checkpoint_id_raises(self):
        with pytest.raises(ValueError, match="checkpoint_id"):
            RunResult(thread_id="t1", error_message="boom")

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
        assert result.error_message is None
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
        assert result.error_message is None
        assert result.interrupt_value.message == "Approve?"
        assert result.checkpoint_id is not None

    def test_run_error_raises_graph_execution_error(self):
        core = _make_core(_error_graph)
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"})
        
        error = exc_info.value
        assert "Graph execution failed" in str(error)
        assert error.get_original_exception() is not None
        assert isinstance(error.get_original_exception(), RuntimeError)
        assert "first attempt failed" in str(error.get_original_exception())
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
        assert "Type is not msgpack serializable" in str(error.get_original_exception())

    def test_run_without_transform_initial_state_passes_unchanged(self):
        """When liner has no transform_initial_state, initial_state is passed to _invoke unchanged."""
        core = _make_core(_simple_graph)
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(initial_state, config):
            captured_args["initial_state"] = initial_state
            captured_args["config"] = config
            return original_invoke(initial_state, config)
        
        core._invoke = mock_invoke
        
        # Verify transform_initial_state does not exist
        assert not hasattr(core._liner, "transform_initial_state")
        
        input_state = {"value": "test"}
        result = core.run(input_state)
        
        # Verify the initial_state passed to _invoke is the same as input
        assert captured_args["initial_state"] == input_state

    def test_run_with_transform_initial_state_calls_and_passes_transformed(self):
        """When liner has transform_initial_state, it gets called and result is passed to _invoke."""
        core = _make_core(_simple_graph)
        
        # Add transform_initial_state method to liner
        def transform_fn(state):
            return {"value": state["value"] + "_transformed"}
        
        core._liner.transform_initial_state = transform_fn
        
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
        
        # Verify the initial_state passed to _invoke is the transformed version
        assert captured_args["initial_state"] == {"value": "test_transformed"}


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

    def test_resume_without_transform_passes_original_to_invoke(self):
        """When liner has no transform_resume_value, original resume_value is passed in Command to _invoke."""
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
        
        # Verify transform_resume_value does not exist
        assert not hasattr(core._liner, "transform_resume_value")
        
        resume_value = {"key": "value"}
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, resume_value)
        
        # Verify the initial_state passed to _invoke is a Command with the original resume_value
        assert isinstance(captured_args["initial_state"], Command)
        assert captured_args["initial_state"].resume == resume_value

    def test_resume_with_transform_passes_transformed_to_invoke(self):
        """When liner has transform_resume_value, transformed resume_value is passed in Command to _invoke."""
        core, run_result = self._paused_core()
        assert run_result.checkpoint_id is not None
        
        # Add transform_resume_value to liner
        def transform_fn(rv):
            return {"transformed": True, "original": rv}
        
        core._liner.transform_resume_value = transform_fn
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(initial_state, config):
            captured_args["initial_state"] = initial_state
            captured_args["config"] = config
            return original_invoke(initial_state, config)
        
        core._invoke = mock_invoke
        
        resume_value = {"approval": "granted"}
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, resume_value)
        
        # Verify the initial_state passed to _invoke is a Command with the transformed resume_value
        assert isinstance(captured_args["initial_state"], Command)
        assert captured_args["initial_state"].resume == {"transformed": True, "original": resume_value}


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

    def test_retry_calls_on_retry_hook(self):
        """When liner has on_retry method, retry calls it."""
        core = _make_core(_error_graph)
        
        # Add on_retry method to liner
        on_retry_called = {}
        
        def on_retry_fn(thread_id, checkpoint_id):
            on_retry_called["called"] = True
            on_retry_called["thread_id"] = thread_id
            on_retry_called["checkpoint_id"] = checkpoint_id
        
        core._liner.on_retry = on_retry_fn
        
        # First call: error
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"}, thread_id="t-hook")
        
        err = exc_info.value
        checkpoint_id = err.get_checkpoint_id()
        
        # Retry
        result = core.retry(err.get_thread_id(), checkpoint_id)
        
        # Verify on_retry was called
        assert on_retry_called["called"]
        assert on_retry_called["thread_id"] == err.get_thread_id()
        assert on_retry_called["checkpoint_id"] == checkpoint_id

    def test_retry_on_retry_hook_throws_logs_stderr(self, capsys):
        """When on_retry hook throws, stderr is logged and error RunResult is returned."""
        core = _make_core(_error_graph)
        
        # Add on_retry method that throws
        def bad_on_retry_fn(thread_id, checkpoint_id):
            raise RuntimeError("on_retry failed")
        
        core._liner.on_retry = bad_on_retry_fn
        
        # First call: error
        with pytest.raises(GraphExecutionError) as exc_info:
            core.run({"value": "start"}, thread_id="t-hook-error")
        
        err = exc_info.value
        checkpoint_id = err.get_checkpoint_id()
        
        # Retry - should return error RunResult because on_retry hook threw
        result = core.retry(err.get_thread_id(), checkpoint_id)
        
        # Verify stderr was logged
        captured = capsys.readouterr()
        assert captured.err != ""
        assert "on_retry failed" in captured.err
        
        # Verify result is an error
        assert result.final_result is None
        assert result.error_message  # truthy
        assert "on_retry" in result.error_message

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
    def test_build_run_result_with_transform(self):
        """Test _build_run_result when liner has transform_run_result method."""
        core = _make_core(_simple_graph)

        # Mock transform_run_result to modify the result
        def transform_fn(result):
            result.final_result = {"modified": True}
            return result

        core._liner.transform_run_result = transform_fn

        result = core._build_run_result(
            thread_id="t1", final_result={"original": True}
        )

        assert result.final_result == {"modified": True}

    def test_build_run_result_without_transform(self):
        """Test _build_run_result when liner doesn't have transform_run_result."""
        core = _make_core(_simple_graph)

        # Ensure transform_run_result doesn't exist
        assert not hasattr(core._liner, "transform_run_result")

        result = core._build_run_result(
            thread_id="t1", final_result={"value": "test"}
        )

        # Result should pass through without modification
        assert result.final_result == {"value": "test"}
        assert result.error_message is None


# ---------------------------------------------------------------------------
# ExosuitCore._log_and_create_error_result
# ---------------------------------------------------------------------------

class TestExosuitCoreLogAndCreateErrorResult:
    def test_log_and_create_error_result_with_prefix(self, capsys):
        """Test _log_and_create_error_result with error_prefix."""
        core = _make_core(_simple_graph)
        exc = ValueError("test error")

        result = core._log_and_create_error_result(
            exc=exc,
            thread_id="t1",
            error_prefix="Custom prefix",
            checkpoint_id="cid1",
        )

        # Verify stderr was written to
        captured = capsys.readouterr()
        assert "test error" in captured.err
        assert "ValueError" in captured.err

        # Verify result is valid and has expected error format
        assert result.final_result is None
        assert result.interrupt_value is None
        assert result.error_message is not None
        assert "Custom prefix" in result.error_message
        assert "test error" in result.error_message
        assert result.thread_id == "t1"
        assert result.checkpoint_id == "cid1"

    def test_log_and_create_error_result_without_prefix(self, capsys):
        """Test _log_and_create_error_result without error_prefix."""
        core = _make_core(_simple_graph)
        exc = RuntimeError("boom")

        result = core._log_and_create_error_result(
            exc=exc,
            thread_id="t2",
            checkpoint_id="cid2",
        )

        # Verify stderr was written to
        captured = capsys.readouterr()
        assert "boom" in captured.err
        assert "RuntimeError" in captured.err

        # Verify result is valid and has expected error format
        assert result.final_result is None
        assert result.interrupt_value is None
        assert result.error_message is not None
        assert result.error_message == "boom"
        assert result.thread_id == "t2"
        assert result.checkpoint_id == "cid2"


# ---------------------------------------------------------------------------
# ExosuitCore compile responsibility
# ---------------------------------------------------------------------------

class TestExosuitCoreCompile:
    def test_accepts_precompiled_graph(self):
        """ExosuitCore must accept a Liner instance with a pre-compiled graph."""
        # Create a StateGraph and compile it with a checkpointer
        graph = _simple_graph()
        checkpointer = MemorySaver()
        compiled = graph.compile(checkpointer=checkpointer)

        # Compiled graph should not be a StateGraph
        from langgraph.graph.state import StateGraph as LangGraphStateGraph
        assert not isinstance(compiled, LangGraphStateGraph)

        class TestLiner(ExosuitLiner):
            def get_graph(self) -> Any:
                return compiled

            def get_checkpointer_cm(self) -> Any:
                return _CheckpointerContextManager(checkpointer)

        core = ExosuitCore(TestLiner())
        result = core.run({"value": "test"})
        assert result.final_result is not None
        assert result.final_result == {"value": "test_done"}

    def test_accepts_uncompiled_state_graph(self):
        """ExosuitCore accepts and compiles an uncompiled StateGraph from get_graph."""
        # Return an uncompiled StateGraph (not calling .compile())
        uncompiled = _simple_graph()

        checkpointer = MemorySaver()

        class TestLiner(ExosuitLiner):
            def get_graph(self) -> Any:
                return uncompiled

            def get_checkpointer_cm(self) -> Any:
                return _CheckpointerContextManager(checkpointer)

        # Should not raise; ExosuitCore should compile it for us
        core = ExosuitCore(TestLiner())
        result = core.run({"value": "test"})
        assert result.final_result is not None
        assert result.final_result == {"value": "test_done"}

    def test_uncompiled_state_graph_compiles_with_correct_checkpointer(self):
        """ExosuitCore compiles uncompiled StateGraph using the correct checkpointer."""
        uncompiled = _simple_graph()
        checkpointer = MemorySaver()

        class TestLiner(ExosuitLiner):
            def get_graph(self) -> Any:
                return uncompiled

            def get_checkpointer_cm(self) -> Any:
                return _CheckpointerContextManager(checkpointer)

        core = ExosuitCore(TestLiner())
        # Run and pause to verify checkpointer is set up correctly
        core_with_interrupt = _make_core(_interrupt_graph, precompile=False)
        result = core_with_interrupt.run({"value": "start"}, thread_id="t1")
        
        # Should pause with a checkpoint
        assert result.interrupt_value is not None
        assert result.checkpoint_id is not None

