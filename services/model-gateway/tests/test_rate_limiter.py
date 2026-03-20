"""Tests for the token bucket rate limiter."""

from __future__ import annotations

from model_gateway.rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket:
    def test_initial_capacity(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.remaining == 10

    def test_consume_reduces_tokens(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.try_consume(3) is True
        assert bucket.remaining == 7

    def test_consume_fails_when_empty(self):
        bucket = TokenBucket(capacity=2, refill_rate=0.0)
        assert bucket.try_consume(1) is True
        assert bucket.try_consume(1) is True
        assert bucket.try_consume(1) is False

    def test_refill_over_time(self):
        bucket = TokenBucket(capacity=10, refill_rate=10.0)
        bucket.try_consume(10)  # drain
        assert bucket.remaining == 0

        # Simulate 0.5 seconds passing
        bucket.last_refill -= 0.5
        assert bucket.remaining == 5

    def test_refill_caps_at_capacity(self):
        bucket = TokenBucket(capacity=10, refill_rate=100.0)
        bucket.last_refill -= 10.0  # way in the past
        assert bucket.remaining == 10


class TestRateLimiter:
    def test_check_request_allows_within_limit(self):
        limiter = RateLimiter(rpm=3, tpm=1000)
        assert limiter.check_request("tenant-a") is True
        assert limiter.check_request("tenant-a") is True
        assert limiter.check_request("tenant-a") is True
        assert limiter.check_request("tenant-a") is False

    def test_tenants_have_independent_limits(self):
        limiter = RateLimiter(rpm=2, tpm=1000)
        assert limiter.check_request("tenant-a") is True
        assert limiter.check_request("tenant-a") is True
        assert limiter.check_request("tenant-a") is False
        # tenant-b still has full quota
        assert limiter.check_request("tenant-b") is True

    def test_check_tokens(self):
        limiter = RateLimiter(rpm=100, tpm=100)
        assert limiter.check_tokens("t1", 50) is True
        assert limiter.check_tokens("t1", 50) is True
        assert limiter.check_tokens("t1", 1) is False

    def test_remaining_rpm(self):
        limiter = RateLimiter(rpm=10, tpm=1000)
        limiter.check_request("t1")
        assert limiter.remaining_rpm("t1") == 9

    def test_remaining_tpm(self):
        limiter = RateLimiter(rpm=100, tpm=500)
        limiter.check_tokens("t1", 200)
        assert limiter.remaining_tpm("t1") == 300
