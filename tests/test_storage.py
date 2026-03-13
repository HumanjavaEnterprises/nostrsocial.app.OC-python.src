"""Tests for storage backends."""

import json
import os

from nostrsocial.storage import FileStorage, MemoryStorage


class TestMemoryStorage:
    def test_empty_load(self):
        storage = MemoryStorage()
        assert storage.load() is None

    def test_roundtrip(self):
        storage = MemoryStorage()
        data = {"key": "value", "nested": {"a": 1}}
        storage.save(data)
        loaded = storage.load()
        assert loaded == data

    def test_overwrite(self):
        storage = MemoryStorage()
        storage.save({"v": 1})
        storage.save({"v": 2})
        assert storage.load()["v"] == 2


class TestFileStorage:
    def test_empty_load(self, tmp_path):
        storage = FileStorage(str(tmp_path / "data.json"))
        assert storage.load() is None

    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        data = {"key": "value", "count": 42}
        storage.save(data)

        loaded = storage.load()
        assert loaded["key"] == "value"
        assert loaded["count"] == 42

    def test_file_permissions(self, tmp_path):
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        storage.save({"test": True})

        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    def test_bytes_roundtrip(self, tmp_path):
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        secret = b"\x01\x02\x03\x04" * 8
        data = {"device_secret": secret, "version": "0.1.0"}
        storage.save(data)

        loaded = storage.load()
        assert loaded["device_secret"] == secret
        assert loaded["version"] == "0.1.0"

    def test_nested_bytes(self, tmp_path):
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        data = {
            "outer": {
                "secret": b"\xaa\xbb\xcc\xdd",
                "label": "test",
            }
        }
        storage.save(data)
        loaded = storage.load()
        assert loaded["outer"]["secret"] == b"\xaa\xbb\xcc\xdd"
        assert loaded["outer"]["label"] == "test"

    def test_atomic_write_no_temp_file_left(self, tmp_path):
        """Temp file should not exist after successful save."""
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        storage.save({"test": True})
        assert not os.path.exists(path + ".tmp")
        assert os.path.exists(path)

    def test_contacts_with_linked_channels_roundtrip(self, tmp_path):
        """Contact dicts with linked_channels survive FileStorage roundtrip."""
        path = str(tmp_path / "data.json")
        storage = FileStorage(path)
        data = {
            "device_secret": b"\x01" * 32,
            "contacts": [
                {
                    "identifier": "alice@example.com",
                    "channel": "email",
                    "list_type": "friends",
                    "tier": "close",
                    "identity_state": "proxy",
                    "proxy_npub": "npub1test",
                    "claimed_npub": None,
                    "display_name": "Alice",
                    "added_at": 1000.0,
                    "last_interaction": 2000.0,
                    "interaction_count": 5,
                    "notes": None,
                    "upgrade_hint": "",
                    "linked_channels": {"twitter": "@alice", "phone": "+15551234567"},
                }
            ],
            "version": "0.1.0",
        }
        storage.save(data)
        loaded = storage.load()
        contact = loaded["contacts"][0]
        assert contact["linked_channels"] == {"twitter": "@alice", "phone": "+15551234567"}
