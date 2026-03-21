"""Redis-backed policy repository.

Stores governance policies in Redis hashes for persistence across
restarts. Falls back to the in-memory PolicyRepository if Redis
is not available.

Each policy is stored as a JSON string in a Redis hash keyed by
``ngen:policies``, with the policy ID as the hash field.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from governance_service.models import Policy, PolicyCreate, PolicyUpdate
from governance_service.repository import PolicyRepository

logger = logging.getLogger(__name__)


class RedisPolicyRepository(PolicyRepository):
    """Redis-backed policy repository.

    Extends PolicyRepository to persist policies in Redis while
    keeping the in-memory dict as a read cache.
    """

    def __init__(self, redis_client: Any, hash_key: str = "ngen:policies") -> None:
        super().__init__()
        self._redis = redis_client
        self._hash_key = hash_key
        self._load_from_redis()

    def _load_from_redis(self) -> None:
        """Load all policies from Redis into the in-memory cache."""
        try:
            all_data = self._redis.hgetall(self._hash_key)
            for policy_id, policy_json in all_data.items():
                try:
                    policy = Policy.model_validate_json(policy_json)
                    self._policies[policy.id] = policy
                except Exception:
                    logger.warning("Failed to parse policy %s from Redis", policy_id)
            logger.info("Loaded %d policies from Redis", len(self._policies))
        except Exception as exc:
            logger.warning("Failed to load policies from Redis: %s", exc)

    def _persist(self, policy: Policy) -> None:
        """Write a policy to Redis."""
        try:
            self._redis.hset(
                self._hash_key,
                policy.id,
                policy.model_dump_json(),
            )
        except Exception as exc:
            logger.warning("Failed to persist policy %s to Redis: %s", policy.id, exc)

    def _remove(self, policy_id: str) -> None:
        """Remove a policy from Redis."""
        try:
            self._redis.hdel(self._hash_key, policy_id)
        except Exception as exc:
            logger.warning("Failed to remove policy %s from Redis: %s", policy_id, exc)

    def create(self, data: PolicyCreate) -> Policy:
        policy = super().create(data)
        self._persist(policy)
        return policy

    def update(self, policy_id: str, data: PolicyUpdate) -> Policy | None:
        policy = super().update(policy_id, data)
        if policy:
            self._persist(policy)
        return policy

    def delete(self, policy_id: str) -> bool:
        result = super().delete(policy_id)
        if result:
            self._remove(policy_id)
        return result


def create_policy_repository(redis_url: str | None = None) -> PolicyRepository:
    """Factory: create a RedisPolicyRepository if Redis is available, else in-memory.

    Args:
        redis_url: Redis URL. If None, checks REDIS_URL env var.
    """
    import os
    url = redis_url or os.environ.get("REDIS_URL", "")

    if url:
        try:
            import redis
            client = redis.from_url(url, decode_responses=True, socket_timeout=2)
            client.ping()
            logger.info("Redis policy repository connected at %s", url)
            return RedisPolicyRepository(redis_client=client)
        except Exception as exc:
            logger.warning("Redis not available (%s), using in-memory policy repository", exc)

    return PolicyRepository()
