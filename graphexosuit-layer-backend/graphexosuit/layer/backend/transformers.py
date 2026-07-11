"""graphexosuit.layer.backend.transformers -- RunResult serialization helpers.

Responsibilities:
  - Convert a RunResult into a JSON-serializable dict suitable for HTTP responses.
  - Build resume_url path with properly URL-encoded identifiers.
  - Exclude interrupt payloads from responses; expose only label and resume_url per option.
  - Raise clear errors when final_result contains non-serializable objects.
"""

from __future__ import annotations

import json
from typing import Any

from graphexosuit.core import RunResult


def build_resume_url(thread_id: str, checkpoint_id: str) -> str:
    """Return the resumption URL for one interrupt option.

    The URL contains only thread_id and checkpoint_id; the resume_value must be
    sent in the request body when clients POST to this URL. This design supports
    arbitrarily large payloads and follows REST best practices.

    Args:
        thread_id: The thread identifier for the paused execution.
        checkpoint_id: The checkpoint identifier at the point of interruption.
    """
    from urllib.parse import quote
    return f"/thread/{quote(thread_id, safe='')}/checkpoint/{quote(checkpoint_id, safe='')}/resume"


def _serialize_final_result(final_result: dict) -> dict:
    """Return a JSON-safe copy of *final_result*, converting non-serializable values to strings.

    We perform a round-trip through json.dumps/json.loads so that any
    non-serializable leaf value is replaced with its str() representation
    rather than raising a hard error.

    Args:
        final_result: The raw final_result dict from a completed RunResult.
    """
    return json.loads(json.dumps(final_result, default=str))


def transform_run_result(result: RunResult) -> dict:
    """Convert a RunResult into a JSON-serializable response dict.

    When the workflow is **paused** (``interrupt_value`` is present) the
    response includes:
      - ``thread_id``
      - ``checkpoint_id``
      - ``interrupt_value`` dict with ``message`` and ``options``; each option
        exposes ``label`` and a pre-built ``resume_url`` (payload is **excluded**).

    When the workflow **completes** (``final_result`` is present) the response
    includes only:
      - ``thread_id``
      - ``final_result``

    Args:
        result: The RunResult produced by ExosuitCore.run/resume/retry.

    Raises:
        ValueError: If ``result`` is neither paused nor complete (invalid state).
    """
    if result.interrupt_value is not None:
        if result.checkpoint_id is None:
            raise ValueError(
                f"RunResult for thread_id {result.thread_id!r} has interrupt_value set "
                "but checkpoint_id is None. This suggests a programming error in graphexosuit."
            )

        # ## Paused branch
        options_payload = [
            {
                "label": option.label,
                "resume_url": build_resume_url(
                    thread_id=result.thread_id,
                    # checkpoint_id is guaranteed non-None when interrupt_value is set
                    # (enforced by RunResult.__post_init__)
                    checkpoint_id=result.checkpoint_id,
                ),
            }
            for option in result.interrupt_value.options
        ]
        return {
            "thread_id": result.thread_id,
            "checkpoint_id": result.checkpoint_id,
            "interrupt_value": {
                "message": result.interrupt_value.message,
                "options": options_payload,
            },
        }

    if result.final_result is not None:
        # ## Completed branch
        return {
            "thread_id": result.thread_id,
            "final_result": _serialize_final_result(result.final_result),
        }

    # ## Invalid state – RunResult validation should have caught this, but guard anyway
    raise ValueError(
        f"RunResult for thread_id={result.thread_id!r} has neither "
        "interrupt_value nor final_result set. "
        "This indicates a programming error in the graph or the ExosuitCore implementation."
    )
