"""Custom exceptions for graphexosuit."""

class GraphExecutionError(Exception):
    """Raised when the graph throws an unexpected error during execution.   This wraps the original exception and provides additional context about the graph execution."""
    def __init__(self,
                 message: str,
                 original_exception: Exception,
                 thread_id: str,
                 checkpoint_id: str,
                 ):
        super().__init__(f"{message} because {original_exception}")

        self._checkpoint_id = checkpoint_id
        self._thread_id = thread_id

    def get_checkpoint_id(self) -> str:
        return self._checkpoint_id

    def get_thread_id(self) -> str:
        return self._thread_id


class GraphLoaderError(Exception):
    """Raised when the graph module cannot be loaded or is missing required functions."""


class InvalidInterruptError(ValueError):
    """Raised when an interrupt value does not satisfy the StandardizedInterrupt interface."""
