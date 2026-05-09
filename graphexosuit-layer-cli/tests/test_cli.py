"""Tests for graphexosuitcli CLI commands."""

from __future__ import annotations

import json
import sys
import types as _types
from typing import Any, TypedDict

from typer.testing import CliRunner

from graphexosuit.core import ExosuitLiner
from graphexosuit.layer.cli import app


# ---------------------------------------------------------------------------
# Fixture: minimal in-process graph module with Liner-compatible class
# ---------------------------------------------------------------------------
# The checkpointer is a module-level singleton so that state is preserved
# across multiple CLI invocations within the same test.

class _State(TypedDict):
    value: str


# Separate call counters per thread scenario to avoid cross-test pollution.
_fail_call_count: dict[str, int] = {}


def _get_compiled_graph():
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


def _get_checkpointer():
    return _shared_checkpointer


class _TestLiner(ExosuitLiner):
    """Liner-compatible class for testing."""

    def get_compiled_graph(self) -> Any:
        return _get_compiled_graph()

    def get_checkpointer(self) -> Any:
        return _get_checkpointer()


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


def _env():
    return {"GRAPHEXOSUIT_LINER_CLASS": f"{_FAKE_MODULE}:_TestLiner"}


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_to_completion(self):
        result = runner.invoke(
            app, ["run", "--initial-state", '{"value": "hello"}'], env=_env()
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["final_result"] is not None
        assert data["final_result"]["value"] == "hello_done"

    def test_run_with_thread_id(self):
        result = runner.invoke(
            app,
            ["run", "--initial-state", '{"value": "hello"}', "--thread-id", "my-thread"],
            env=_env(),
        )
        assert result.exit_code == 0
        data = _parse_json(result.output)
        assert data["thread_id"] == "my-thread"

    def test_run_invalid_json(self):
        result = runner.invoke(app, ["run", "--initial-state", "not-json"], env=_env())
        assert result.exit_code != 0

    def test_run_missing_env_var(self):
        result = runner.invoke(app, ["run", "--initial-state", '{"value": "x"}'])
        # Should fail because GRAPHEXOSUIT_LINER_CLASS is not set
        assert result.exit_code != 0 or "not set" in result.output


# ---------------------------------------------------------------------------
# resume command
# ---------------------------------------------------------------------------

class TestResumeCommand:
    def _get_paused(self):
        """Run until pause, return thread_id and checkpoint_id."""
        result = runner.invoke(
            app,
            ["run", "--initial-state", '{"value": "interrupt_me"}', "--thread-id", "t-res"],
            env=_env(),
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["interrupt_value"] is not None
        return data["thread_id"], data["checkpoint_id"]

    def test_resume_completes(self):
        thread_id, checkpoint_id = self._get_paused()
        result = runner.invoke(
            app,
            [
                "resume",
                "--thread-id", thread_id,
                "--checkpoint-id", checkpoint_id,
                "--resume-value", "{}",
            ],
            env=_env(),
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        # Resume should complete without errors
        assert data["thread_id"] == thread_id

    def test_resume_with_payload(self):
        thread_id, checkpoint_id = self._get_paused()
        result = runner.invoke(
            app,
            [
                "resume",
                "--thread-id", thread_id,
                "--checkpoint-id", checkpoint_id,
                "--resume-value", '{"extra": "data"}',
            ],
            env=_env(),
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["final_result"] is not None

    def test_resume_invalid_payload_json(self):
        result = runner.invoke(
            app,
            [
                "resume",
                "--thread-id", "t",
                "--checkpoint-id", "c",
                "--resume-value", "bad-json",
            ],
            env=_env(),
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# retry command
# ---------------------------------------------------------------------------

class TestRetryCommand:
    def test_retry_recovers(self):
        # First run fails
        result = runner.invoke(
            app,
            ["run", "--initial-state", '{"value": "fail_me"}', "--thread-id", "t-retry"],
            env=_env(),
        )
        assert result.exit_code == 0, result.output
        data = _parse_json(result.output)
        assert data["error_message"] is not None

        result2 = runner.invoke(
            app,
            [
                "retry",
                "--thread-id", data["thread_id"],
                "--checkpoint-id", data["checkpoint_id"],
            ],
            env=_env(),
        )
        assert result2.exit_code == 0, result2.output
        data2 = _parse_json(result2.output)
        assert data2["final_result"] is not None
