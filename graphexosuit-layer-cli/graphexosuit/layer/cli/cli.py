#!/usr/bin/env -S uv run

"""Typer CLI for graphexosuit."""

from __future__ import annotations

import json
import sys
import typer
from dataclasses import asdict
from shlex import quote
from typing import Any, Optional

from graphexosuit.core import ExosuitCore, ExosuitLiner, RunResult


def _get_quoted_program_name() -> str:
    return quote(sys.argv[0] if len(sys.argv) > 0 else "graphexosuit")


def _to_cli_args(run_result: RunResult) -> str:
    """Build CLI arguments needed to reconstruct a run context."""
    args = f"--thread-id {quote(run_result.thread_id)} "
    if run_result.checkpoint_id:
        args += f"--checkpoint-id {quote(run_result.checkpoint_id)} "
    return args


def _print_result(result) -> None:
    """Serialize a RunResult to JSON and print it to stdout."""
    print(json.dumps(asdict(result), default=str, indent=2))

def _print_tips_to_stderr(run_result: RunResult) -> None:
    """Print re-execution tips to stderr if the graph execution did not complete."""
    if run_result.final_result is not None:
        return

    tip = ""
    if run_result.interrupt_value is not None:
        tip += f"Graph execution paused; message = {repr(run_result.interrupt_value.message)}\n"

        for option in run_result.interrupt_value.options:
            tip += "\n"
            tip += f"- For {repr(option.label)}, run:  "
            tip += f"{_get_quoted_program_name()} resume "
            tip += _to_cli_args(run_result)

            # Resumption requires the option's payload
            tip += f"--resume-value {quote(json.dumps(option.payload))}"

    elif run_result.error_message:
        tip += "Graph execution failed. To retry, run:\n"
        tip += "\n"
        tip += f"    {_get_quoted_program_name()} retry "

        tip += _to_cli_args(run_result)

    # else we got no tips

    if tip:
        print(tip, file=sys.stderr)  # adds a newline at the end

class CliApp:
    """CLI application for graphexosuit; clients must inject a Liner instance."""

    def __init__(self, liner: ExosuitLiner) -> None:
        """Initialize CLI with a custom liner instance.

        Args:
            liner: An ExosuitLiner instance to use for graph execution.
        """
        self.core = ExosuitCore(liner)
        self.app = typer.Typer(
            name="graphexosuit",
            help="Execute, resume, and retry LangGraph workflows.",
            add_completion=False,
        )

        # Register commands
        self.app.command()(self.run)
        self.app.command()(self.resume)
        self.app.command()(self.retry)

    def run(
        self,
        initial_state_json: str = typer.Option(..., "--initial-state", help="Graph input dict as a JSON string."),
        thread_id: Optional[str] = typer.Option(
            None, "--thread-id", help="Optional thread identifier."
        ),
    ) -> None:
        """Run the graph from the beginning."""
        try:
            initial_state = json.loads(initial_state_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid JSON for --initial-state: {exc}", err=True)
            raise typer.Exit(code=1)

        result = self.core.run(initial_state, thread_id=thread_id)
        _print_result(result)
        _print_tips_to_stderr(result)

    def resume(
        self,
        thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
        checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
        resume_value_json: str = typer.Option(..., "--resume-value", help="Resume value as JSON."),
    ) -> None:
        """Resume a paused graph execution."""
        resume_value: Any = None
        try:
            resume_value = json.loads(resume_value_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid JSON for --resume-value: {exc}", err=True)
            raise typer.Exit(code=1)

        result = self.core.resume(thread_id, checkpoint_id, resume_value)
        _print_result(result)
        _print_tips_to_stderr(result)

    def retry(
        self,
        thread_id: str = typer.Option(..., "--thread-id", help="Thread identifier."),
        checkpoint_id: str = typer.Option(..., "--checkpoint-id", help="Checkpoint identifier."),
    ) -> None:
        """Retry the failed node of a graph execution."""
        result = self.core.retry(thread_id, checkpoint_id)
        _print_result(result)
        _print_tips_to_stderr(result)

    def __call__(self) -> None:
        """Invoke the CLI application."""
        self.app()
