"""In-memory token bucket rate limiter for the Crawl phase."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Token bucket rate limiter.

    Supports both requests-per-minute (RPM) and tokens-per-minute (TPM).
    """

    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity, self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now

    def try_consume(self, amount: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        self._refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    @property
    def remaining(self) -> int:
        self._refill()
        return int(self.tokens)


class RateLimiter:
    """Per-tenant rate limiter with RPM and TPM buckets."""

    def __init__(
        self,
        rpm: int = 60,
        tpm: int = 100_000,
    ) -> None:
        self._rpm = rpm
        self._tpm = tpm
        self._rpm_buckets: dict[str, TokenBucket] = {}
        self._tpm_buckets: dict[str, TokenBucket] = {}

    def _get_rpm_bucket(self, tenant_id: str) -> TokenBucket:
        if tenant_id not in self._rpm_buckets:
            self._rpm_buckets[tenant_id] = TokenBucket(
                capacity=self._rpm,
                refill_rate=self._rpm / 60.0,
            )
        return self._rpm_buckets[tenant_id]

    def _get_tpm_bucket(self, tenant_id: str) -> TokenBucket:
        if tenant_id not in self._tpm_buckets:
            self._tpm_buckets[tenant_id] = TokenBucket(
                capacity=self._tpm,
                refill_rate=self._tpm / 60.0,
            )
        return self._tpm_buckets[tenant_id]

    def check_request(self, tenant_id: str) -> bool:
        """Check if a request is allowed (RPM check)."""
        return self._get_rpm_bucket(tenant_id).try_consume(1)

    def check_tokens(self, tenant_id: str, tokens: int) -> bool:
        """Check if token usage is allowed (TPM check)."""
        return self._get_tpm_bucket(tenant_id).try_consume(tokens)

    def remaining_rpm(self, tenant_id: str) -> int:
        return self._get_rpm_bucket(tenant_id).remaining

    def remaining_tpm(self, tenant_id: str) -> int:
        return self._get_tpm_bucket(tenant_id).remaining
