"""graphexosuit.layer.backend.batch_key_value_store - Namespaced batch key-value store wrapper.

Responsibilities:
  - Provide BatchKeyValueStore class that wraps a BaseStore instance.
  - Manage namespaced key-value pairs with automatic JSON serialization/deserialization.
  - Support put() to store dictionaries and get() to retrieve values by key list.
  - Prefix keys with namespace and "." to isolate data within the store.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.stores import BaseStore


class BatchKeyValueStore:
    """Namespaced key-value store wrapper around a BaseStore.
    
    Provides a simplified interface for storing and retrieving JSON-serializable
    data in a BaseStore, with automatic namespace prefixing and JSON encoding/decoding.
    All keys are prefixed with "{namespace}." to isolate data by namespace.
    """
    
    def __init__(self, store: BaseStore) -> None:
        """Initialize the batch key-value store with a BaseStore instance.
        
        Args:
            store: The underlying BaseStore instance to wrap.
        """
        self._store = store
    
    def put(self, namespace: str, data: dict[str, Any]) -> None:
        """Store all key-value pairs from a dictionary in the underlying store.
        
        Prefixes each key with the namespace and a "." before storing.
        All values are JSON-encoded and converted to UTF-8 bytes.
        
        Args:
            namespace: The namespace prefix for all keys.
            data: Dictionary of key-value pairs to store.
        """
        prefixed_data = {
            f"{namespace}.{key}": json.dumps(value).encode("utf-8")
            for key, value in data.items()
        }
        self._store.mset(list(prefixed_data.items()))
    
    def get(self, namespace: str, keys: list[str]) -> dict[str, Any]:
        """Load a dictionary from the underlying store for the given keys.
        
        Prefixes each key with the namespace and a "." before retrieving.
        All values are JSON-decoded from UTF-8 bytes.
        Returns an empty dict if no keys are found or all values are None.
        
        Args:
            namespace: The namespace prefix for all keys.
            keys: List of keys (without namespace prefix) to retrieve from the store.
            
        Returns:
            Dictionary mapping each unprefixed key to its value in the store.
            Returns empty dict if no keys are found.
        """
        prefixed_keys = [f"{namespace}.{key}" for key in keys]
        values_list = [
            (json.loads(b.decode("utf-8")) if b is not None else None)
            for b in self._store.mget(prefixed_keys)
        ]
        return dict(zip(keys, values_list)) if values_list else {}
