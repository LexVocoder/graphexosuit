from __future__ import annotations

import os
from typing import Any, Optional, TypedDict
from graphexosuit import StandardizedInterrupt, InterruptOption
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from graphexosuit.core import RunResult
from graphexosuit.liner import Liner

# Graph nodes

def initialize(state):
    """Standard initialization node that ensures entire initial state is captured in the first checkpoint, making it available for resuming and retrying even if the graph fails or is interrupted immediately."""
    return state

def node(state):
    post_interrupt_data = interrupt(
        StandardizedInterrupt(
            message="Choose",
            options=[
                InterruptOption(id="ok", label="OK"),
                InterruptOption(id="cancel", label="Cancel"),
            ],
        )
    )
    return {"value": post_interrupt_data}


class SimpleState(TypedDict):
    value: Any


class SimpleLiner(Liner):
    def __init__(self):
        """Initialize data persistence.
        Must be idempotent."""

        # Cross-platform parent of the .cache directory
        self.cache_dir = os.path.join(
            os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
            ".cache",
            "graphexosuit-samples-interrupt",
        )

        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_checkpoint_db_path(self) -> str:
        return os.path.join(self.cache_dir, "checkpoints.db")

    def get_graph(self) -> StateGraph:

        builder = StateGraph(SimpleState)
        builder.add_node("initialize", initialize)
        builder.add_node("node", node)

        builder.set_entry_point("initialize")
        builder.add_edge("initialize", "node")
        builder.set_finish_point("node")
        return builder

    def get_checkpointer(self):
        return SqliteSaver.from_conn_string(self._get_checkpoint_db_path())

    def transform_result(self, result: RunResult) -> RunResult:
        if result.completed:
            # Delete cache folder and all contents upon *successful* completion.
            # If we delete it on failure or interrupt, we won't be able to resume or retry.
            os.unlink(self._get_checkpoint_db_path())
            os.rmdir(self.cache_dir)

        return result
