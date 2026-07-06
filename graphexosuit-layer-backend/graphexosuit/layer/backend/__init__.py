"""graphexosuit.layer.backend – Async FastAPI backend for graphexosuit LangGraph workflows.

Responsibilities:
  - Expose create_app(liner, execution_data_store) factory for async REST API
    with background workers and polling-based result retrieval.
  - Provide REST endpoints for graph execution with execution data persistence.
  - Capture stdout/stderr from background graph executions and store in execution data.
  - Support polling interface for clients to retrieve execution results and status.
"""

from graphexosuit.layer.backend.main import create_app

__all__ = [
    "create_app",
]
