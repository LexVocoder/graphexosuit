"""graphexosuit.layer.backend - FastAPI web interface for graphexosuit.

Responsibilities:
  - Provide HTTP/REST API for executing, resuming, and retrying LangGraph workflows.
"""

from graphexosuit.layer.backend.app import app

__all__ = ["app"]
