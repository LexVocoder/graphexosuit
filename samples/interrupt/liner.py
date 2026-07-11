#!/usr/bin/env -S uv run

# # interrupt.py

"""Graph factory and checkpointer factory for the interrupt sample."""

from __future__ import annotations

import os
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from graphexosuit.core import InterruptOption, StandardizedInterrupt

# Graph nodes

def initialize(state):
    """Standard initialization node that ensures entire initial state is both valid and captured in the first checkpoint, making it available for resuming and retrying even if the graph fails or is interrupted immediately thereafter."""

    print("Initializing graph...")

    if not state or "value" not in state:
        raise KeyError(f"Initial state must have 'value' key; got {repr(state)}")

    return state

def node(state):

    print("Executing node...")

    if state["value"] == "fail":
        raise ValueError("state['value'] was 'fail'")

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


def get_checkpointer_cm() -> Any:
    """Return a context manager that yields a SqliteSaver checkpointer."""
    # Cross-platform parent of the .cache directory
    cache_dir = os.path.join(
        os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
        ".cache",
        "graphexosuit-samples-interrupt",
    )
    os.makedirs(cache_dir, exist_ok=True)

    path_to_db = os.path.join(cache_dir, "checkpoints.db")

    return SqliteSaver.from_conn_string(path_to_db)


def build_graph() -> StateGraph:
    """Return an uncompiled StateGraph for the interrupt sample."""
    builder = StateGraph(SimpleState)
    builder.add_node("initialize", initialize)
    builder.add_node("node", node)

    builder.set_entry_point("initialize")
    builder.add_edge("initialize", "node")
    builder.set_finish_point("node")
    return builder

