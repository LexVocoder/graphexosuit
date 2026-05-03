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
    ResumeValue,
    RunResult,
    StandardizedInterrupt,
    _validate_run_result,
    _validate_interrupt_value,
    _validate_resume_value,
)
from graphexosuit.liner import Liner


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


def _make_core(graph_fn) -> ExosuitCore:
    class TestLiner:
        def get_graph(self) -> StateGraph:
            return graph_fn()

        def get_checkpointer(self) -> Any:
            return MemorySaver()

    return ExosuitCore(TestLiner())


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

    def test_run_invalid_interrupt_returns_error_result(self):
        core = _make_core(_invalid_interrupt_graph)
        result = core.run({"value": "start"})
        assert not result.completed
        assert not result.paused
        assert result.error is not None
        # Error can be due to serialization or validation
        assert result.error != ""

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

    def test_resume_malformed_resume_value_no_stderr_logging(self, capsys):
        """Malformed resume_value returns error but does NOT log to stderr (it's a client error)."""
        core, run_result = self._paused_core()
        bad = MagicMock(spec=["id"])  # missing payload
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, bad)
        
        # Verify stderr is empty (no logging)
        captured = capsys.readouterr()
        assert captured.err == ""
        
        # Verify result is an error
        assert not result.completed
        assert result.error is not None
        assert "ResumeValue" in result.error

    def test_resume_without_transform_passes_original_to_invoke(self):
        """When liner has no transform_resume_value, original resume_value is passed in Command to _invoke."""
        core, run_result = self._paused_core()
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(state, config):
            captured_args["state"] = state
            captured_args["config"] = config
            return original_invoke(state, config)
        
        core._invoke = mock_invoke
        
        # Verify transform_resume_value does not exist
        assert not hasattr(core._liner, "transform_resume_value")
        
        rv = ResumeValue(id="approve", payload={"key": "value"})
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, rv)
        
        # Verify the state passed to _invoke is a Command with the original resume_value
        assert isinstance(captured_args["state"], Command)
        assert captured_args["state"].resume == rv

    def test_resume_with_transform_passes_transformed_to_invoke(self):
        """When liner has transform_resume_value, transformed resume_value is passed in Command to _invoke."""
        core, run_result = self._paused_core()
        
        # Add transform_resume_value to liner
        def transform_fn(rv):
            return ResumeValue(id=rv.id + "_transformed", payload=rv.payload)
        
        core._liner.transform_resume_value = transform_fn
        
        # Mock _invoke to capture what it receives
        original_invoke = core._invoke
        captured_args = {}
        
        def mock_invoke(state, config):
            captured_args["state"] = state
            captured_args["config"] = config
            return original_invoke(state, config)
        
        core._invoke = mock_invoke
        
        rv = ResumeValue(id="approve", payload=None)
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, rv)
        
        # Verify the state passed to _invoke is a Command with the transformed resume_value
        assert isinstance(captured_args["state"], Command)
        assert captured_args["state"].resume.id == "approve_transformed"

    def test_resume_transformed_malformed_logs_stderr(self, capsys):
        """When transformed resume_value is malformed, logs to stderr and returns error RunResult."""
        core, run_result = self._paused_core()
        
        # Add transform_resume_value that returns a malformed value
        def bad_transform_fn(rv):
            return MagicMock(spec=["id"])  # missing payload
        
        core._liner.transform_resume_value = bad_transform_fn
        
        rv = ResumeValue(id="approve", payload=None)
        result = core.resume(run_result.thread_id, run_result.checkpoint_id, rv)
        
        # Verify stderr was written to (error in transform)
        captured = capsys.readouterr()
        assert captured.err != ""
        assert "ResumeValue" in captured.err
        
        # Verify result is an error
        assert not result.completed
        assert result.error  # truthy
        assert "Transformed resume value is not well-formed" in result.error


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
        err_result = core.run({"value": "start"}, thread_id="t-hook")
        assert err_result.error
        
        # Retry
        result = core.retry(err_result.thread_id, err_result.checkpoint_id)
        
        # Verify on_retry was called
        assert on_retry_called["called"]
        assert on_retry_called["thread_id"] == err_result.thread_id
        assert on_retry_called["checkpoint_id"] == err_result.checkpoint_id

    def test_retry_on_retry_hook_throws_logs_stderr(self, capsys):
        """When on_retry hook throws, stderr is logged and error RunResult is returned."""
        core = _make_core(_error_graph)
        
        # Add on_retry method that throws
        def bad_on_retry_fn(thread_id, checkpoint_id):
            raise RuntimeError("on_retry failed")
        
        core._liner.on_retry = bad_on_retry_fn
        
        # First call: error
        err_result = core.run({"value": "start"}, thread_id="t-hook-error")
        assert err_result.error
        
        # Retry
        result = core.retry(err_result.thread_id, err_result.checkpoint_id)
        
        # Verify stderr was logged
        captured = capsys.readouterr()
        assert captured.err != ""
        assert "on_retry failed" in captured.err
        
        # Verify result is an error
        assert not result.completed
        assert result.error  # truthy
        assert "on_retry" in result.error

    def test_retry_get_state_next_falsy_no_stderr(self, capsys):
        """When get_state().next is falsy, no stderr logged but error returned."""
        core = _make_core(_simple_graph)
        run_result = core.run({"value": "x"}, thread_id="t-no-next")
        
        # A completed run has no pending node — retry should report an error
        result = core.retry(run_result.thread_id, run_result.checkpoint_id)
        
        # Verify stderr is empty (no exception logged)
        captured = capsys.readouterr()
        assert captured.err == ""
        
        # Verify result is an error
        assert not result.completed
        assert result.error  # truthy
        assert "No failed node found" in result.error

    def test_retry_get_state_raises_logs_stderr(self, capsys):
        """When get_state() raises an exception, stderr is logged and error returned."""
        core = _make_core(_simple_graph)
        run_result = core.run({"value": "x"}, thread_id="t-get-state-error")
        
        # Mock get_state to raise an exception
        original_get_state = core._graph_app.get_state
        
        def bad_get_state(config):
            raise RuntimeError("get_state failed")
        
        core._graph_app.get_state = bad_get_state
        
        # Retry
        result = core.retry(run_result.thread_id, run_result.checkpoint_id)
        
        # Verify stderr was logged
        captured = capsys.readouterr()
        assert captured.err != ""
        assert "get_state failed" in captured.err
        
        # Verify result is an error
        assert not result.completed
        assert result.error  # truthy
        assert "Error retrieving state snapshot" in result.error


# ---------------------------------------------------------------------------
# ExosuitCore._build_run_result
# ---------------------------------------------------------------------------

class TestExosuitCoreBuildRunResult:
    def test_build_run_result_with_transform(self):
        """Test _build_run_result when liner has transform_run_result method."""
        core = _make_core(_simple_graph)

        # Mock transform_run_result to modify the result
        def transform_fn(result):
            result.result = {"modified": True}
            return result

        core._liner.transform_run_result = transform_fn

        result = core._build_run_result(
            completed=True, thread_id="t1", result={"original": True}
        )

        assert result.result == {"modified": True}

    def test_build_run_result_without_transform(self):
        """Test _build_run_result when liner doesn't have transform_run_result."""
        core = _make_core(_simple_graph)

        # Ensure transform_run_result doesn't exist
        assert not hasattr(core._liner, "transform_run_result")

        result = core._build_run_result(
            completed=True, thread_id="t1", result={"value": "test"}
        )

        # Result should pass through without modification
        assert result.result == {"value": "test"}
        assert result.completed


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
        assert not result.completed
        assert not result.paused
        assert result.error is not None
        assert "Custom prefix" in result.error
        assert "test error" in result.error
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
        assert not result.completed
        assert not result.paused
        assert result.error is not None
        assert result.error == "boom"
        assert result.thread_id == "t2"
        assert result.checkpoint_id == "cid2"


# ---------------------------------------------------------------------------
# ExosuitCore compile responsibility
# ---------------------------------------------------------------------------

class TestExosuitCoreCompile:
    def test_accepts_uncompiled_graph(self):
        """ExosuitCore must accept a Liner instance with uncompiled graph."""
        uncompiled = _simple_graph()
        # Should NOT be a CompiledStateGraph yet
        from langgraph.graph.state import CompiledStateGraph
        assert not isinstance(uncompiled, CompiledStateGraph)

        class TestLiner(Liner):
            def get_graph(self) -> StateGraph:
                return uncompiled

            def get_checkpointer(self) -> Any:
                return MemorySaver()

        core = ExosuitCore(TestLiner())
        result = core.run({"value": "test"})
        assert result.completed
