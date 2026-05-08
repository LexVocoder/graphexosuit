# graphexosuit

Lightweight, flexible framework for executing LangGraphs from web or CLI.

This repository contains three independent packages that can be installed and used separately:

## Packages

### 1. [`graphexosuit`](graphexosuit/) — Core Runtime
The core Python package providing a standardised runtime interface for executing, pausing, resuming, and retrying [LangGraph](https://github.com/langchain-ai/langgraph) workflows.

**Install:**
```bash
uv pip install ./graphexosuit
```

**Quick start:**
```python
from graphexosuit import ExosuitCore
from my_project.workflows import MyWorkflow

core = ExosuitCore(MyWorkflow())
result = core.run({"value": "start"}, thread_id="thread-1")
```

See [graphexosuit README](graphexosuit/README.md) for full documentation.

---

### 2. [`graphexosuitcli`](graphexosuitcli/) — CLI Tool
Typer CLI for executing graphexosuit workflows from the command line.

**Install:**
```bash
uv pip install ./graphexosuitcli
```

**Usage:**
```bash
export LANGGRAPH_GRAPH_MODULE=my_project.workflows
graphexosuit run --input '{"value": "start"}' --thread-id my-thread
```

See [graphexosuitcli README](graphexosuitcli/README.md) for full documentation.

---

### 3. [`graphexosuitweb`](graphexosuitweb/) — Web Service
FastAPI web service for executing graphexosuit workflows over HTTP.

**Install:**
```bash
uv pip install ./graphexosuitweb
```

**Usage:**
```bash
export LANGGRAPH_GRAPH_MODULE=my_project.workflows
uvicorn graphexosuitweb.app:app --host 0.0.0.0 --port 8000
```

See [graphexosuitweb README](graphexosuitweb/README.md) for full documentation.

---

## Installation

Each package is **independently installable**. Install only what you need:

### From local development

For local development with these packages in their directories:

- **Core library only:** `uv pip install ./graphexosuit`
- **Core + CLI:** `uv pip install ./graphexosuit ./graphexosuitcli`
- **Core + Web:** `uv pip install ./graphexosuit ./graphexosuitweb`
- **All three:** `uv pip install ./graphexosuit ./graphexosuitcli ./graphexosuitweb`

Or install core first, then add optional packages:
```bash
uv pip install ./graphexosuit
uv pip install ./graphexosuitcli
uv pip install ./graphexosuitweb
```

### From PyPI (when published)

When packages are published to PyPI, standard dependency resolution applies:

```bash
uv pip install graphexosuit
uv pip install graphexosuitcli  # automatically installs graphexosuit
uv pip install graphexosuitweb  # automatically installs graphexosuit
```

## License

MIT
