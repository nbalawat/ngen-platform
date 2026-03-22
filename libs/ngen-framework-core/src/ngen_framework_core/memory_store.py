"""Memory store implementations for the multi-tenant memory subsystem.

Provides InMemoryMemoryStore (testing) and RedisMemoryStore (production)
implementations of the MemoryStore protocol.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from typing import Any

from .protocols import MemoryEntry, MemoryScope, MemoryStore, MemoryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matches_scope(entry: MemoryEntry, scope: MemoryScope) -> bool:
    """Check if an entry's scope matches the given scope prefix."""
    return entry.scope.to_prefix().startswith(scope.to_prefix())


def _is_expired(entry: MemoryEntry, now: float | None = None) -> bool:
    """Check if an entry has expired based on its TTL."""
    if entry.ttl_seconds is None:
        return False
    now = now or time.time()
    return entry.created_at + entry.ttl_seconds < now


def _serialize_entry(entry: MemoryEntry) -> str:
    """Serialize a MemoryEntry to JSON string."""
    return json.dumps({
        "id": entry.id,
        "memory_type": entry.memory_type.value,
        "scope": {
            "org_id": entry.scope.org_id,
            "team_id": entry.scope.team_id,
            "project_id": entry.scope.project_id,
            "agent_name": entry.scope.agent_name,
            "thread_id": entry.scope.thread_id,
        },
        "content": entry.content,
        "metadata": entry.metadata,
        "role": entry.role,
        "embedding": entry.embedding,
        "created_at": entry.created_at,
        "ttl_seconds": entry.ttl_seconds,
        "summary_id": entry.summary_id,
        "size_bytes": entry.size_bytes,
        "token_estimate": entry.token_estimate,
    })


def _deserialize_entry(data: str) -> MemoryEntry:
    """Deserialize a JSON string to MemoryEntry."""
    d = json.loads(data)
    return MemoryEntry(
        id=d["id"],
        memory_type=MemoryType(d["memory_type"]),
        scope=MemoryScope(**d["scope"]),
        content=d["content"],
        metadata=d.get("metadata", {}),
        role=d.get("role"),
        embedding=d.get("embedding"),
        created_at=d.get("created_at", 0.0),
        ttl_seconds=d.get("ttl_seconds"),
        summary_id=d.get("summary_id"),
        size_bytes=d.get("size_bytes", 0),
        token_estimate=d.get("token_estimate", 0),
    )


# ---------------------------------------------------------------------------
# InMemoryMemoryStore
# ---------------------------------------------------------------------------


class InMemoryMemoryStore:
    """In-memory MemoryStore implementation for testing.

    Stores entries in a dict keyed by entry ID. Supports cosine similarity
    search on embeddings for semantic retrieval testing.
    """

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    async def write(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if entry.created_at == 0.0:
            entry.created_at = time.time()
        self._entries[entry.id] = entry
        return entry.id

    async def read(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        now = time.time()
        results = [
            e
            for e in self._entries.values()
            if _matches_scope(e, scope)
            and e.memory_type == memory_type
            and not _is_expired(e, now)
        ]
        if filters:
            for key, value in filters.items():
                if key == "summary_id":
                    results = [e for e in results if e.summary_id == value]
                elif key == "role":
                    results = [e for e in results if e.role == value]
                elif key == "unsummarized":
                    results = [e for e in results if e.summary_id is None]
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    async def search(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        now = time.time()
        candidates = [
            e
            for e in self._entries.values()
            if _matches_scope(e, scope)
            and e.memory_type == memory_type
            and e.embedding is not None
            and not _is_expired(e, now)
        ]
        scored = [
            (e, _cosine_similarity(query_embedding, e.embedding))  # type: ignore[arg-type]
            for e in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:top_k]]

    async def update(
        self,
        entry_id: str,
        scope: MemoryScope,
        updates: dict[str, Any],
    ) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None or not _matches_scope(entry, scope):
            return False
        for key, value in updates.items():
            if key == "content":
                entry.content = value
            elif key == "summary_id":
                entry.summary_id = value
            elif key == "metadata":
                entry.metadata.update(value)
            elif key == "embedding":
                entry.embedding = value
        return True

    async def delete(self, entry_id: str, scope: MemoryScope) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None or not _matches_scope(entry, scope):
            return False
        del self._entries[entry_id]
        return True

    async def delete_by_scope(
        self,
        scope: MemoryScope,
        memory_type: MemoryType | None = None,
    ) -> int:
        to_delete = [
            eid
            for eid, e in self._entries.items()
            if _matches_scope(e, scope)
            and (memory_type is None or e.memory_type == memory_type)
        ]
        for eid in to_delete:
            del self._entries[eid]
        return len(to_delete)

    async def expire(self, scope: MemoryScope, before_timestamp: float) -> int:
        to_delete = [
            eid
            for eid, e in self._entries.items()
            if _matches_scope(e, scope) and e.created_at < before_timestamp
        ]
        for eid in to_delete:
            del self._entries[eid]
        return len(to_delete)

    async def count(self, scope: MemoryScope, memory_type: MemoryType) -> int:
        now = time.time()
        return sum(
            1
            for e in self._entries.values()
            if _matches_scope(e, scope)
            and e.memory_type == memory_type
            and not _is_expired(e, now)
        )

    async def stats(self, scope: MemoryScope) -> dict[str, Any]:
        now = time.time()
        result: dict[str, dict[str, int]] = {}
        for e in self._entries.values():
            if not _matches_scope(e, scope) or _is_expired(e, now):
                continue
            key = e.memory_type.value
            if key not in result:
                result[key] = {"count": 0, "size_bytes": 0, "token_estimate": 0}
            result[key]["count"] += 1
            result[key]["size_bytes"] += e.size_bytes
            result[key]["token_estimate"] += e.token_estimate
        return result


# ---------------------------------------------------------------------------
# RedisMemoryStore
# ---------------------------------------------------------------------------


class RedisMemoryStore:
    """Redis-backed MemoryStore for production structured data.

    Key pattern: {scope.to_prefix()}:{memory_type}:{entry_id}
    Values: JSON-serialized MemoryEntry.
    """

    def __init__(self, redis_client: Any, default_ttl: int | None = None) -> None:
        self._redis = redis_client
        self._default_ttl = default_ttl

    def _key(self, scope: MemoryScope, memory_type: MemoryType, entry_id: str) -> str:
        return f"{scope.to_prefix()}:{memory_type.value}:{entry_id}"

    def _scan_pattern(
        self,
        scope: MemoryScope,
        memory_type: MemoryType | None = None,
    ) -> str:
        base = scope.to_prefix()
        if memory_type:
            return f"{base}:{memory_type.value}:*"
        return f"{base}:*"

    async def write(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if entry.created_at == 0.0:
            entry.created_at = time.time()
        key = self._key(entry.scope, entry.memory_type, entry.id)
        data = _serialize_entry(entry)
        ttl = entry.ttl_seconds or self._default_ttl
        if ttl:
            await self._redis.setex(key, ttl, data)
        else:
            await self._redis.set(key, data)
        return entry.id

    async def read(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        pattern = self._scan_pattern(scope, memory_type)
        entries: list[MemoryEntry] = []
        async for key in self._redis.scan_iter(match=pattern, count=200):
            raw = await self._redis.get(key)
            if raw is None:
                continue
            entry = _deserialize_entry(
                raw if isinstance(raw, str) else raw.decode("utf-8")
            )
            if filters:
                if "unsummarized" in filters and entry.summary_id is not None:
                    continue
                if "summary_id" in filters and entry.summary_id != filters["summary_id"]:
                    continue
                if "role" in filters and entry.role != filters["role"]:
                    continue
            entries.append(entry)
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:limit]

    async def search(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        # Basic implementation: load all entries and compute cosine similarity.
        # Production vector search (Redis VSS, pgvector) would use native indexes.
        all_entries = await self.read(scope, memory_type, limit=1000)
        candidates = [e for e in all_entries if e.embedding is not None]
        scored = [
            (e, _cosine_similarity(query_embedding, e.embedding))  # type: ignore[arg-type]
            for e in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:top_k]]

    async def update(
        self,
        entry_id: str,
        scope: MemoryScope,
        updates: dict[str, Any],
    ) -> bool:
        # Try all memory types to find the entry
        for mt in MemoryType:
            key = self._key(scope, mt, entry_id)
            raw = await self._redis.get(key)
            if raw is not None:
                entry = _deserialize_entry(
                    raw if isinstance(raw, str) else raw.decode("utf-8")
                )
                for k, v in updates.items():
                    if k == "content":
                        entry.content = v
                    elif k == "summary_id":
                        entry.summary_id = v
                    elif k == "metadata":
                        entry.metadata.update(v)
                    elif k == "embedding":
                        entry.embedding = v
                data = _serialize_entry(entry)
                ttl_remaining = await self._redis.ttl(key)
                if ttl_remaining and ttl_remaining > 0:
                    await self._redis.setex(key, ttl_remaining, data)
                else:
                    await self._redis.set(key, data)
                return True
        return False

    async def delete(self, entry_id: str, scope: MemoryScope) -> bool:
        for mt in MemoryType:
            key = self._key(scope, mt, entry_id)
            result = await self._redis.delete(key)
            if result:
                return True
        return False

    async def delete_by_scope(
        self,
        scope: MemoryScope,
        memory_type: MemoryType | None = None,
    ) -> int:
        pattern = self._scan_pattern(scope, memory_type)
        count = 0
        async for key in self._redis.scan_iter(match=pattern, count=200):
            await self._redis.delete(key)
            count += 1
        return count

    async def expire(self, scope: MemoryScope, before_timestamp: float) -> int:
        pattern = self._scan_pattern(scope)
        count = 0
        async for key in self._redis.scan_iter(match=pattern, count=200):
            raw = await self._redis.get(key)
            if raw is None:
                continue
            entry = _deserialize_entry(
                raw if isinstance(raw, str) else raw.decode("utf-8")
            )
            if entry.created_at < before_timestamp:
                await self._redis.delete(key)
                count += 1
        return count

    async def count(self, scope: MemoryScope, memory_type: MemoryType) -> int:
        pattern = self._scan_pattern(scope, memory_type)
        count = 0
        async for _ in self._redis.scan_iter(match=pattern, count=200):
            count += 1
        return count

    async def stats(self, scope: MemoryScope) -> dict[str, Any]:
        pattern = self._scan_pattern(scope)
        result: dict[str, dict[str, int]] = {}
        async for key in self._redis.scan_iter(match=pattern, count=200):
            raw = await self._redis.get(key)
            if raw is None:
                continue
            entry = _deserialize_entry(
                raw if isinstance(raw, str) else raw.decode("utf-8")
            )
            mt = entry.memory_type.value
            if mt not in result:
                result[mt] = {"count": 0, "size_bytes": 0, "token_estimate": 0}
            result[mt]["count"] += 1
            result[mt]["size_bytes"] += entry.size_bytes
            result[mt]["token_estimate"] += entry.token_estimate
        return result
