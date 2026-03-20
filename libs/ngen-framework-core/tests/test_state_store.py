"""Tests for the pluggable state store implementations."""

from __future__ import annotations

import pytest
import redis.asyncio as aioredis

from ngen_framework_core.protocols import StateSnapshot
from ngen_framework_core.state_store import (
    InMemoryStateStore,
    RedisStateStore,
    _deserialize_snapshot,
    _serialize_snapshot,
    _snapshot_key,
)


def _docker_available() -> bool:
    """Check if Docker daemon is reachable."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


_skip_no_docker = pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon not available"
)

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_snapshot() -> StateSnapshot:
    return StateSnapshot(
        agent_name="test-agent",
        state={"messages": [{"role": "user", "content": "hello"}]},
        version=1,
        metadata={"created_by": "test"},
    )


@pytest.fixture
def sample_snapshot_v2() -> StateSnapshot:
    return StateSnapshot(
        agent_name="test-agent",
        state={
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
        },
        version=2,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


class TestSerializationHelpers:
    def test_snapshot_key(self) -> None:
        assert _snapshot_key("my-agent", 1) == "ngen:state:my-agent:v1"
        assert _snapshot_key("other", 42) == "ngen:state:other:v42"

    def test_serialize_deserialize_roundtrip(self, sample_snapshot: StateSnapshot) -> None:
        data = _serialize_snapshot(sample_snapshot)
        restored = _deserialize_snapshot(data)
        assert restored.agent_name == sample_snapshot.agent_name
        assert restored.state == sample_snapshot.state
        assert restored.version == sample_snapshot.version
        assert restored.metadata == sample_snapshot.metadata

    def test_deserialize_missing_metadata(self) -> None:
        import json

        data = json.dumps({"agent_name": "a", "state": {}, "version": 1})
        restored = _deserialize_snapshot(data)
        assert restored.metadata == {}


# ---------------------------------------------------------------------------
# InMemoryStateStore
# ---------------------------------------------------------------------------


class TestInMemoryStateStore:
    async def test_save_and_load(self, sample_snapshot: StateSnapshot) -> None:
        store = InMemoryStateStore()
        key = await store.save(sample_snapshot)
        assert key == "ngen:state:test-agent:v1"

        loaded = await store.load(key)
        assert loaded is not None
        assert loaded.agent_name == "test-agent"
        assert loaded.state == sample_snapshot.state

    async def test_load_missing_returns_none(self) -> None:
        store = InMemoryStateStore()
        assert await store.load("nonexistent") is None

    async def test_delete_existing(self, sample_snapshot: StateSnapshot) -> None:
        store = InMemoryStateStore()
        key = await store.save(sample_snapshot)
        assert await store.delete(key) is True
        assert await store.load(key) is None

    async def test_delete_missing_returns_false(self) -> None:
        store = InMemoryStateStore()
        assert await store.delete("nonexistent") is False

    async def test_list_keys_empty(self) -> None:
        store = InMemoryStateStore()
        assert await store.list_keys() == []

    async def test_list_keys_with_prefix(
        self, sample_snapshot: StateSnapshot, sample_snapshot_v2: StateSnapshot
    ) -> None:
        store = InMemoryStateStore()
        await store.save(sample_snapshot)
        await store.save(sample_snapshot_v2)

        keys = await store.list_keys("ngen:state:test-agent")
        assert len(keys) == 2
        assert keys == sorted(keys)

    async def test_list_keys_prefix_filters(self, sample_snapshot: StateSnapshot) -> None:
        store = InMemoryStateStore()
        await store.save(sample_snapshot)

        other = StateSnapshot(agent_name="other-agent", state={}, version=1, metadata={})
        await store.save(other)

        keys = await store.list_keys("ngen:state:test-agent")
        assert len(keys) == 1
        assert "test-agent" in keys[0]

    async def test_overwrite_same_version(self, sample_snapshot: StateSnapshot) -> None:
        store = InMemoryStateStore()
        await store.save(sample_snapshot)

        updated = StateSnapshot(
            agent_name="test-agent",
            state={"messages": [{"role": "user", "content": "updated"}]},
            version=1,
            metadata={},
        )
        key = await store.save(updated)
        loaded = await store.load(key)
        assert loaded is not None
        assert loaded.state["messages"][0]["content"] == "updated"


# ---------------------------------------------------------------------------
# RedisStateStore (real Redis via Testcontainers)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def redis_container():
    """Start a real Redis container for the test module."""
    import os
    import subprocess

    from testcontainers.redis import RedisContainer

    # Ensure DOCKER_HOST is set for the Python Docker SDK (Docker Desktop
    # uses a non-default socket path on macOS).
    if not os.environ.get("DOCKER_HOST"):
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["DOCKER_HOST"] = result.stdout.strip()

    # Disable Ryuk (Testcontainers reaper) — it tries to mount the Docker
    # socket inside a container which fails on Docker Desktop for macOS.
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

    with RedisContainer("redis:7") as container:
        yield container


@pytest.fixture()
async def redis_client(redis_container):
    """Create a fresh async Redis client and flush the DB before each test."""
    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))
    client = aioredis.Redis(host=host, port=port, decode_responses=False)
    await client.flushdb()
    yield client
    await client.aclose()


@_skip_no_docker
class TestRedisStateStore:
    async def test_save_without_ttl(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        key = await store.save(sample_snapshot)

        assert key == "ngen:state:test-agent:v1"
        # Verify data actually landed in Redis
        raw = await redis_client.get(key)
        assert raw is not None
        # No TTL set
        ttl = await redis_client.ttl(key)
        assert ttl == -1  # -1 means no expiry

    async def test_save_with_ttl(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client, ttl_seconds=3600)
        key = await store.save(sample_snapshot)

        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 3600

    async def test_load_returns_none_when_missing(self, redis_client) -> None:
        store = RedisStateStore(redis_client)
        result = await store.load("ngen:state:missing:v1")
        assert result is None

    async def test_load_returns_snapshot(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        key = await store.save(sample_snapshot)

        loaded = await store.load(key)
        assert loaded is not None
        assert loaded.agent_name == "test-agent"
        assert loaded.state == sample_snapshot.state
        assert loaded.version == sample_snapshot.version
        assert loaded.metadata == sample_snapshot.metadata

    async def test_save_and_load_roundtrip(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        key = await store.save(sample_snapshot)
        loaded = await store.load(key)
        assert loaded is not None
        assert loaded.agent_name == sample_snapshot.agent_name
        assert loaded.state == sample_snapshot.state

    async def test_delete_existing_returns_true(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        key = await store.save(sample_snapshot)
        assert await store.delete(key) is True
        # Verify actually gone
        assert await store.load(key) is None

    async def test_delete_missing_returns_false(self, redis_client) -> None:
        store = RedisStateStore(redis_client)
        assert await store.delete("nonexistent-key") is False

    async def test_list_keys_empty(self, redis_client) -> None:
        store = RedisStateStore(redis_client)
        keys = await store.list_keys()
        assert keys == []

    async def test_list_keys_with_results(
        self, redis_client, sample_snapshot: StateSnapshot, sample_snapshot_v2: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        await store.save(sample_snapshot)
        await store.save(sample_snapshot_v2)

        keys = await store.list_keys("ngen:state:test-agent")
        assert len(keys) == 2
        assert keys == sorted(keys)

    async def test_list_keys_prefix_filters(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        await store.save(sample_snapshot)

        other = StateSnapshot(agent_name="other-agent", state={}, version=1, metadata={})
        await store.save(other)

        keys = await store.list_keys("ngen:state:test-agent")
        assert len(keys) == 1
        assert "test-agent" in keys[0]

    async def test_overwrite_same_version(
        self, redis_client, sample_snapshot: StateSnapshot
    ) -> None:
        store = RedisStateStore(redis_client)
        await store.save(sample_snapshot)

        updated = StateSnapshot(
            agent_name="test-agent",
            state={"messages": [{"role": "user", "content": "updated"}]},
            version=1,
            metadata={},
        )
        key = await store.save(updated)
        loaded = await store.load(key)
        assert loaded is not None
        assert loaded.state["messages"][0]["content"] == "updated"
