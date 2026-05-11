"""Dynamic module loader for Liner instances."""

from __future__ import annotations

import importlib
import os
from typing import Any

from graphexosuit.core.errors import GraphLoaderError

_ENV_VAR = "GRAPHEXOSUIT_LINER_CLASS"


def load_liner() -> Any:
    """Import a Liner class and instantiate it.

    The class path is read from the ``GRAPHEXOSUIT_LINER_CLASS`` environment
    variable using the format ``"module.path:ClassName"``
    (e.g. ``"my_project.workflows:MyWorkflow"``).

    The returned instance must have ``get_graph()`` and ``get_checkpointer()``
    methods (duck typing; no strict subclass check required).

    Returns
    -------
    Any
        An instantiated object with ``get_graph()`` and ``get_checkpointer()`` methods.

    Raises
    ------
    GraphLoaderError
        If the environment variable is missing, the module cannot be imported,
        the class is not found, or instantiation fails.
    """
    class_path = os.environ.get(_ENV_VAR)
    if not class_path:
        raise GraphLoaderError(
            f"Environment variable {_ENV_VAR!r} is not set. "
            "Set it to the module path and class name (e.g. 'my_project.workflows:MyWorkflow')."
        )

    if ":" not in class_path:
        raise GraphLoaderError(
            f"Invalid {_ENV_VAR!r} format: {class_path!r}. "
            "Expected format: 'module.path:ClassName'."
        )

    module_path, class_name = class_path.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise GraphLoaderError(
            f"Could not import module {module_path!r}: {exc}"
        ) from exc

    liner_class = getattr(module, class_name, None)
    if liner_class is None:
        raise GraphLoaderError(
            f"Module {module_path!r} has no class named {class_name!r}."
        )

    try:
        return liner_class()
    except Exception as exc:
        raise GraphLoaderError(
            f"Failed to instantiate {class_path!r}: {exc}"
        ) from exc
