"""Entry point for running the graphexosuitweb server via ``graphexosuitweb`` command."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Launch the graphexosuitweb FastAPI server with uvicorn."""
    uvicorn.run(
        "graphexosuit.layer.backend.app:app",
        host="0.0.0.0",
        port=8000,
    )


if __name__ == "__main__":
    main()
