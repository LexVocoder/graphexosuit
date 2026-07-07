"""Tests for graphexosuit.layer.backend.batch_key_value_store."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.stores import BaseStore

from graphexosuit.layer.backend.batch_key_value_store import BatchKeyValueStore


# ---------------------------------------------------------------------------
# Simple in-memory execution data store for testing
# ---------------------------------------------------------------------------

class _InMemoryExecutionDataStore(BaseStore):
    """Simple in-memory implementation of BaseStore for testing."""
    
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
    
    def mget(self, keys: list[str]) -> list[Any | None]:
        """Get multiple values from the store."""
        return [self._data.get(key) for key in keys]
    
    def mset(self, key_value_pairs: list[tuple[str, Any]]) -> None:
        """Set multiple key-value pairs."""
        for key, value in key_value_pairs:
            self._data[key] = value
    
    def mdelete(self, keys: list[str]) -> None:
        """Delete multiple keys."""
        for key in keys:
            if key in self._data:
                del self._data[key]
    
    def yield_keys(self, pattern: str | None = None) -> Any:
        """Yield all keys, optionally filtered by pattern."""
        for key in self._data.keys():
            yield key


# ===========================================================================
# Unit tests: BatchKeyValueStore
# ===========================================================================

class TestBatchKeyValueStoreInit:
    def test_init_accepts_base_store(self) -> None:
        """BatchKeyValueStore must accept a BaseStore instance."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        assert kv_store is not None


class TestBatchKeyValueStorePut:
    def test_put_stores_single_key_value_pair(self) -> None:
        """put() must store a single key-value pair in the underlying store."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("namespace1", {"key1": "value1"})
        
        # Check that the prefixed key was stored in the underlying store
        result = store.mget(["namespace1.key1"])
        assert result[0] is not None
        # Verify it's JSON encoded
        import json
        decoded = json.loads(result[0].decode("utf-8"))
        assert decoded == "value1"
    
    def test_put_stores_multiple_key_value_pairs(self) -> None:
        """put() must store multiple key-value pairs at once."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        data = {
            "key1": "value1",
            "key2": 42,
            "key3": ["list", "item"],
        }
        kv_store.put("namespace1", data)
        
        # Verify all prefixed keys were stored
        result = store.mget(["namespace1.key1", "namespace1.key2", "namespace1.key3"])
        assert len(result) == 3
        assert all(v is not None for v in result)
    
    def test_put_namespaces_keys_correctly(self) -> None:
        """put() must prefix keys with namespace and '.'."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("thread-123", {"output_lines": ["line1", "line2"]})
        kv_store.put("thread-456", {"output_lines": ["other"]})
        
        # Verify namespacing works
        result_123 = store.mget(["thread-123.output_lines"])
        result_456 = store.mget(["thread-456.output_lines"])
        
        import json
        lines_123 = json.loads(result_123[0].decode("utf-8"))
        lines_456 = json.loads(result_456[0].decode("utf-8"))
        
        assert lines_123 == ["line1", "line2"]
        assert lines_456 == ["other"]
    
    def test_put_handles_complex_nested_structures(self) -> None:
        """put() must handle complex nested data structures."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        complex_data = {
            "result": {
                "value": "success",
                "metadata": {
                    "timestamp": "2026-07-07T12:00:00Z",
                    "nodes_executed": 5,
                },
            },
            "error": None,
            "output_lines": ["line1", "line2"],
        }
        kv_store.put("execution-1", complex_data)
        
        # Verify the data can be retrieved and decoded properly
        result = store.mget(["execution-1.result", "execution-1.error", "execution-1.output_lines"])
        import json
        decoded = [json.loads(r.decode("utf-8")) for r in result]
        
        assert decoded[0] == complex_data["result"]
        assert decoded[1] is None
        assert decoded[2] == complex_data["output_lines"]
    
    def test_put_overwrites_existing_values(self) -> None:
        """put() must overwrite existing values for the same keys."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("namespace1", {"key1": "old_value"})
        kv_store.put("namespace1", {"key1": "new_value"})
        
        # Verify the new value is stored
        result = store.mget(["namespace1.key1"])
        import json
        decoded = json.loads(result[0].decode("utf-8"))
        assert decoded == "new_value"


class TestBatchKeyValueStoreGet:
    def test_get_retrieves_single_key_value_pair(self) -> None:
        """get() must retrieve a single key-value pair."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("namespace1", {"key1": "value1"})
        result = kv_store.get("namespace1", ["key1"])
        
        assert result == {"key1": "value1"}
    
    def test_get_retrieves_multiple_key_value_pairs(self) -> None:
        """get() must retrieve multiple key-value pairs at once."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        data = {
            "key1": "value1",
            "key2": 42,
            "key3": ["list", "item"],
        }
        kv_store.put("namespace1", data)
        result = kv_store.get("namespace1", ["key1", "key2", "key3"])
        
        assert result == data
    
    def test_get_returns_dict_with_none_for_nonexistent_namespace(self) -> None:
        """get() must return a dict with None values if namespace does not exist."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        result = kv_store.get("nonexistent", ["key1", "key2"])
        
        assert result == {"key1": None, "key2": None}
    
    def test_get_handles_partial_keys(self) -> None:
        """get() must handle requests for keys that don't all exist."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("namespace1", {"key1": "value1", "key3": "value3"})
        result = kv_store.get("namespace1", ["key1", "key2", "key3"])
        
        # key2 should be None because it wasn't stored
        assert result["key1"] == "value1"
        assert result["key2"] is None
        assert result["key3"] == "value3"
    
    def test_get_retrieves_complex_nested_structures(self) -> None:
        """get() must correctly deserialize complex nested structures."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        complex_data = {
            "result": {
                "value": "success",
                "metadata": {
                    "timestamp": "2026-07-07T12:00:00Z",
                    "nodes_executed": 5,
                },
            },
            "error": None,
        }
        kv_store.put("execution-1", complex_data)
        result = kv_store.get("execution-1", ["result", "error"])
        
        assert result["result"] == complex_data["result"]
        assert result["error"] is None
    
    def test_get_preserves_json_serializable_types(self) -> None:
        """get() must preserve various JSON-serializable types correctly."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        data = {
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }
        kv_store.put("types", data)
        result = kv_store.get("types", list(data.keys()))
        
        assert result == data
        assert isinstance(result["string"], str)
        assert isinstance(result["integer"], int)
        assert isinstance(result["float"], float)
        assert isinstance(result["boolean"], bool)
        assert result["null"] is None
        assert isinstance(result["list"], list)
        assert isinstance(result["dict"], dict)


class TestBatchKeyValueStoreIntegration:
    def test_put_get_roundtrip(self) -> None:
        """put() and get() must work together correctly."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        original_data = {
            "output_lines": ["line1", "line2", "line3"],
            "status": "running",
            "result": None,
            "error": None,
            "created_at": "2026-07-07T12:00:00Z",
        }
        kv_store.put("thread-123", original_data)
        
        retrieved_data = kv_store.get("thread-123", list(original_data.keys()))
        
        assert retrieved_data == original_data
    
    def test_multiple_namespaces_isolated(self) -> None:
        """Different namespaces must be isolated from each other."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        kv_store.put("thread-1", {"status": "running", "result": None})
        kv_store.put("thread-2", {"status": "completed", "result": {"value": "done"}})
        
        result1 = kv_store.get("thread-1", ["status", "result"])
        result2 = kv_store.get("thread-2", ["status", "result"])
        
        assert result1 == {"status": "running", "result": None}
        assert result2 == {"status": "completed", "result": {"value": "done"}}
    
    def test_updates_preserve_other_keys(self) -> None:
        """put() in the same namespace should not affect other keys in that namespace."""
        store = _InMemoryExecutionDataStore()
        kv_store = BatchKeyValueStore(store)
        
        # Initial data
        kv_store.put("thread-1", {
            "output_lines": ["line1"],
            "status": "running",
            "result": None,
        })
        
        # Update only the status
        kv_store.put("thread-1", {"status": "completed"})
        
        # Retrieve all keys
        result = kv_store.get("thread-1", ["output_lines", "status", "result"])
        
        # The first put and second put both affected the store
        # But since the underlying store is just a dict, the second put only
        # updates the "status" key, not the entire namespace
        assert result["status"] == "completed"
        # output_lines and result are still there from the first put
        assert result["output_lines"] == ["line1"]
        assert result["result"] is None
