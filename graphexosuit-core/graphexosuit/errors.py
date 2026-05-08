"""Custom exceptions for graphexosuit."""


class GraphLoaderError(Exception):
    """Raised when the graph module cannot be loaded or is missing required functions."""


class InvalidInterruptError(ValueError):
    """Raised when an interrupt value does not satisfy the StandardizedInterrupt interface."""
