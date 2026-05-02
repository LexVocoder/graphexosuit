# graphexosuitcli

Typer CLI for [graphexosuit](../graphexosuit) — execute, pause, resume, and retry LangGraph workflows from the command line.

## Installation

```bash
pip install graphexosuitcli
```

## Configuration

Set the `LANGGRAPH_GRAPH_MODULE` environment variable to the dotted path of the module containing `get_graph()` and `get_checkpointer()`:

```bash
export LANGGRAPH_GRAPH_MODULE=my_project.workflows
```

## Commands

### `graphexosuit run`

```bash
graphexosuit run --input '{"value": "start"}' [--thread-id <id>]
```

### `graphexosuit resume`

```bash
graphexosuit resume \
  --thread-id <id> \
  --checkpoint-id <id> \
  --resume-id approve \
  [--payload '{"key": "value"}']
```

### `graphexosuit retry`

```bash
graphexosuit retry --thread-id <id> --checkpoint-id <id>
```

All commands print a `RunResult` JSON object to stdout.
