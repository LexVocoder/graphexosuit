"""Tests for graphexosuit.layer.backend.streaming_text_capture module."""

from __future__ import annotations

import time
from typing import Any

import pytest

from graphexosuit.layer.backend.streaming_text_capture import StreamingTextCapture


# ===========================================================================
# Unit tests: StreamingTextCapture
# ===========================================================================

class TestStreamingTextCapture:
    """Tests for the StreamingTextCapture class."""
    
    def test_write_complete_line_flushes_immediately(self) -> None:
        """write() with complete line (ending in \\n) must flush immediately to store."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        
        # Initialize store
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Write complete line
        count = capture.write("hello world\n")
        assert count == 12
        assert store_data["thread-1.output_lines"] == ["hello world"]
        assert capture.buf == ""
    
    def test_write_incomplete_line_buffers(self) -> None:
        """write() without trailing \\n must buffer and not flush."""
        store_data: dict[str, Any] = {}
        call_count = {"store": 0}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            call_count["store"] += 1
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        mock_store_dict("thread-1", {"output_lines": []})
        call_count["store"] = 0  # Reset after init
        
        # Write incomplete line
        capture.write("hello world")
        assert capture.buf == "hello world"
        assert call_count["store"] == 0  # No store call for incomplete line
    
    def test_write_mixed_complete_and_incomplete(self) -> None:
        """write() with mixed content must flush complete lines and buffer incomplete."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Write with multiple newlines and incomplete line at end
        capture.write("line1\nline2\npartial")
        assert store_data["thread-1.output_lines"] == ["line1", "line2"]
        assert capture.buf == "partial"
    
    def test_close_flushes_remaining_buffer(self) -> None:
        """close() must flush any remaining buffered content."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Write incomplete line
        capture.write("incomplete")
        assert capture.buf == "incomplete"
        
        # Close should flush
        capture.close()
        assert store_data["thread-1.output_lines"] == ["incomplete"]
        assert capture.buf == ""
    
    def test_close_is_idempotent(self) -> None:
        """close() must be safe to call multiple times."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Write and close twice
        capture.write("test")
        capture.close()
        first_close_state = store_data["thread-1.output_lines"].copy()
        
        capture.close()  # Second close
        second_close_state = store_data["thread-1.output_lines"]
        
        assert first_close_state == second_close_state == ["test"]
    
    def test_multiple_writes_accumulate_lines(self) -> None:
        """Multiple write() calls must accumulate lines correctly in store."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Multiple writes with mixed complete/incomplete lines
        capture.write("first\n")
        capture.write("sec")
        capture.write("ond\n")
        capture.write("third")
        
        assert store_data["thread-1.output_lines"] == ["first", "second"]
        assert capture.buf == "third"
        
        # Close to flush remaining
        capture.close()
        assert store_data["thread-1.output_lines"] == ["first", "second", "third"]
    
    def test_streaming_with_stderr(self) -> None:
        """StreamingTextCapture must work independently for output_lines from both stdout and stderr."""
        store_data: dict[str, Any] = {}
        
        def mock_load_dict(thread_id: str, keys: list[str]) -> dict[str, Any]:
            result = {}
            for key in keys:
                full_key = f"{thread_id}.{key}"
                if full_key in store_data:
                    result[key] = store_data[full_key]
            return result
        
        def mock_store_dict(thread_id: str, data: dict[str, Any]) -> None:
            for key, value in data.items():
                full_key = f"{thread_id}.{key}"
                store_data[full_key] = value
        
        stdout_capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        stderr_capture = StreamingTextCapture("thread-1", "output_lines", mock_load_dict, mock_store_dict)
        
        mock_store_dict("thread-1", {"output_lines": []})
        
        # Write to both stdout and stderr, both go to output_lines
        stdout_capture.write("out1\n")
        stderr_capture.write("err1\n")
        stdout_capture.write("out2\n")
        
        assert store_data["thread-1.output_lines"] == ["out1", "err1", "out2"]
