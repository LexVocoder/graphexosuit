#!/usr/bin/env -S uv run

# # interrupt.py

"""Graph that demonstrates a node that calls interrupt(), wrapped in a command-line interface that allows for resuming after the interrupt."""

from __future__ import annotations

import os
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from graphexosuit.core import StandardizedInterrupt, InterruptOption, ExosuitLiner

# Graph nodes

def initialize(state):
    """Standard initialization node that ensures entire initial state is both valid and captured in the first checkpoint, making it available for resuming and retrying even if the graph fails or is interrupted immediately thereafter."""

    if not state or "value" not in state:
        raise KeyError(f"Initial state must have 'value' key; got {repr(state)}")

    return state

def node(state):
    post_interrupt_data = interrupt(
        StandardizedInterrupt(
            message="Choose an ice cream flavor",
            options=[
                InterruptOption(label="I prefer chocolate", payload={"flavor": "chocolate"}),
                InterruptOption(label="I prefer vanilla", payload={"flavor": "vanilla"}),
            ],
        )
    )
    return {"value": post_interrupt_data}


class SimpleState(TypedDict):
    value: Any


class InterruptLiner(ExosuitLiner):
    def __init__(self):
        pass

    def get_checkpointer(self) -> Any:
        # Cross-platform parent of the .cache directory
        cache_dir = os.path.join(
            os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
            ".cache",
            "graphexosuit-samples-interrupt",
        )
        os.makedirs(cache_dir, exist_ok=True)

        path_to_db = os.path.join(cache_dir, "checkpoints.db")

        return SqliteSaver.from_conn_string(path_to_db)

    def get_graph(self) -> StateGraph:
        builder = StateGraph(SimpleState)
        builder.add_node("initialize", initialize)
        builder.add_node("node", node)

        builder.set_entry_point("initialize")
        builder.add_edge("initialize", "node")
        builder.set_finish_point("node")
        return builder

if __name__ == "__main__":
    from graphexosuit.layer.cli import main
    os.environ["GRAPHEXOSUIT_LINER_CLASS"] = f"interrupt:{InterruptLiner.__name__}"
    main()
