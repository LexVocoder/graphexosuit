#!/usr/bin/env -S uv run

"""Typer CLI for graphexosuit."""

from __future__ import annotations

import json
import os
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


def _load_core(
        liner_class: Optional[str] = None,
        liner_dir: Optional[str] = None,
    ) -> ExosuitCore:
    """Load Liner and return an ExosuitCore instance."""

    if liner_class:
        os.environ["GRAPHEXOSUIT_LINER_CLASS"] = liner_class

    if liner_dir:
        sys.path.append(liner_dir)

    liner = load_liner()
    return ExosuitCore(liner)


def _print_result(result) -> None:
    """Serialize a RunResult to JSON and print it to stdout."""
    print(json.dumps(asdict(result), default=str, indent=2))

def _print_tips_to_stderr(
        run_result: RunResult,
        liner_class: Optional[str] = None,
        liner_dir: Optional[str] = None,
    ) -> None:
    """Print re-execution tips to stderr if the graph execution did not complete."""
    if run_result.completed:
        return

    tip = ""
    if run_result.paused and run_result.interrupt_value is not None:
        tip += f"Graph execution paused. {run_result.interrupt_value.message}:\n\n"

        for option in run_result.interrupt_value.options:
            tip += f"- For {option.label}, run graphexosuit resume "

            if liner_class:
                tip += f"--liner-class {repr(liner_class)} "

            if liner_dir:
                tip += f"--liner-dir {repr(liner_dir)} "

            tip += f"--thread-id {repr(run_result.thread_id)} "
            tip += f"--checkpoint-id {repr(run_result.checkpoint_id)} "
            tip += f"--resume-id {repr(option.id)} "
            if option.payload is not None:
                tip += f"--payload {repr(json.dumps(option.payload))}"
            tip += "\n"
    elif run_result.error:
        tip += "Graph execution failed. To retry, run:\n"
        tip += f"  graphexosuit retry "

        if liner_class:
            tip += f"--liner-class {repr(liner_class)} "

        if liner_dir:
            tip += f"--liner-dir {repr(liner_dir)} "

        tip += f"--thread-id {repr(run_result.thread_id)} "
        tip += f"--checkpoint-id {repr(run_result.checkpoint_id)}"
    # else we got no tips

    if tip:
        print(tip, file=sys.stderr)

@app.command()
def run(
    input: str = typer.Option(..., "--input", help="Graph input as a JSON string."),
    thread_id: Optional[str] = typer.Option(
        None, "--thread-id", help="Optional thread identifier."
    ),
    liner_class: Optional[str] = typer.Option(
        None, "--liner-class", help="Optional liner class to use in package:class format (e.g. 'my_package:MyLiner'). Overrides GRAPHEXOSUIT_LINER_CLASS environment variable."
    ),
    liner_dir: Optional[str] = typer.Option(
        None, "--liner-dir", help="Optional directory to load liner from. Added to end of sys.path (PYTHONPATH)."
    ),
) -> None:
    """Run the graph from the beginning."""
    try:
        initial_state = json.loads(input)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --input: {exc}", err=True)
        raise typer.Exit(code=1)

    core = _load_core(liner_class=liner_class, liner_dir=liner_dir)

    result = core.run(initial_state, thread_id=thread_id)
    _print_result(result)
    _print_tips_to_stderr(result, liner_class, liner_dir)


@app.command()
def resume(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
    resume_id: str = typer.Option(..., "--resume-id", help="Selected option ID."),
    payload: Optional[str] = typer.Option(
        None, "--payload", help="Optional payload as a JSON string."
    ),
    liner_class: Optional[str] = typer.Option(
        None, "--liner-class", help="Optional liner class to use in package:class format (e.g. 'my_package:MyLiner'). Overrides GRAPHEXOSUIT_LINER_CLASS environment variable."
    ),
    liner_dir: Optional[str] = typer.Option(
        None, "--liner-dir", help="Optional directory to load liner from. Added to end of sys.path (PYTHONPATH)."
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

    core = _load_core(liner_class=liner_class, liner_dir=liner_dir)

    resume_value = ResumeValue(id=resume_id, payload=payload_data)
    result = core.resume(thread_id, checkpoint_id, resume_value)
    _print_result(result)
    _print_tips_to_stderr(result, liner_class, liner_dir)


@app.command()
def retry(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
    liner_class: Optional[str] = typer.Option(
        None, "--liner-class", help="Optional liner class to use in package:class format (e.g. 'my_package:MyLiner'). Overrides GRAPHEXOSUIT_LINER_CLASS environment variable."
    ),
    liner_dir: Optional[str] = typer.Option(
        None, "--liner-dir", help="Optional directory to load liner from. Added to end of sys.path (PYTHONPATH)."
    ),
) -> None:
    """Retry the failed node of a graph execution."""
    core = _load_core(liner_class=liner_class, liner_dir=liner_dir)
    result = core.retry(thread_id, checkpoint_id)
    _print_result(result)
    _print_tips_to_stderr(result, liner_class, liner_dir)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
