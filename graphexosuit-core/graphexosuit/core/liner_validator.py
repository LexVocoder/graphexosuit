"""graphexosuit.core.liner_validator -- Liner instance validation.

Responsibilities:
  - Validate that a Liner instance satisfies the ExosuitLiner interface.
  - Raise descriptive ValueError on invalid or missing required methods.
  - Called at app startup to fail fast before any request is served.
"""

from __future__ import annotations

from typing import Any


# ## Required interface
# These are the two methods every Liner must expose to be usable by ExosuitCore.
_REQUIRED_METHODS: tuple[str, ...] = ("get_graph", "get_checkpointer_cm")


def validate_liner(liner: Any) -> None:
    """Raise ValueError if *liner* is missing required ExosuitLiner interface methods.

    Performs a duck-type check: any object exposing ``get_graph`` and
    ``get_checkpointer_cm`` as callables is accepted.  The full
    ``ExosuitLiner`` ABC is not required so that callers can use plain
    classes or mock objects.

    Args:
        liner: The candidate Liner instance to validate.

    Raises:
        ValueError: If *liner* is None, or is missing one or more required methods.
    """
    if liner is None:
        raise ValueError(
            "Liner must not be None. "
            "Pass a Liner instance to create_app(liner=...)."
        )

    missing_methods = [
        method_name
        for method_name in _REQUIRED_METHODS
        if not callable(getattr(liner, method_name, None))
    ]

    if missing_methods:
        raise ValueError(
            f"Liner instance is missing required method(s): {missing_methods}. "
            f"The Liner must expose: {list(_REQUIRED_METHODS)}."
        )
