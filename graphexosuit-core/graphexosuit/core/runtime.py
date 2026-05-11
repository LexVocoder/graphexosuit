"""Core data structures, validation, and execution logic for graphexosuit."""

from __future__ import annotations

import sys
import traceback
import uuid
from dataclasses import dataclass, field
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import StateGraph
from langgraph.types import Command
from typing import Any, Optional, cast


@dataclass
class InterruptOption:
    """A selectable option presented to the user during a graph interrupt.

    Duck-typed: any object with ``label`` and ``payload`` attributes works.
    """

    label: str
    payload: Any


@dataclass
class StandardizedInterrupt:
    """The interrupt value that graph nodes must pass to ``interrupt()``.

    Duck-typed: any object with ``message`` and ``options`` attributes works.
    """

    message: str
    options: list[InterruptOption]


@dataclass
class RunResult:
    """The outcome of a graph execution, pause, or error.

    Exactly one of error_message, interrupt_value, or final_result is non-None.
    """

    thread_id: str
    checkpoint_id: Optional[str] = None
    error_message: Optional[str] = None
    interrupt_value: Optional[StandardizedInterrupt] = None
    final_result: Optional[dict] = None

    def __post_init__(self) -> None:
        _validate_run_result(self)


def _validate_run_result(result: RunResult) -> None:
    """Raise ValueError if RunResult is in an inconsistent state.

    Exactly one of error_message, interrupt_value, or final_result must be non-None.
    If interrupt_value or error_message is set, checkpoint_id must also be set.
    """
    has_completion = result.final_result is not None
    has_error = result.error_message is not None
    has_interrupt = result.interrupt_value is not None

    terminal_states = sum([has_completion, has_error, has_interrupt])
    if terminal_states != 1:
        raise ValueError(
            "RunResult: exactly one of final_result, error_message, or interrupt_value must be set"
        )

    if has_interrupt and result.checkpoint_id is None:
        raise ValueError(
            "RunResult: interrupt_value set requires checkpoint_id to be set"
        )

    if has_error and result.checkpoint_id is None:
        raise ValueError(
            "RunResult: error_message set requires checkpoint_id to be set"
        )


def _validate_interrupt_value(value: Any) -> None:
    """Raise ValueError if *value* does not satisfy the StandardizedInterrupt duck type."""
    if not (hasattr(value, "message") and hasattr(value, "options")):
        raise ValueError(
            "Interrupt must have 'message' and 'options' attributes"
        )
    for option in value.options:
        if not (hasattr(option, "label") and hasattr(option, "payload")):
            raise ValueError(
                "Each interrupt option must have 'label' and 'payload' attributes"
            )


def _extract_checkpoint_id(graph: Any, config: RunnableConfig) -> Optional[str]:
    """Return the latest checkpoint ID from the graph state."""
    state = graph.get_state(config)
    return state.config["configurable"].get("checkpoint_id")


class ExosuitCore:
    """Thin runtime wrapper around a LangGraph workflow.

    The constructor accepts a Liner-compatible instance that exposes
    ``get_graph()`` and ``get_checkpointer()`` methods.

    Parameters
    ----------
    liner:
        A Liner-compatible instance that provides ``get_graph()`` and
        ``get_checkpointer()`` methods.
    """
    def __init__(self, liner: Any) -> None:
        self._liner = liner
        graph = liner.get_graph()
        
        # Enter the checkpointer context manager and store it for cleanup in __del__
        self._checkpointer_cm = liner.get_checkpointer()
        checkpointer = self._checkpointer_cm.__enter__()

        if isinstance(graph, StateGraph):
            # Compile it for them
            self._graph_app = graph.compile(checkpointer=checkpointer)
        else:
            self._graph_app = graph

        # Register graphexosuit types with the serializer to prevent deserialization warnings
        checkpointer.serde = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("graphexosuit.core.runtime", "InterruptOption"),
                ("graphexosuit.core.runtime", "StandardizedInterrupt"),
            ]
        )

    def __del__(self) -> None:
        """Exit the checkpointer context manager on cleanup."""
        if hasattr(self, '_checkpointer_cm'):
            self._checkpointer_cm.__exit__(None, None, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_run_result(
            self,
            thread_id: str,
            checkpoint_id: Optional[str] = None,
            error_message: Optional[str] = None,
            interrupt_value: Optional[StandardizedInterrupt] = None,
            final_result: Optional[dict] = None,
    ) -> RunResult:
        """Helper to construct a RunResult with optional transformation & validation."""
        run_result = RunResult(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            error_message=error_message,
            interrupt_value=interrupt_value,
            final_result=final_result,
        )

        if hasattr(self._liner, "transform_run_result"):
            run_result = self._liner.transform_run_result(run_result)

        _validate_run_result(run_result)
        return run_result

    def _log_and_create_error_result(
            self,
            exc: Exception,
            thread_id: str,
            checkpoint_id: str,
            error_prefix: Optional[str] = None,
    ) -> RunResult:

        traceback.print_exception(exc, file=sys.stderr)

        run_result = self._build_run_result(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                error_message=f"{error_prefix}: {exc}" if error_prefix else str(exc),
            )

        return run_result

    def _invoke(self,
                initial_state: Any,
                config: RunnableConfig,
                ) -> RunResult:
        """Invoke the graph and return a RunResult, handling pauses and errors."""
        # configurable key is guaranteed to exist; all config dicts are created with it by this class
        thread_id: str = cast(dict, config)["configurable"]["thread_id"]

        try:
            output = self._graph_app.invoke(initial_state, config=config, durability='sync')
        except Exception as exc:
            # An error occurred during graph execution. It could be anything.
            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return self._log_and_create_error_result(
                exc=exc,
                thread_id=thread_id,
                error_prefix="Error during graph execution",
                checkpoint_id=checkpoint_id if checkpoint_id else "unknown",
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
                    checkpoint_id=checkpoint_id if checkpoint_id else "unknown",
                )

            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return self._build_run_result(
                thread_id=thread_id,
                interrupt_value=interrupt_obj,
                checkpoint_id=checkpoint_id,
            )

        return self._build_run_result(
            thread_id=thread_id,
            final_result=output if isinstance(output, dict) else {"output": output},
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
        config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})

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
            The payload to send back to the paused node (typically a dict).
        """

        if hasattr(self._liner, "transform_resume_value"):
            resume_value = self._liner.transform_resume_value(resume_value)

        config = cast(RunnableConfig, {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        })
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

        config = cast(RunnableConfig, {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        })

        # None is a magic value meaning "resume from last checkpoint"
        return self._invoke(None, config)
