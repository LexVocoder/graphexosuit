"""graphexosuit.layer.backend.streaming_text_capture - Real-time stdout/stderr capture with store updates.

Responsibilities:
  - Provide StreamingTextCapture class that wraps StringIO and streams complete lines
    to an execution data store in real-time.
  - Buffer incomplete lines (without trailing newline) until a newline is encountered.
  - Expose idempotent close() method to flush remaining buffered content.
"""

from __future__ import annotations

import io
from typing import Any, Callable


class StreamingTextCapture(io.StringIO):
    """Custom StringIO that streams lines to execution data as they are written.
    
    Each write() appends complete lines (with \\n delimiter) directly to the store,
    providing real-time heartbeat updates to clients polling execution status.
    Incomplete lines are buffered until a \\n is encountered.
    """
    
    def __init__(
        self,
        thread_id: str,
        field_name: str,
        load_dict_fn: Callable[[str, list[str]], dict[str, Any]],
        store_dict_fn: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Initialize the streaming capture for stdout or stderr.
        
        Args:
            thread_id: The thread identifier for this execution.
            field_name: Either "stdout_lines" or "stderr_lines" to persist to.
            load_dict_fn: Function to load data from the execution data store.
            store_dict_fn: Function to store data in the execution data store.
        """
        super().__init__()
        self.thread_id = thread_id
        self.field_name = field_name
        self.load_dict_fn = load_dict_fn
        self.store_dict_fn = store_dict_fn
        self.buf = ""
    
    def _append_lines_to_store(self, lines_to_append: list[str]) -> None:
        """Append lines to the execution data store for this field.
        
        Loads existing lines from the store, appends the new lines, and persists
        the updated list.
        
        Args:
            lines_to_append: List of lines to append to the field.
        """
        current_data = self.load_dict_fn(self.thread_id, [self.field_name])
        existing_lines = current_data.get(self.field_name) or []
        updated_lines = existing_lines + lines_to_append
        self.store_dict_fn(self.thread_id, {self.field_name: updated_lines})
    
    def write(self, s: str) -> int:
        """Write text and flush complete lines to execution data store.
        
        Args:
            s: The text to write.
            
        Returns:
            Number of characters written (matches StringIO interface).
        """
        # Accumulate text
        self.buf += s
        
        # Split on newlines and flush complete lines
        lines = self.buf.split("\n")
        complete_lines = lines[:-1]  # All but the last (which may be incomplete)
        self.buf = lines[-1]  # Keep the incomplete line
        
        # Stream each complete line to the store
        if complete_lines:
            self._append_lines_to_store(complete_lines)
        
        # Return count of characters written (as StringIO.write does)
        return len(s)
    
    def close(self) -> None:
        """Flush any remaining buffered output and mark capture as closed (idempotent).
        
        Writes any incomplete line (without trailing newline) to the store.
        Safe to call multiple times; subsequent calls do nothing if buffer is empty.
        """
        if self.buf:
            self._append_lines_to_store([self.buf])
            self.buf = ""
