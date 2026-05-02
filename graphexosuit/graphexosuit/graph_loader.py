"""Dynamic module loader for graph and checkpointer factories."""

from __future__ import annotations

import importlib
import os
from typing import Any, Tuple

from graphexosuit.errors import GraphLoaderError

_ENV_VAR = "LANGGRAPH_GRAPH_MODULE"


def load_graph_and_checkpointer() -> Tuple[Any, Any]:
    """Import the developer's module and call ``get_graph()`` and ``get_checkpointer()``.

    The module path is read from the ``LANGGRAPH_GRAPH_MODULE`` environment
    variable (e.g. ``"my_project.workflows"``).

    Returns
    -------
    tuple[StateGraph, checkpointer]
        An uncompiled StateGraph and a checkpointer instance.

    Raises
    ------
    GraphLoaderError
        If the environment variable is missing, the module cannot be imported,
        or the required functions are absent.
    """
    module_path = os.environ.get(_ENV_VAR)
    if not module_path:
        raise GraphLoaderError(
            f"Environment variable {_ENV_VAR!r} is not set. "
            "Set it to the dotted module path containing get_graph() and get_checkpointer()."
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise GraphLoaderError(
            f"Could not import module {module_path!r}: {exc}"
        ) from exc

    get_graph = getattr(module, "get_graph", None)
    if get_graph is None or not callable(get_graph):
        raise GraphLoaderError(
            f"Module {module_path!r} must define a callable get_graph()."
        )

    get_checkpointer = getattr(module, "get_checkpointer", None)
    if get_checkpointer is None or not callable(get_checkpointer):
        raise GraphLoaderError(
            f"Module {module_path!r} must define a callable get_checkpointer()."
        )

    state_graph = get_graph()
    checkpointer = get_checkpointer()
    return state_graph, checkpointer
