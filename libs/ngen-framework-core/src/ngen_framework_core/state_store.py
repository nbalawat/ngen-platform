"""Pluggable state store for agent checkpoint/restore.

Provides an abstract StateStore protocol and two implementations:
- InMemoryStateStore: for testing and local development
- RedisStateStore: for production use with Redis
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from ngen_framework_core.protocols import StateSnapshot

logger = logging.getLogger(__name__)


class StateStore(Protocol):
    """Protocol for persistent state storage."""

    async def save(self, snapshot: StateSnapshot) -> str:
        """Save a snapshot and return a storage key."""
        ...

    async def load(self, key: str) -> StateSnapshot | None:
        """Load a snapshot by key. Returns None if not found."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete a snapshot by key. Returns True if deleted."""
        ...

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys matching an optional prefix."""
        ...


def _snapshot_key(agent_name: str, version: int) -> str:
    """Generate a storage key for a snapshot."""
    return f"ngen:state:{agent_name}:v{version}"


def _serialize_snapshot(snapshot: StateSnapshot) -> str:
    """Serialize a StateSnapshot to JSON."""
    return json.dumps(
        {
            "agent_name": snapshot.agent_name,
            "state": snapshot.state,
            "version": snapshot.version,
            "metadata": snapshot.metadata,
        }
    )


def _deserialize_snapshot(data: str) -> StateSnapshot:
    """Deserialize a StateSnapshot from JSON."""
    d = json.loads(data)
    return StateSnapshot(
        agent_name=d["agent_name"],
        state=d["state"],
        version=d["version"],
        metadata=d.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# In-memory implementation (testing / local dev)
# ---------------------------------------------------------------------------


class InMemoryStateStore:
    """In-memory state store for testing and local development."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def save(self, snapshot: StateSnapshot) -> str:
        key = _snapshot_key(snapshot.agent_name, snapshot.version)
        self._store[key] = _serialize_snapshot(snapshot)
        logger.debug("Saved snapshot: %s", key)
        return key

    async def load(self, key: str) -> StateSnapshot | None:
        data = self._store.get(key)
        if data is None:
            return None
        return _deserialize_snapshot(data)

    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._store if k.startswith(prefix))


# ---------------------------------------------------------------------------
# Redis implementation (production)
# ---------------------------------------------------------------------------


class RedisStateStore:
    """Redis-backed state store for production use.

    Requires an ``redis.asyncio.Redis`` client instance.
    """

    def __init__(self, redis_client: Any, ttl_seconds: int | None = None) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def save(self, snapshot: StateSnapshot) -> str:
        key = _snapshot_key(snapshot.agent_name, snapshot.version)
        data = _serialize_snapshot(snapshot)
        if self._ttl:
            await self._redis.setex(key, self._ttl, data)
        else:
            await self._redis.set(key, data)
        logger.debug("Saved snapshot to Redis: %s", key)
        return key

    async def load(self, key: str) -> StateSnapshot | None:
        data = await self._redis.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return _deserialize_snapshot(data)

    async def delete(self, key: str) -> bool:
        result = await self._redis.delete(key)
        return result > 0

    async def list_keys(self, prefix: str = "") -> list[str]:
        pattern = f"{prefix}*" if prefix else "ngen:state:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            keys.append(key)
        return sorted(keys)
