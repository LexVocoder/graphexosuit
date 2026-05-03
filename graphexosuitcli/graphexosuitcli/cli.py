#!/usr/bin/env -S uv run

"""Typer CLI for graphexosuit."""

from __future__ import annotations

import json
import sys
import typer
from dataclasses import asdict
from typing import Optional

from graphexosuit import ExosuitCore, load_liner, ResumeValue
from graphexosuit.core import RunResult


app = typer.Typer(
    name="graphexosuit",
    help="Execute, resume, and retry LangGraph workflows.",
    add_completion=False,
)


def _load_core():
    """Load Liner and return an ExosuitCore instance."""
    liner = load_liner()
    return ExosuitCore(liner)


def _print_result(result) -> None:
    """Serialize a RunResult to JSON and print it to stdout."""
    print(json.dumps(asdict(result), default=str, indent=2))

def _print_tips_to_stderr(result: RunResult) -> None:
    """Print re-execution tips to stderr if the graph execution did not complete."""
    if result.completed:
        return

    tip = ""
    if result.paused and result.interrupt_value is not None:
        tip += "Graph execution paused. To resume, run:\n"
        tip += f"  cli.py resume "
        tip += f"--thread-id {result.thread_id} "
        tip += f"--checkpoint-id {result.checkpoint_id} "
        tip += f"--resume-id '{'/'.join(option.id for option in result.interrupt_value.options)}' "
        tip += f"--payload '{'/'.join(json.dumps(option.payload) if option.payload is not None else '{}' for option in result.interrupt_value.options)}'"
    elif result.error:
        tip += "Graph execution failed. To retry, run:\n"
        tip += f"  cli.py retry "
        tip += f"--thread-id {result.thread_id} "
        tip += f"--checkpoint-id {result.checkpoint_id}"
    # else we got no tips

    if tip:
        print(tip, file=sys.stderr)

@app.command()
def run(
    input: str = typer.Option(..., "--input", help="Graph input as a JSON string."),
    thread_id: Optional[str] = typer.Option(
        None, "--thread-id", help="Optional thread identifier."
    ),
) -> None:
    """Run the graph from the beginning."""
    try:
        initial_state = json.loads(input)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --input: {exc}", err=True)
        raise typer.Exit(code=1)

    core = _load_core()
    try:
        result = core.run(initial_state, thread_id=thread_id)
        _print_result(result)
        _print_tips_to_stderr(result)
    finally:
        core.close()


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

    core = _load_core()
    try:
        resume_value = ResumeValue(id=resume_id, payload=payload_data)
        result = core.resume(thread_id, checkpoint_id, resume_value)
        _print_result(result)
        _print_tips_to_stderr(result)
    finally:
        core.close()


@app.command()
def retry(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
) -> None:
    """Retry the failed node of a graph execution."""
    core = _load_core()
    try:
        result = core.retry(thread_id, checkpoint_id)
        _print_result(result)
        _print_tips_to_stderr(result)
    finally:
        core.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
