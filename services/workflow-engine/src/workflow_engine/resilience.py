"""Resilience patterns for workflow agent execution.

Provides three composable patterns:
- RetryPolicy: Exponential backoff with jitter for transient failures
- TimeoutPolicy: Per-agent execution timeout
- CircuitBreaker: Fail-fast when an agent repeatedly fails

These are configured per-agent via workflow CRD metadata and applied
by the topology executors during agent execution.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff retry configuration.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier applied to delay after each attempt.
        jitter: If True, add random jitter to prevent thundering herd.
        retryable_errors: If set, only retry on these exception types.
            If empty, retry on all exceptions.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_errors: tuple[type[Exception], ...] = ()

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay for the given attempt number (0-indexed)."""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay

    def is_retryable(self, error: Exception) -> bool:
        """Check if the error should trigger a retry."""
        if not self.retryable_errors:
            return True
        return isinstance(error, self.retryable_errors)


# Default: no retries
NO_RETRY = RetryPolicy(max_retries=0)


# ---------------------------------------------------------------------------
# Timeout Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeoutPolicy:
    """Per-agent execution timeout.

    Attributes:
        timeout_seconds: Maximum seconds for a single agent execution.
            None means no timeout.
    """

    timeout_seconds: float | None = None


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast, rejecting calls
    HALF_OPEN = "half_open"  # Allowing a probe request


@dataclass
class CircuitBreaker:
    """Circuit breaker for an individual agent.

    When an agent fails repeatedly, the circuit opens and immediately
    rejects further calls. After a cooldown period, a single probe
    request is allowed through. If it succeeds, the circuit closes;
    if it fails, the circuit reopens.

    Attributes:
        failure_threshold: Number of consecutive failures to open circuit.
        recovery_timeout: Seconds to wait before allowing a probe.
        half_open_max_calls: Number of probe calls allowed in half-open state.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """Current circuit state, accounting for recovery timeout."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful execution."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._reset()
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed execution."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._success_count = 0
        self._half_open_calls = 0

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker opened after %d consecutive failures",
                self._failure_count,
            )

    def on_half_open_call(self) -> None:
        """Track a probe call in half-open state."""
        self._half_open_calls += 1

    def _reset(self) -> None:
        """Reset to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        logger.info("Circuit breaker reset to CLOSED")

    def reset(self) -> None:
        """Public reset — for testing and manual recovery."""
        self._reset()


# ---------------------------------------------------------------------------
# Circuit Breaker Registry (per-agent tracking)
# ---------------------------------------------------------------------------


class CircuitBreakerRegistry:
    """Tracks circuit breakers per agent name.

    Thread-safe for async code (single-threaded event loop).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, agent_name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an agent."""
        if agent_name not in self._breakers:
            self._breakers[agent_name] = CircuitBreaker(
                failure_threshold=self._failure_threshold,
                recovery_timeout=self._recovery_timeout,
            )
        return self._breakers[agent_name]

    def reset(self, agent_name: str | None = None) -> None:
        """Reset one or all circuit breakers."""
        if agent_name:
            if agent_name in self._breakers:
                self._breakers[agent_name].reset()
        else:
            self._breakers.clear()


# ---------------------------------------------------------------------------
# Resilience Configuration (per-agent, from CRD metadata)
# ---------------------------------------------------------------------------


@dataclass
class ResilienceConfig:
    """Combined resilience configuration for an agent execution.

    Constructed from agent metadata in the WorkflowCRD.
    """

    retry: RetryPolicy = field(default_factory=lambda: NO_RETRY)
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    circuit_breaker_enabled: bool = False

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> ResilienceConfig:
        """Parse resilience config from agent ref metadata.

        Example metadata:
            {
                "resilience": {
                    "retry": {"max_retries": 3, "base_delay": 1.0},
                    "timeout_seconds": 30,
                    "circuit_breaker": true
                }
            }
        """
        if not metadata:
            return cls()

        resilience = metadata.get("resilience")
        if not resilience:
            return cls()

        # Parse retry
        retry_data = resilience.get("retry", {})
        retry = RetryPolicy(
            max_retries=retry_data.get("max_retries", 0),
            base_delay=retry_data.get("base_delay", 1.0),
            max_delay=retry_data.get("max_delay", 60.0),
            backoff_factor=retry_data.get("backoff_factor", 2.0),
            jitter=retry_data.get("jitter", True),
        )

        # Parse timeout
        timeout_seconds = resilience.get("timeout_seconds")
        timeout = TimeoutPolicy(timeout_seconds=timeout_seconds)

        # Parse circuit breaker
        cb_enabled = resilience.get("circuit_breaker", False)

        return cls(retry=retry, timeout=timeout, circuit_breaker_enabled=cb_enabled)


# ---------------------------------------------------------------------------
# Resilience errors
# ---------------------------------------------------------------------------


class AgentTimeoutError(Exception):
    """Raised when an agent exceeds its execution timeout."""

    def __init__(self, agent_name: str, timeout: float) -> None:
        self.agent_name = agent_name
        self.timeout = timeout
        super().__init__(
            f"Agent '{agent_name}' timed out after {timeout}s"
        )


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting calls."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__(
            f"Circuit breaker open for agent '{agent_name}', rejecting execution"
        )


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(
        self, agent_name: str, attempts: int, last_error: Exception
    ) -> None:
        self.agent_name = agent_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Agent '{agent_name}' failed after {attempts} attempts: {last_error}"
        )


# ---------------------------------------------------------------------------
# Resilient executor wrapper
# ---------------------------------------------------------------------------


async def execute_with_resilience(
    agent_name: str,
    execute_fn,
    resilience: ResilienceConfig,
    circuit_registry: CircuitBreakerRegistry | None = None,
) -> list[Any]:
    """Execute an agent function with retry, timeout, and circuit breaker.

    Args:
        agent_name: Name of the agent being executed.
        execute_fn: Async callable that returns an async iterator of events.
        resilience: Resilience configuration.
        circuit_registry: Optional circuit breaker registry.

    Returns:
        List of collected events from the successful execution.

    Raises:
        CircuitOpenError: If circuit breaker is open.
        RetryExhaustedError: If all retries are exhausted.
        AgentTimeoutError: If execution exceeds timeout.
    """
    # Check circuit breaker first
    breaker = None
    if resilience.circuit_breaker_enabled and circuit_registry:
        breaker = circuit_registry.get(agent_name)
        if not breaker.allow_request():
            raise CircuitOpenError(agent_name)
        if breaker.state == CircuitState.HALF_OPEN:
            breaker.on_half_open_call()

    last_error: Exception | None = None
    max_attempts = resilience.retry.max_retries + 1

    for attempt in range(max_attempts):
        try:
            events = await _execute_with_timeout(
                agent_name, execute_fn, resilience.timeout
            )
            # Success
            if breaker:
                breaker.record_success()
            return events

        except Exception as exc:
            last_error = exc
            logger.warning(
                "Agent '%s' attempt %d/%d failed: %s",
                agent_name,
                attempt + 1,
                max_attempts,
                exc,
            )

            if breaker:
                breaker.record_failure()

            # Check if we should retry
            if attempt < resilience.retry.max_retries:
                if resilience.retry.is_retryable(exc):
                    delay = resilience.retry.compute_delay(attempt)
                    logger.info(
                        "Retrying agent '%s' in %.2fs (attempt %d/%d)",
                        agent_name,
                        delay,
                        attempt + 2,
                        max_attempts,
                    )
                    await asyncio.sleep(delay)
                    continue

            # Not retryable or last attempt
            break

    assert last_error is not None
    raise RetryExhaustedError(agent_name, max_attempts, last_error)


async def _execute_with_timeout(
    agent_name: str,
    execute_fn,
    timeout: TimeoutPolicy,
) -> list[Any]:
    """Execute with optional timeout, collecting all events."""

    async def _collect():
        events = []
        async for event in execute_fn():
            events.append(event)
        return events

    if timeout.timeout_seconds is not None:
        try:
            return await asyncio.wait_for(
                _collect(), timeout=timeout.timeout_seconds
            )
        except asyncio.TimeoutError:
            raise AgentTimeoutError(agent_name, timeout.timeout_seconds)
    else:
        return await _collect()
