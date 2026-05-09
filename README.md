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
from graphexosuit.core import ExosuitCore
from my_project.workflows import MyWorkflow

core = ExosuitCore(MyWorkflow())
result = core.run({"value": "start"}, thread_id="thread-1")
```

See [graphexosuit-core README](graphexosuit-core/README.md) for full documentation.

---

### 2. [`graphexosuit-layer-cli`](graphexosuit-layer-cli/) — CLI Tool
Typer CLI for executing graphexosuit workflows from the command line.

**Install:**
```bash
uv pip install ./graphexosuit-layer-cli
```

**Usage:**
```bash
export GRAPHEXOSUIT_LINER_CLASS=my_project.workflows:MyLiner
graphexosuit run --initial-state '{"value": "start"}' --thread-id my-thread
```

See [graphexosuit-layer-cli README](graphexosuit-layer-cli/README.md) for full documentation.

---

### 3. [`graphexosuit-layer-backend`](graphexosuit-layer-backend/) — Web Service
FastAPI web service for executing graphexosuit workflows over HTTP.

**Install:**
```bash
uv pip install ./graphexosuit-layer-backend
```

**Usage:**
```bash
export GRAPHEXOSUIT_LINER_CLASS=my_project.workflows:MyLiner
uvicorn graphexosuit.layer.backend:app --host 0.0.0.0 --port 8000
```

See [graphexosuit-layer-backend README](graphexosuit-layer-backend/README.md) for full documentation.

---

## Installation

Each package is **independently installable**. Install only what you need:

### From local development

For local development with these packages in their directories:

- **Core library only:** `uv pip install ./graphexosuit-core`
- **Core + CLI:** `uv pip install ./graphexosuit-core ./graphexosuit-layer-cli`
- **Core + Web:** `uv pip install ./graphexosuit-core ./graphexosuit-layer-backend`
- **All three:** `uv pip install ./graphexosuit-core ./graphexosuit-layer-cli ./graphexosuit-layer-backend`

Or install core first, then add optional packages:
```bash
uv pip install ./graphexosuit-core
uv pip install ./graphexosuit-layer-cli
uv pip install ./graphexosuit-layer-backend
```

### From PyPI (when published)

When packages are published to PyPI, standard dependency resolution applies:

```bash
uv pip install graphexosuit-core
uv pip install graphexosuit-layer-cli  # automatically installs graphexosuit-core
uv pip install graphexosuit-layer-backend  # automatically installs graphexosuit-core
```

## License

MIT
