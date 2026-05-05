"""Core data structures, validation, and execution logic for graphexosuit."""

from __future__ import annotations

import sys
import traceback
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, field
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import StateGraph
from langgraph.types import Command
from typing import Any, Optional


@dataclass
class InterruptOption:
    """A selectable option presented to the user during a graph interrupt.

    Duck-typed: any object with ``id``, ``label``, and optional ``payload`` works.
    """

    id: str
    label: str
    payload: Optional[dict] = None


@dataclass
class StandardizedInterrupt:
    """The interrupt value that graph nodes must pass to ``interrupt()``.

    Duck-typed: any object with ``message`` and ``options`` attributes works.
    """

    message: str
    options: list[InterruptOption]


@dataclass
class ResumeValue:
    """The value sent back to a paused node when resuming execution.

    Duck-typed: any object with ``id`` and ``payload`` attributes works.
    """

    id: str
    payload: Optional[dict] = None


@dataclass
class RunResult:
    """The outcome of a graph execution, pause, or error."""

    completed: bool
    thread_id: str
    checkpoint_id: Optional[str] = None
    error: Optional[str] = None
    interrupt_value: Optional[StandardizedInterrupt] = None
    paused: bool = False
    result: Optional[dict] = None

    def __post_init__(self) -> None:
        _validate_run_result(self)


def _validate_run_result(result: RunResult) -> None:
    """Raise ValueError if RunResult is in an inconsistent state."""
    if result.completed:
        if result.error:
            raise ValueError(
                "RunResult: completed=True is incompatible with error being set"
            )
        if result.paused:
            raise ValueError(
                "RunResult: completed=True is incompatible with paused=True"
            )
    elif result.paused:
        if result.interrupt_value is None:
            raise ValueError(
                "RunResult: paused=True requires interrupt_value to be set"
            )
        if result.checkpoint_id is None:
            raise ValueError(
                "RunResult: paused=True requires checkpoint_id to be set"
            )
    else:
        # completed=False, paused=False  →  must have an error
        if not result.error:
            raise ValueError(
                "RunResult: completed=False and paused=False requires error to be set"
            )


def _validate_interrupt_value(value: Any) -> None:
    """Raise ValueError if *value* does not satisfy the StandardizedInterrupt duck type."""
    if not (hasattr(value, "message") and hasattr(value, "options")):
        raise ValueError(
            "Interrupt must have 'message' and 'options' attributes"
        )
    for option in value.options:
        if not (hasattr(option, "id") and hasattr(option, "label")):
            raise ValueError(
                "Each interrupt option must have 'id' and 'label' attributes"
            )


def _validate_resume_value(value: Any) -> None:
    """Raise ValueError if *value* does not satisfy the ResumeValue duck type."""
    if not (hasattr(value, "id") and hasattr(value, "payload")):
        raise ValueError(
            "ResumeValue must have 'id' and 'payload' attributes"
        )


def _extract_checkpoint_id(graph: Any, config: dict) -> Optional[str]:
    """Return the latest checkpoint ID from the graph state."""
    state = graph.get_state(config)
    return state.config["configurable"].get("checkpoint_id")


class ExosuitCore:
    """Thin runtime wrapper around a compiled LangGraph workflow.

    The constructor accepts a Liner-compatible instance that exposes
    ``get_compiled_graph()`` and ``get_checkpointer()`` methods.

    Parameters
    ----------
    liner:
        A Liner-compatible instance that provides ``get_compiled_graph()`` and
        ``get_checkpointer()`` methods.
    """
    def __init__(self, liner: Any) -> None:
        self._liner = liner
        self._graph_app = liner.get_compiled_graph()
        
        # Verify that the graph is compiled, not a bare StateGraph
        if isinstance(self._graph_app, StateGraph):
            raise ValueError(
                "ExosuitCore requires a compiled graph, not a StateGraph. "
                "Ensure your Liner's get_compiled_graph() calls .compile(checkpointer=...) on the graph."
            )
        
        # Use ExitStack to manage the checkpointer context manager lifecycle
        self._exit_stack = ExitStack()
        checkpointer_cm = liner.get_checkpointer()
        checkpointer = self._exit_stack.enter_context(checkpointer_cm)
        
        # Register graphexosuit types with the serializer to prevent deserialization warnings
        checkpointer.serde = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("graphexosuit.core", "ResumeValue"),
                ("graphexosuit.core", "InterruptOption"),
                ("graphexosuit.core", "StandardizedInterrupt"),
            ]
        )

    def close(self) -> None:
        """Close and cleanup the checkpointer context manager."""
        self._exit_stack.close()

    def __del__(self) -> None:
        """Ensure cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_run_result(
            self,
            completed: bool,
            thread_id: str,
            checkpoint_id: Optional[str] = None,
            error: Optional[str] = None,
            interrupt_value: Optional[StandardizedInterrupt] = None,
            paused: bool = False,
            result: Optional[dict] = None,
    ) -> RunResult:
        """Helper to construct a RunResult with optional transformation & validation."""
        run_result = RunResult(
            completed=completed,
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            error=error,
            interrupt_value=interrupt_value,
            paused=paused,
            result=result,
        )

        if hasattr(self._liner, "transform_run_result"):
            run_result = self._liner.transform_run_result(run_result)

        _validate_run_result(run_result)
        return run_result

    def _log_and_create_error_result(
            self,
            exc: Exception,
            thread_id: str,
            error_prefix: Optional[str] = None,
            checkpoint_id: Optional[str] = None,
    ) -> RunResult:

        traceback.print_exception(exc, file=sys.stderr)

        run_result = self._build_run_result(
                completed=False,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                error=f"{error_prefix}: {exc}" if error_prefix else str(exc),
                paused=False,
            )

        return run_result

    def _invoke(self, initial_state: Any, config: dict) -> RunResult:
        """Invoke the graph and return a RunResult, handling pauses and errors."""
        thread_id: str = config["configurable"]["thread_id"]

        try:
            output = self._graph_app.invoke(initial_state, config=config, durability='sync')
        except Exception as exc:
            # An error occurred during graph execution. It could be anything.
            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return self._log_and_create_error_result(
                exc=exc,
                thread_id=thread_id,
                error_prefix="Error during graph execution",
                checkpoint_id=checkpoint_id,
            )

        # LangGraph signals an interrupt by including __interrupt__ in the output
        interrupts = output.get("__interrupt__", []) if isinstance(output, dict) else []
        if interrupts:
            interrupt_obj = interrupts[0].value
            try:
                _validate_interrupt_value(interrupt_obj)
            except ValueError as exc:
                checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
                return self._log_and_create_error_result(
                    exc=exc,
                    thread_id=thread_id,
                    error_prefix=f"Graph returned an invalid interrupt value",
                    checkpoint_id=checkpoint_id,
                )

            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return self._build_run_result(
                completed=False,
                thread_id=thread_id,
                paused=True,
                interrupt_value=interrupt_obj,
                checkpoint_id=checkpoint_id,
            )

        return self._build_run_result(
            completed=True,
            thread_id=thread_id,
            result=output if isinstance(output, dict) else {"output": output},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        initial_state: dict,
        thread_id: Optional[str] = None,
    ) -> RunResult:
        """Execute the graph from the beginning.

        Parameters
        ----------
        initial_state:
            Initial state passed to the graph.
        thread_id:
            Optional identifier.  A UUID is generated when omitted.
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        if hasattr(self._liner, "transform_initial_state"):
            initial_state = self._liner.transform_initial_state(initial_state)

        return self._invoke(initial_state, config)

    def resume(
        self,
        thread_id: str,
        checkpoint_id: str,
        resume_value: Any,
    ) -> RunResult:
        """Resume a paused graph execution.

        Parameters
        ----------
        thread_id:
            Thread identifier of the paused execution.
        checkpoint_id:
            Checkpoint to resume from.
        resume_value:
            Duck-typed ResumeValue with ``.id`` and ``.payload`` attributes.
        """

        try:
            _validate_resume_value(resume_value)
        except ValueError as exc:
            # Client did not provide a well-formed resume value.
            # Don't log stack trace to stderr, because it's a client error.
            return self._build_run_result(
                completed=False,
                error=f"Given resume value is not well-formed: {exc}",
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
            )

        if hasattr(self._liner, "transform_resume_value"):
            resume_value = self._liner.transform_resume_value(resume_value)
            try:
                _validate_resume_value(resume_value)
            except ValueError as exc:
                # Transformed resume value is not well-formed.
                return self._log_and_create_error_result(
                    exc=exc,
                    thread_id=thread_id,
                    error_prefix=f"Transformed resume value is not well-formed",
                    checkpoint_id=checkpoint_id,
                )

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        return self._invoke(Command(resume=resume_value), config)

    def retry(self, thread_id: str, checkpoint_id: str) -> RunResult:
        """Retry a failed graph node from its last checkpoint.

        Parameters
        ----------
        thread_id:
            Thread identifier of the failed execution.
        checkpoint_id:
            Checkpoint at which the failure occurred.
        """

        if hasattr(self._liner, "on_retry"):
            try:
                self._liner.on_retry(thread_id=thread_id, checkpoint_id=checkpoint_id)
            except Exception as exc:
                return self._log_and_create_error_result(
                    exc=exc,
                    thread_id=thread_id,
                    error_prefix="Error in liner's on_retry hook",
                    checkpoint_id=checkpoint_id,
                )

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

        # None is a magic value meaning "resume"
        return self._invoke(None, config)
