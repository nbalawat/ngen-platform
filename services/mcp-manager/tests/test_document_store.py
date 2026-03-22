"""Tests for filesystem document store."""

from __future__ import annotations

import pytest

from mcp_manager.documents.store import FileSystemDocumentStore


@pytest.fixture()
def store(tmp_path):
    return FileSystemDocumentStore(base_dir=str(tmp_path))


class TestFileSystemDocumentStore:
    def test_save_and_load(self, store):
        content = b"Hello, world!"
        store.save("tenant-a", "docs", "test.txt", content)
        loaded = store.load("tenant-a", "docs", "test.txt")
        assert loaded == content

    def test_tenant_isolation(self, store):
        store.save("tenant-a", "docs", "secret.txt", b"tenant A data")
        store.save("tenant-b", "docs", "secret.txt", b"tenant B data")

        assert store.load("tenant-a", "docs", "secret.txt") == b"tenant A data"
        assert store.load("tenant-b", "docs", "secret.txt") == b"tenant B data"

    def test_load_nonexistent_raises(self, store):
        with pytest.raises(FileNotFoundError):
            store.load("tenant-a", "docs", "nonexistent.txt")

    def test_list_files(self, store):
        store.save("tenant-a", "docs", "a.txt", b"a")
        store.save("tenant-a", "docs", "b.txt", b"b")
        store.save("tenant-a", "other", "c.txt", b"c")

        files = store.list_files("tenant-a", "docs")
        assert sorted(files) == ["a.txt", "b.txt"]

    def test_list_empty_collection(self, store):
        assert store.list_files("tenant-a", "nonexistent") == []

    def test_delete(self, store):
        store.save("tenant-a", "docs", "test.txt", b"data")
        assert store.delete("tenant-a", "docs", "test.txt") is True
        assert store.delete("tenant-a", "docs", "test.txt") is False

    def test_delete_collection(self, store):
        store.save("tenant-a", "docs", "a.txt", b"a")
        store.save("tenant-a", "docs", "b.txt", b"b")
        count = store.delete_collection("tenant-a", "docs")
        assert count == 2
        assert store.list_files("tenant-a", "docs") == []

    def test_path_traversal_prevention(self, store):
        """Filenames with path traversal characters are sanitized."""
        store.save("tenant-a", "docs", "../../../etc/passwd", b"safe")
        # Should be stored safely, not at the traversal path
        files = store.list_files("tenant-a", "docs")
        assert len(files) == 1
        assert "etc" not in files[0]
