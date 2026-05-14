"""Tests for graphexosuitcli CLI commands."""

from __future__ import annotations

import io
import json
import sys
import types as _types
from typing import Any, TypedDict

from typer.testing import CliRunner

from graphexosuit.core import ExosuitLiner, GraphExecutionError
from graphexosuit.layer.cli import CliApp


# ---------------------------------------------------------------------------
# Fixture: minimal in-process graph module with Liner-compatible class
# ---------------------------------------------------------------------------
# The checkpointer is a module-level singleton so that state is preserved
# across multiple CLI invocations within the same test.

class _State(TypedDict):
    value: str


# Separate call counters per thread scenario to avoid cross-test pollution.
_fail_call_count: dict[str, int] = {}


def _get_graph():
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
            # Only fail the very first execution of this thread
            _fail_call_count[value] = _fail_call_count.get(value, 0) + 1
            if _fail_call_count[value] == 1:
                raise RuntimeError("deliberate failure")
        return {"value": value + "_done"}

    builder.add_node("node", node)
    builder.set_entry_point("node")
    builder.set_finish_point("node")
    return builder.compile(checkpointer=_get_checkpointer())


# Singleton checkpointer shared across all CLI calls in this test session
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
        return _get_graph()

    def get_checkpointer_cm(self) -> Any:
        return _CheckpointerContextManager(_get_checkpointer())


# Register fake module on sys.modules so graph_loader can import it
_FAKE_MODULE = "fake_graph_module"
_fake_mod = _types.ModuleType(_FAKE_MODULE)
setattr(_fake_mod, "_TestLiner", _TestLiner)
sys.modules[_FAKE_MODULE] = _fake_mod


# Use mix_stderr=False so that stderr (tracebacks) don't pollute stdout JSON
runner = CliRunner()


def _parse_json(output: str) -> dict:
    """Extract JSON from CLI output (supports multi-line formatted JSON)."""
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(output.strip())
    return obj


def _get_cli():
    """Create a CliApp instance with a test liner."""
    return CliApp(_TestLiner())


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_to_completion(self):
        cli = _get_cli()
        result = runner.invoke(
            cli.app, ["run", "--initial-state", '{"value": "hello"}']
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["final_result"] is not None
        assert data["final_result"]["value"] == "hello_done"

    def test_run_with_thread_id(self):
        cli = _get_cli()
        result = runner.invoke(
            cli.app,
            ["run", "--initial-state", '{"value": "hello"}', "--thread-id", "my-thread"],
        )
        assert result.exit_code == 0
        data = _parse_json(result.output)
        assert data["thread_id"] == "my-thread"

    def test_run_invalid_json(self):
        cli = _get_cli()
        result = runner.invoke(cli.app, ["run", "--initial-state", "not-json"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# resume command
# ---------------------------------------------------------------------------

class TestResumeCommand:
    def _get_paused(self):
        """Run until pause, return thread_id and checkpoint_id."""
        cli = _get_cli()
        result = runner.invoke(
            cli.app,
            ["run", "--initial-state", '{"value": "interrupt_me"}', "--thread-id", "t-res"],
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["interrupt_value"] is not None
        return data["thread_id"], data["checkpoint_id"]

    def test_resume_completes(self):
        cli = _get_cli()
        thread_id, checkpoint_id = self._get_paused()
        result = runner.invoke(
            cli.app,
            [
                "resume",
                "--thread-id", thread_id,
                "--checkpoint-id", checkpoint_id,
                "--resume-value", "{}",
            ],
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        # Resume should complete without errors
        assert data["thread_id"] == thread_id

    def test_resume_with_payload(self):
        cli = _get_cli()
        thread_id, checkpoint_id = self._get_paused()
        result = runner.invoke(
            cli.app,
            [
                "resume",
                "--thread-id", thread_id,
                "--checkpoint-id", checkpoint_id,
                "--resume-value", '{"extra": "data"}',
            ],
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["final_result"] is not None

    def test_resume_invalid_payload_json(self):
        cli = _get_cli()
        result = runner.invoke(
            cli.app,
            [
                "resume",
                "--thread-id", "t",
                "--checkpoint-id", "c",
                "--resume-value", "bad-json",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# retry command
# ---------------------------------------------------------------------------

class TestRetryCommand:
    def test_retry_recovers(self):
        cli = _get_cli()
        # First run fails
        result = runner.invoke(
            cli.app,
            ["run", "--initial-state", '{"value": "fail_me"}', "--thread-id", "t-retry"],
        )
        # When the graph execution fails, the CLI exits with error code
        assert result.exit_code != 0
        # Extract thread_id and checkpoint_id from the exception
        assert result.exception is not None
        assert isinstance(result.exception, GraphExecutionError)
        thread_id = result.exception.get_thread_id()
        checkpoint_id = result.exception.get_checkpoint_id()

        result2 = runner.invoke(
            cli.app,
            [
                "retry",
                "--thread-id", thread_id,
                "--checkpoint-id", checkpoint_id,
            ],
        )
        assert result2.exit_code == 0, result2.output
        data2 = _parse_json(result2.output)
        assert data2["final_result"] is not None


# ---------------------------------------------------------------------------
# confess method
# ---------------------------------------------------------------------------

class TestReportExc:
    def test_confess_with_generic_exception(self):
        """confess() should print traceback but no retry tip for generic exceptions."""
        cli = _get_cli()
        generic_exc = ValueError("something went wrong")
        
        # Capture stderr to verify output
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        exit_code_captured = None
        
        def mock_exit(code: int) -> None:
            nonlocal exit_code_captured
            exit_code_captured = code
        
        try:
            sys.stderr = captured_stderr
            cli.confess(generic_exc, exit=mock_exit)
        finally:
            sys.stderr = original_stderr
        
        stderr_output = captured_stderr.getvalue()
        # Should contain traceback but NOT retry tip
        assert "ValueError: something went wrong" in stderr_output
        assert "retry" not in stderr_output
        # Should have called exit(1)
        assert exit_code_captured == 1

    def test_confess_with_graph_execution_error(self):
        """confess() should print traceback AND retry tip for GraphExecutionError."""
        cli = _get_cli()
        exc = GraphExecutionError(
            message="Graph execution failed",
            original_exception=RuntimeError("test failure"),
            thread_id="test-thread",
            checkpoint_id="test-checkpoint",
        )
        
        # Capture stderr to verify output
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        exit_code_captured = None
        
        def mock_exit(code: int) -> None:
            nonlocal exit_code_captured
            exit_code_captured = code
        
        try:
            sys.stderr = captured_stderr
            cli.confess(exc, exit=mock_exit)
        finally:
            sys.stderr = original_stderr
        
        stderr_output = captured_stderr.getvalue()
        # Should contain both traceback and retry tip
        assert "GraphExecutionError" in stderr_output
        assert "retry" in stderr_output
        assert "test-thread" in stderr_output
        assert "test-checkpoint" in stderr_output
        # Should have called exit(1)
        assert exit_code_captured == 1
