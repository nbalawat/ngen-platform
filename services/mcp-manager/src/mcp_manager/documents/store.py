"""Document storage — filesystem-based, expandable to cloud.

Stores raw uploaded files organized by tenant and collection.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = os.environ.get("NGEN_DOCUMENT_STORE_PATH", "data/documents")


@runtime_checkable
class DocumentStore(Protocol):
    """Protocol for document file storage."""

    def save(self, tenant_id: str, collection: str, filename: str, content: bytes) -> str:
        """Save a file. Returns the storage path."""
        ...

    def load(self, tenant_id: str, collection: str, filename: str) -> bytes:
        """Load a file's content."""
        ...

    def delete(self, tenant_id: str, collection: str, filename: str) -> bool:
        """Delete a file. Returns True if it existed."""
        ...

    def list_files(self, tenant_id: str, collection: str) -> list[str]:
        """List filenames in a tenant's collection."""
        ...

    def delete_collection(self, tenant_id: str, collection: str) -> int:
        """Delete all files in a collection. Returns count deleted."""
        ...


class FileSystemDocumentStore:
    """Stores documents on the local filesystem.

    Layout: {base_dir}/{tenant_id}/{collection}/{filename}
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir or _DEFAULT_BASE_DIR)

    def _path(self, tenant_id: str, collection: str, filename: str) -> Path:
        # Sanitize path components to prevent traversal
        safe_tenant = tenant_id.replace("/", "_").replace("..", "_")
        safe_collection = collection.replace("/", "_").replace("..", "_")
        safe_filename = os.path.basename(filename)
        return self._base_dir / safe_tenant / safe_collection / safe_filename

    def save(self, tenant_id: str, collection: str, filename: str, content: bytes) -> str:
        path = self._path(tenant_id, collection, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.info("Saved document: %s (%d bytes)", path, len(content))
        return str(path)

    def load(self, tenant_id: str, collection: str, filename: str) -> bytes:
        path = self._path(tenant_id, collection, filename)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        return path.read_bytes()

    def delete(self, tenant_id: str, collection: str, filename: str) -> bool:
        path = self._path(tenant_id, collection, filename)
        if path.exists():
            path.unlink()
            logger.info("Deleted document: %s", path)
            return True
        return False

    def list_files(self, tenant_id: str, collection: str) -> list[str]:
        dir_path = self._base_dir / tenant_id.replace("/", "_") / collection.replace("/", "_")
        if not dir_path.exists():
            return []
        return sorted(f.name for f in dir_path.iterdir() if f.is_file())

    def delete_collection(self, tenant_id: str, collection: str) -> int:
        dir_path = self._base_dir / tenant_id.replace("/", "_") / collection.replace("/", "_")
        if not dir_path.exists():
            return 0
        files = [f for f in dir_path.iterdir() if f.is_file()]
        count = len(files)
        shutil.rmtree(dir_path)
        return count
