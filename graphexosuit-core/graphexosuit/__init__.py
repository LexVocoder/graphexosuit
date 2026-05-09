"""graphexosuit – lightweight LangGraph runtime wrapper.

Responsibilities:
  - Mark graphexosuit as a namespace package (for multi-package support).
  - All public API exports have been moved to graphexosuit.core.
"""

# Namespace package - supports multiple graphexosuit subpackages in different distributions
__path__ = __import__("pkgutil").extend_path(__path__, __name__)

