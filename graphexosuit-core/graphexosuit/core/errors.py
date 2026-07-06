"""Custom exceptions for graphexosuit."""

class GraphExecutionError(Exception):
    """Raised when the graph throws an unexpected error during execution.   This wraps the original exception and provides additional context about the graph execution."""
    def __init__(self,
                 message: str,
                 original_exception: Exception,
                 thread_id: str,
                 checkpoint_id: str,
                 ):
        super().__init__(f"{message}, because {original_exception}")

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


class ThreadNotFound(Exception):
    """Raised when a thread or checkpoint does not exist.
    
    Args:
        thread_id: The thread identifier that was not found.
        checkpoint_id: Optional checkpoint identifier (set if checkpoint not found).
    """
    def __init__(self, thread_id: str, checkpoint_id: str | None = None) -> None:
        """Initialize ThreadNotFound exception.
        
        Args:
            thread_id: The thread ID that was not found.
            checkpoint_id: Optional checkpoint ID if specific checkpoint is missing.
        """
        self.thread_id = thread_id
        self.checkpoint_id = checkpoint_id
        
        if checkpoint_id:
            message = f"Thread '{thread_id}' with checkpoint '{checkpoint_id}' not found"
        else:
            message = f"Thread '{thread_id}' not found"
        super().__init__(message)
