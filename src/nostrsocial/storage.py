"""Persistence backends for social graph data."""

from __future__ import annotations

import base64
import json
import os
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for social graph storage backends."""

    def save(self, data: dict) -> None:
        """Persist the social graph data."""
        ...

    def load(self) -> Optional[dict]:
        """Load the social graph data. Returns None if no data exists."""
        ...


class MemoryStorage:
    """In-memory storage backend, useful for tests."""

    def __init__(self) -> None:
        self._data: Optional[dict] = None

    def save(self, data: dict) -> None:
        self._data = data

    def load(self) -> Optional[dict]:
        return self._data


class FileStorage:
    """JSON file storage backend with restrictive permissions."""

    def __init__(self, path: str) -> None:
        self._path = path

    def save(self, data: dict) -> None:
        serializable = _prepare_for_json(data)
        with open(self._path, "w") as f:
            json.dump(serializable, f, indent=2)
        os.chmod(self._path, 0o600)

    def load(self) -> Optional[dict]:
        if not os.path.exists(self._path):
            return None
        with open(self._path, "r") as f:
            data = json.load(f)
        return _restore_from_json(data)


def _prepare_for_json(data: dict) -> dict:
    """Convert bytes values to base64 strings for JSON serialization."""
    result = {}
    for key, value in data.items():
        if isinstance(value, bytes):
            result[key] = {"__bytes__": base64.b64encode(value).decode("ascii")}
        elif isinstance(value, dict):
            result[key] = _prepare_for_json(value)
        elif isinstance(value, list):
            result[key] = [
                _prepare_for_json(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value
    return result


def _restore_from_json(data: dict) -> dict:
    """Convert base64 strings back to bytes after JSON deserialization."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict) and "__bytes__" in value:
            result[key] = base64.b64decode(value["__bytes__"])
        elif isinstance(value, dict):
            result[key] = _restore_from_json(value)
        elif isinstance(value, list):
            result[key] = [
                _restore_from_json(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value
    return result
