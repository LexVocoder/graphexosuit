"""Typer CLI for graphexosuit."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Optional

import typer

app = typer.Typer(
    name="graphexosuit",
    help="Execute, pause, resume, and retry LangGraph workflows.",
    add_completion=False,
)


def _load_core():
    """Load graph, checkpointer, and return an ExosuitCore instance."""
    from graphexosuit import ExosuitCore, load_graph_and_checkpointer

    state_graph, checkpointer = load_graph_and_checkpointer()
    return ExosuitCore(state_graph, checkpointer)


def _print_result(result) -> None:
    """Serialize a RunResult to JSON and print it to stdout."""
    print(json.dumps(asdict(result), default=str))


@app.command()
def run(
    input: str = typer.Option(..., "--input", help="Graph input as a JSON string."),
    thread_id: Optional[str] = typer.Option(
        None, "--thread-id", help="Optional thread identifier."
    ),
) -> None:
    """Run the graph from the beginning."""
    try:
        input_data = json.loads(input)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --input: {exc}", err=True)
        raise typer.Exit(code=1)

    core = _load_core()
    result = core.run(input_data, thread_id=thread_id)
    _print_result(result)


@app.command()
def resume(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
    resume_id: str = typer.Option(..., "--resume-id", help="Selected option ID."),
    payload: Optional[str] = typer.Option(
        None, "--payload", help="Optional payload as a JSON string."
    ),
) -> None:
    """Resume a paused graph execution."""
    payload_data: Optional[dict] = None
    if payload is not None:
        try:
            payload_data = json.loads(payload)
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid JSON for --payload: {exc}", err=True)
            raise typer.Exit(code=1)

    from graphexosuit import ResumeValue

    core = _load_core()
    resume_value = ResumeValue(id=resume_id, payload=payload_data)
    result = core.resume(thread_id, checkpoint_id, resume_value)
    _print_result(result)


@app.command()
def retry(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
) -> None:
    """Retry the failed node of a graph execution."""
    core = _load_core()
    result = core.retry(thread_id, checkpoint_id)
    _print_result(result)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
