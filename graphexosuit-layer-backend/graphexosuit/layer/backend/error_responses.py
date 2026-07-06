"""graphexosuit.layer.backend.error_responses -- HTTP error response builders.

Responsibilities:
  - Provide helpers that construct standardized JSON error response dicts.
  - Build retry URLs with properly URL-encoded parameters for failed executions.
  - Keep all error-shaping logic out of main.py to make it independently testable.
"""

from __future__ import annotations

from urllib.parse import quote


def build_retry_url(thread_id: str, checkpoint_id: str) -> str:
    """Return the retry URL for a failed execution.

    Args:
        thread_id: The thread identifier of the failed execution.
        checkpoint_id: The checkpoint at which the failure occurred.
    """
    return f"/thread/{quote(thread_id, safe='')}/checkpoint/{quote(checkpoint_id, safe='')}/retry"
    

def error_response_500(
    error: Exception,
    thread_id: str,
    checkpoint_id: str,
) -> dict:
    """Build the JSON body for an HTTP 500 GraphExecutionError response.

    Includes a ``retry_url`` that clients can POST to without any additional
    parameters to re-run the failed node from its last checkpoint.

    Args:
        error: The exception that caused the failure (original message is included).
        thread_id: The thread identifier of the failed execution.
        checkpoint_id: The checkpoint at which the failure occurred.
    """
    return {
        "error": str(error),
        "thread_id": thread_id,
        "checkpoint_id": checkpoint_id,
        "retry_url": build_retry_url(thread_id, checkpoint_id),
    }
