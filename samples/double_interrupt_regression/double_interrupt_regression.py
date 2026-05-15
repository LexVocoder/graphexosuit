#!/usr/bin/env -S uv run
"""Minimal graph that reproduces the checkpoint/resume bug.

After resuming from the first interrupt and hitting the second, the reported
checkpoint_id is stale (still pointing to the first interrupt checkpoint).
Resuming with that stale checkpoint_id re-executes from the first interrupt
node instead of continuing from the second.
"""

import sys
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from graphexosuit.core import StandardizedInterrupt, InterruptOption, ExosuitCore, ExosuitLiner


class State(TypedDict):
    step: int


def node_interrupt1(state: State) -> dict:
    """First human-in-the-loop pause."""
    print(f">>> interrupt1 (step={state['step']})")
    result = interrupt(
        StandardizedInterrupt(
            message="First approval needed",
            options=[InterruptOption(label="Approve", payload="approved")],
        )
    )
    print(f">>> interrupt1 resumed with: {result!r}")
    return {"step": state["step"] + 1}


def node_interrupt2(state: State) -> dict:
    """Second human-in-the-loop pause."""
    print(f">>> interrupt2 (step={state['step']})")
    result = interrupt(
        StandardizedInterrupt(
            message="Second approval needed",
            options=[InterruptOption(label="Approve", payload="approved")],
        )
    )
    print(f">>> interrupt2 resumed with: {result!r}")
    return {"step": state["step"] + 1}


def get_graph() -> StateGraph:
    graph = StateGraph(State)
    graph.add_node("node_interrupt1", node_interrupt1)
    graph.add_node("node_interrupt2", node_interrupt2)

    graph.set_entry_point("node_interrupt1")
    graph.add_edge("node_interrupt1", "node_interrupt2")
    graph.add_edge("node_interrupt2", END)
    return graph


class TestLiner(ExosuitLiner):
    def __init__(self):
        self.checkpointer = MemorySaver()

    def get_graph(self) -> StateGraph:
        return get_graph()

    def get_checkpointer_cm(self):
        class CM:
            def __init__(self, cp): self._cp = cp
            def __enter__(self): return self._cp
            def __exit__(self, *a): pass
        return CM(self.checkpointer)


def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


if __name__ == "__main__":
    liner = TestLiner()
    core = ExosuitCore(liner)

    # ── Run 1: initial execution, hits node_interrupt1 ──────────────
    sep("RUN 1: initial (should pause at node_interrupt1)")
    r1 = core.run({"step": 0}, thread_id="bug-thread")
    print(f"\ncheckpoint_id : {r1.checkpoint_id}")
    print(f"interrupt msg : {r1.interrupt_value.message if r1.interrupt_value else 'NONE'}")
    assert r1.interrupt_value is not None, "Expected interrupt at node_interrupt1"
    assert "First" in r1.interrupt_value.message, f"Unexpected interrupt: {r1.interrupt_value.message}"
    checkpoint_after_interrupt1 = r1.checkpoint_id

    # ── Run 2: resume interrupt1, should pause at node_interrupt2 ───
    sep("RUN 2: resume interrupt1 (should pause at node_interrupt2)")
    r2 = core.resume(r1.thread_id, r1.checkpoint_id, "approved")
    print(f"\ncheckpoint_id : {r2.checkpoint_id}")
    print(f"interrupt msg : {r2.interrupt_value.message if r2.interrupt_value else 'NONE'}")
    assert r2.interrupt_value is not None, "Expected interrupt at node_interrupt2"
    assert "Second" in r2.interrupt_value.message, f"Unexpected interrupt: {r2.interrupt_value.message}"
    checkpoint_after_interrupt2 = r2.checkpoint_id

    print(f"\ncheckpoint_after_interrupt1 = {checkpoint_after_interrupt1}")
    print(f"checkpoint_after_interrupt2 = {checkpoint_after_interrupt2}")

    # ─── THE KEY DIAGNOSTIC ─────────────────────────────────────────
    if checkpoint_after_interrupt2 == checkpoint_after_interrupt1:
        print("\n❌ BUG CONFIRMED: r2.checkpoint_id == r1.checkpoint_id")
        print("   The second interrupt returned the FIRST interrupt's checkpoint.")
        print("   Resuming from this will re-run from node_interrupt1, not node_interrupt2.")
    else:
        print("\n✓ Checkpoint IDs differ — resuming from correct position.")

    # ── Run 3: resume interrupt2 using the reported checkpoint ──────
    sep("RUN 3: resume interrupt2 (should complete)")
    print(f"Resuming from: {checkpoint_after_interrupt2}")
    r3 = core.resume(r2.thread_id, checkpoint_after_interrupt2, "approved")
    print(f"\nfinal_result  : {r3.final_result}")
    print(f"final step    : {r3.final_result.get('step') if r3.final_result else 'N/A'}")

    # If bug exists, step will be 1 (jumped back to interrupt1).
    # If fixed, step will be 2 (completed both interrupts).
    if r3.final_result and r3.final_result.get("step") == 2:
        print("\n✓ CORRECT: both interrupts executed exactly once in order.")
        sys.exit(0)
    else:
        print(f"\n❌ BUG: step = {r3.final_result.get('step') if r3.final_result else 'N/A'}")
        print("   node_interrupt1 likely re-ran instead of node_interrupt2 resuming.")
        sys.exit(1)
