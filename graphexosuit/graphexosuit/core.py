"""Core data structures, validation, and execution logic for graphexosuit."""

from __future__ import annotations

import sys
import traceback
import uuid
from dataclasses import dataclass, field
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
    interrupt_value: Optional[Any] = None
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
    """Return the latest checkpoint ID from the graph state, or None."""
    try:
        state = graph.get_state(config)
        return state.config["configurable"].get("checkpoint_id")
    except Exception:
        return None


class ExosuitCore:
    """Thin runtime wrapper around a compiled LangGraph workflow.

    The constructor accepts an *uncompiled* ``StateGraph`` (or any object that
    exposes a ``compile(checkpointer=...)`` method) and a checkpointer, then
    calls ``compile()`` itself.

    Parameters
    ----------
    state_graph:
        An uncompiled ``StateGraph`` returned by the developer's ``get_graph()``.
    checkpointer:
        A LangGraph checkpointer instance returned by ``get_checkpointer()``.
    """

    def __init__(self, state_graph: Any, checkpointer: Any) -> None:
        self._graph_app = state_graph.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _invoke(self, input_data: Any, config: dict) -> RunResult:
        """Invoke the graph and return a RunResult, handling pauses and errors."""
        thread_id: str = config["configurable"]["thread_id"]

        try:
            output = self._graph_app.invoke(input_data, config=config)
        except Exception as exc:
            # Log full traceback to stderr for operational debugging
            traceback.print_exc(file=sys.stderr)
            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return RunResult(
                completed=False,
                thread_id=thread_id,
                error=str(exc),
                checkpoint_id=checkpoint_id,
                paused=False,
            )

        # LangGraph signals an interrupt by including __interrupt__ in the output
        interrupts = output.get("__interrupt__", []) if isinstance(output, dict) else []
        if interrupts:
            interrupt_obj = interrupts[0].value
            try:
                _validate_interrupt_value(interrupt_obj)
            except ValueError as exc:
                checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
                return RunResult(
                    completed=False,
                    thread_id=thread_id,
                    error=str(exc),
                    checkpoint_id=checkpoint_id,
                    paused=False,
                )

            checkpoint_id = _extract_checkpoint_id(self._graph_app, config)
            return RunResult(
                completed=False,
                thread_id=thread_id,
                paused=True,
                interrupt_value=interrupt_obj,
                checkpoint_id=checkpoint_id,
            )

        return RunResult(
            completed=True,
            thread_id=thread_id,
            result=output if isinstance(output, dict) else {"output": output},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        input_data: dict,
        thread_id: Optional[str] = None,
    ) -> RunResult:
        """Execute the graph from the beginning.

        Parameters
        ----------
        input_data:
            Initial state passed to the graph.
        thread_id:
            Optional identifier.  A UUID is generated when omitted.
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        return self._invoke(input_data, config)

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
            return RunResult(
                completed=False,
                thread_id=thread_id,
                error=str(exc),
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

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        try:
            state_snapshot = self._graph_app.get_state(config)
            if not state_snapshot.next:
                return RunResult(
                    completed=False,
                    thread_id=thread_id,
                    error="No failed node found in state snapshot to retry",
                )
            failed_node = state_snapshot.next[0]
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            return RunResult(
                completed=False,
                thread_id=thread_id,
                error=str(exc),
            )

        return self._invoke(Command(goto=failed_node), config)
