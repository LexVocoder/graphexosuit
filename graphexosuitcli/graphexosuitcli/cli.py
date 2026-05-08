#!/usr/bin/env -S uv run

"""Typer CLI for graphexosuit."""

from __future__ import annotations

import json
import os
import sys
import typer
from dataclasses import asdict
from shlex import quote
from typing import Any, Optional

from graphexosuit import ExosuitCore, load_liner
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
    if run_result.final_result is not None:
        return

    tip = ""
    if run_result.interrupt_value is not None:
        tip += f"Graph execution paused; message = {repr(run_result.interrupt_value.message)}\n"

        for option in run_result.interrupt_value.options:
            tip += "\n"
            tip += f"- For {repr(option.label)}, run:  "
            tip += f"graphexosuit resume "
            tip += to_cli_args(run_result, liner_class, liner_dir)

            # Resumption requires the option's payload
            tip += f"--resume-value {quote(json.dumps(option.payload))}"

    elif run_result.error_message:
        tip += "Graph execution failed. To retry, run:\n"
        tip += "\n"
        tip += f"    graphexosuit retry "

        tip += to_cli_args(run_result, liner_class, liner_dir)

    # else we got no tips

    if tip:
        print(tip, file=sys.stderr)  # adds a newline at the end

def to_cli_args(run_result, liner_class, liner_dir):
    args = ''
    if liner_class:
        args += f"--liner-class {quote(liner_class)} "

    if liner_dir:
        args += f"--liner-dir {quote(liner_dir)} "

    args += f"--thread-id {quote(run_result.thread_id)} "

    if run_result.checkpoint_id:
        args += f"--checkpoint-id {quote(run_result.checkpoint_id)} "
    return args

@app.command()
def run(
    initial_state_json: str = typer.Option(..., "--initial-state", help="Graph input as a JSON string."),
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
        initial_state = json.loads(initial_state_json)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --initial-state: {exc}", err=True)
        raise typer.Exit(code=1)

    core = _load_core(liner_class=liner_class, liner_dir=liner_dir)

    result = core.run(initial_state, thread_id=thread_id)
    _print_result(result)
    _print_tips_to_stderr(result, liner_class, liner_dir)


@app.command()
def resume(
    thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
    checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
    resume_value_json: str = typer.Option(..., "--resume-value", help="Resume value as JSON."),
    liner_class: Optional[str] = typer.Option(
        None, "--liner-class", help="Optional liner class to use in package:class format (e.g. 'my_package:MyLiner'). Overrides GRAPHEXOSUIT_LINER_CLASS environment variable."
    ),
    liner_dir: Optional[str] = typer.Option(
        None, "--liner-dir", help="Optional directory to load liner from. Added to end of sys.path (PYTHONPATH)."
    ),
) -> None:
    """Resume a paused graph execution."""
    resume_value: Any = None
    try:
        resume_value = json.loads(resume_value_json)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON for --resume-value: {exc}", err=True)
        raise typer.Exit(code=1)

    core = _load_core(liner_class=liner_class, liner_dir=liner_dir)

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
