"""Redis-backed sliding window rate limiter.

Uses Redis sorted sets for distributed rate limiting across multiple
gateway instances. Falls back to the in-memory RateLimiter if Redis
is not available.

Configuration via environment variables:
- ``REDIS_URL`` — Redis connection URL (e.g., ``redis://localhost:6379``)

When ``REDIS_URL`` is not set, the factory returns the in-memory limiter.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from model_gateway.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RedisRateLimiter(RateLimiter):
    """Distributed rate limiter backed by Redis sorted sets.

    Uses a sliding window algorithm:
    - Each request adds a member to a sorted set keyed by tenant
    - Members older than the window are removed
    - Count of remaining members determines rate
    """

    def __init__(
        self,
        redis_client: Any,
        rpm: int = 60,
        tpm: int = 100_000,
        key_prefix: str = "ngen:ratelimit",
    ) -> None:
        super().__init__(rpm=rpm, tpm=tpm)
        self._redis = redis_client
        self._key_prefix = key_prefix

    def check_request(self, tenant_id: str) -> bool:
        """Check RPM limit using Redis sliding window."""
        try:
            return self._sliding_window_check(
                f"{self._key_prefix}:rpm:{tenant_id}",
                self._rpm,
                window_seconds=60,
            )
        except Exception:
            logger.debug("Redis unavailable, falling back to in-memory RPM check")
            return super().check_request(tenant_id)

    def check_tokens(self, tenant_id: str, tokens: int) -> bool:
        """Check TPM limit using Redis."""
        try:
            return self._sliding_window_check(
                f"{self._key_prefix}:tpm:{tenant_id}",
                self._tpm,
                window_seconds=60,
                cost=tokens,
            )
        except Exception:
            logger.debug("Redis unavailable, falling back to in-memory TPM check")
            return super().check_tokens(tenant_id, tokens)

    def remaining_rpm(self, tenant_id: str) -> int:
        """Get remaining RPM quota from Redis."""
        try:
            count = self._current_count(
                f"{self._key_prefix}:rpm:{tenant_id}", window_seconds=60
            )
            return max(0, self._rpm - count)
        except Exception:
            return super().remaining_rpm(tenant_id)

    def remaining_tpm(self, tenant_id: str) -> int:
        """Get remaining TPM quota from Redis."""
        try:
            count = self._current_count(
                f"{self._key_prefix}:tpm:{tenant_id}", window_seconds=60
            )
            return max(0, self._tpm - count)
        except Exception:
            return super().remaining_tpm(tenant_id)

    def _sliding_window_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> bool:
        """Sliding window rate limit check using Redis sorted sets."""
        now = time.time()
        window_start = now - window_seconds

        pipe = self._redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current window
        pipe.zcard(key)
        results = pipe.execute()
        current_count = results[1]

        if current_count + cost > limit:
            return False

        # Add new entry (score = timestamp, member = unique timestamp)
        # Use cost as a way to add multiple members for token tracking
        pipe2 = self._redis.pipeline()
        for i in range(cost):
            pipe2.zadd(key, {f"{now}:{i}": now})
        pipe2.expire(key, window_seconds + 10)
        pipe2.execute()
        return True

    def _current_count(self, key: str, window_seconds: int) -> int:
        """Count entries in the current window."""
        now = time.time()
        window_start = now - window_seconds
        self._redis.zremrangebyscore(key, 0, window_start)
        return self._redis.zcard(key)


def create_rate_limiter(
    rpm: int = 60,
    tpm: int = 100_000,
    redis_url: str | None = None,
) -> RateLimiter:
    """Factory: create a RedisRateLimiter if Redis is available, else in-memory.

    Args:
        rpm: Requests per minute limit.
        tpm: Tokens per minute limit.
        redis_url: Redis URL. If None, checks REDIS_URL env var.
    """
    import os
    url = redis_url or os.environ.get("REDIS_URL", "")

    if url:
        try:
            import redis
            client = redis.from_url(url, decode_responses=True, socket_timeout=2)
            client.ping()
            logger.info("Redis rate limiter connected at %s", url)
            return RedisRateLimiter(redis_client=client, rpm=rpm, tpm=tpm)
        except Exception as exc:
            logger.warning("Redis not available (%s), using in-memory rate limiter", exc)

    return RateLimiter(rpm=rpm, tpm=tpm)
