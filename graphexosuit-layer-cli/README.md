# graphexosuit-layer-cli

Typer CLI for [graphexosuit-core](../graphexosuit-core) — execute, pause, resume, and retry LangGraph workflows from the command line.

## Installation

```bash
pip install graphexosuit-layer-cli
```

## Configuration

Set the `GRAPHEXOSUIT_LINER_CLASS` environment variable to the module path and class name in the format `"module.path:ClassName"`:

```bash
export GRAPHEXOSUIT_LINER_CLASS=my_project.workflows:MyLiner
```

## Commands

### `graphexosuit run`

```bash
graphexosuit run --initial-state '{"value": "start"}' [--thread-id <id>]
```

### `graphexosuit resume`

```bash
graphexosuit resume \
  --thread-id <id> \
  --checkpoint-id <id> \
  --resume-value '{"key": "value"}'
```

### `graphexosuit retry`

```bash
graphexosuit retry --thread-id <id> --checkpoint-id <id>
```

All commands print a `RunResult` JSON object to stdout.
