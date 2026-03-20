"""Integration tests for RedisMemoryStore using Testcontainers."""

from __future__ import annotations

import os
import subprocess
import time

import pytest
import redis.asyncio as aioredis

from ngen_framework_core.memory_store import RedisMemoryStore
from ngen_framework_core.protocols import (
    MemoryEntry,
    MemoryScope,
    MemoryType,
)


def _docker_available() -> bool:
    """Check if Docker daemon is reachable."""
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def redis_container():
    """Start a real Redis container for the test module."""
    from testcontainers.redis import RedisContainer

    if not os.environ.get("DOCKER_HOST"):
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["DOCKER_HOST"] = result.stdout.strip()

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


@pytest.fixture
def scope_a() -> MemoryScope:
    return MemoryScope(
        org_id="acme", team_id="eng", project_id="proj1", agent_name="bot-a"
    )


@pytest.fixture
def scope_b() -> MemoryScope:
    return MemoryScope(
        org_id="other", team_id="ops", project_id="proj2", agent_name="bot-b"
    )


def _entry(
    scope: MemoryScope,
    memory_type: MemoryType = MemoryType.CONVERSATIONAL,
    content: str = "hello",
    **kwargs,
) -> MemoryEntry:
    return MemoryEntry(
        id="",
        memory_type=memory_type,
        scope=scope,
        content=content,
        created_at=kwargs.pop("created_at", time.time()),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_skip_no_docker
class TestRedisMemoryStore:
    async def test_write_and_read(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        eid = await store.write(_entry(scope_a, content="msg1"))
        assert eid

        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(results) == 1
        assert results[0].content == "msg1"

    async def test_scope_isolation(self, redis_client, scope_a, scope_b):
        store = RedisMemoryStore(redis_client)
        await store.write(_entry(scope_a, content="a-msg"))
        await store.write(_entry(scope_b, content="b-msg"))

        results_a = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        results_b = await store.read(scope_b, MemoryType.CONVERSATIONAL)

        assert len(results_a) == 1
        assert results_a[0].content == "a-msg"
        assert len(results_b) == 1
        assert results_b[0].content == "b-msg"

    async def test_delete(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        eid = await store.write(_entry(scope_a))
        assert await store.delete(eid, scope_a)
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 0

    async def test_delete_by_scope(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        await store.write(_entry(scope_a, content="m1"))
        await store.write(
            _entry(scope_a, memory_type=MemoryType.TOOL_LOG, content="log")
        )
        count = await store.delete_by_scope(scope_a)
        assert count == 2

    async def test_expire(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        await store.write(_entry(scope_a, content="old", created_at=100.0))
        await store.write(_entry(scope_a, content="new", created_at=9999999.0))
        count = await store.expire(scope_a, before_timestamp=500.0)
        assert count == 1

        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(results) == 1
        assert results[0].content == "new"

    async def test_update(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        eid = await store.write(_entry(scope_a, content="old"))
        ok = await store.update(eid, scope_a, {"content": "new"})
        assert ok

        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert results[0].content == "new"

    async def test_count(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 0
        await store.write(_entry(scope_a))
        await store.write(_entry(scope_a, content="m2"))
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 2

    async def test_ttl_applied(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client, default_ttl=3600)
        eid = await store.write(_entry(scope_a))

        # Find the key and check TTL
        pattern = f"{scope_a.to_prefix()}:*"
        keys = []
        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key)
        assert len(keys) == 1
        ttl = await redis_client.ttl(keys[0])
        assert 0 < ttl <= 3600

    async def test_search_cosine(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        await store.write(
            _entry(
                scope_a,
                memory_type=MemoryType.KNOWLEDGE_BASE,
                content="dogs",
                embedding=[1.0, 0.0, 0.0],
            )
        )
        await store.write(
            _entry(
                scope_a,
                memory_type=MemoryType.KNOWLEDGE_BASE,
                content="cats",
                embedding=[0.0, 1.0, 0.0],
            )
        )
        results = await store.search(
            scope_a, MemoryType.KNOWLEDGE_BASE, [1.0, 0.0, 0.0], top_k=1
        )
        assert len(results) == 1
        assert results[0].content == "dogs"

    async def test_filter_unsummarized(self, redis_client, scope_a):
        store = RedisMemoryStore(redis_client)
        eid = await store.write(_entry(scope_a, content="summarized"))
        await store.update(eid, scope_a, {"summary_id": "s1"})
        await store.write(_entry(scope_a, content="unsummarized"))

        results = await store.read(
            scope_a,
            MemoryType.CONVERSATIONAL,
            filters={"unsummarized": True},
        )
        assert len(results) == 1
        assert results[0].content == "unsummarized"
