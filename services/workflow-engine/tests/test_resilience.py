"""Tests for workflow resilience — retry, timeout, and circuit breaker patterns.

Uses real implementations: InMemoryAdapter, real asyncio, real timers.
No mocks, no unittest.mock.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
)

from workflow_engine.resilience import (
    AgentTimeoutError,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    ResilienceConfig,
    RetryExhaustedError,
    RetryPolicy,
    TimeoutPolicy,
    execute_with_resilience,
)


# ---------------------------------------------------------------------------
# RetryPolicy unit tests
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    """Tests for RetryPolicy configuration and delay computation."""

    def test_default_no_retry(self):
        policy = RetryPolicy(max_retries=0)
        assert policy.max_retries == 0

    def test_compute_delay_exponential(self):
        policy = RetryPolicy(base_delay=1.0, backoff_factor=2.0, jitter=False)
        assert policy.compute_delay(0) == 1.0
        assert policy.compute_delay(1) == 2.0
        assert policy.compute_delay(2) == 4.0
        assert policy.compute_delay(3) == 8.0

    def test_compute_delay_max_cap(self):
        policy = RetryPolicy(base_delay=10.0, backoff_factor=3.0, max_delay=30.0, jitter=False)
        assert policy.compute_delay(0) == 10.0
        assert policy.compute_delay(1) == 30.0  # 30 capped
        assert policy.compute_delay(2) == 30.0  # 90 -> capped to 30

    def test_compute_delay_with_jitter(self):
        policy = RetryPolicy(base_delay=10.0, backoff_factor=1.0, jitter=True)
        delays = [policy.compute_delay(0) for _ in range(100)]
        # With jitter, delays should be between 5.0 and 10.0 (0.5x to 1.0x)
        assert all(5.0 <= d <= 10.0 for d in delays)
        # Should not all be the same
        assert len(set(round(d, 3) for d in delays)) > 1

    def test_is_retryable_all_errors(self):
        policy = RetryPolicy()  # no retryable_errors = retry all
        assert policy.is_retryable(ValueError("test"))
        assert policy.is_retryable(RuntimeError("test"))

    def test_is_retryable_specific_errors(self):
        policy = RetryPolicy(retryable_errors=(ValueError, ConnectionError))
        assert policy.is_retryable(ValueError("test"))
        assert policy.is_retryable(ConnectionError("test"))
        assert not policy.is_retryable(RuntimeError("test"))


# ---------------------------------------------------------------------------
# CircuitBreaker unit tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Tests for circuit breaker state machine."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Reset
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Only 2 consecutive

    def test_transitions_to_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request()

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.06)

        assert cb.state == CircuitState.HALF_OPEN
        cb.on_half_open_call()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.06)

        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_max_calls(self):
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=0.05, half_open_max_calls=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.06)

        assert cb.allow_request()
        cb.on_half_open_call()
        assert not cb.allow_request()  # Only 1 probe allowed

    def test_manual_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()


# ---------------------------------------------------------------------------
# CircuitBreakerRegistry tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerRegistry:
    """Tests for per-agent circuit breaker registry."""

    def test_get_creates_breaker(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get("agent-a")
        assert cb.state == CircuitState.CLOSED

    def test_get_returns_same_instance(self):
        registry = CircuitBreakerRegistry()
        cb1 = registry.get("agent-a")
        cb2 = registry.get("agent-a")
        assert cb1 is cb2

    def test_separate_breakers_per_agent(self):
        registry = CircuitBreakerRegistry(failure_threshold=2)
        cb_a = registry.get("agent-a")
        cb_b = registry.get("agent-b")
        cb_a.record_failure()
        cb_a.record_failure()
        assert cb_a.state == CircuitState.OPEN
        assert cb_b.state == CircuitState.CLOSED

    def test_reset_single_agent(self):
        registry = CircuitBreakerRegistry(failure_threshold=2)
        cb = registry.get("agent-a")
        cb.record_failure()
        cb.record_failure()
        registry.reset("agent-a")
        assert cb.state == CircuitState.CLOSED

    def test_reset_all(self):
        registry = CircuitBreakerRegistry(failure_threshold=2)
        for name in ["a", "b", "c"]:
            cb = registry.get(name)
            cb.record_failure()
            cb.record_failure()
        registry.reset()
        # All cleared — new breakers will be created
        assert registry.get("a").state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# ResilienceConfig parsing tests
# ---------------------------------------------------------------------------


class TestResilienceConfig:
    """Tests for ResilienceConfig.from_metadata parsing."""

    def test_empty_metadata(self):
        config = ResilienceConfig.from_metadata(None)
        assert config.retry.max_retries == 0
        assert config.timeout.timeout_seconds is None
        assert config.circuit_breaker_enabled is False

    def test_no_resilience_key(self):
        config = ResilienceConfig.from_metadata({"other": "value"})
        assert config.retry.max_retries == 0

    def test_full_config(self):
        config = ResilienceConfig.from_metadata(
            {
                "resilience": {
                    "retry": {
                        "max_retries": 5,
                        "base_delay": 0.5,
                        "max_delay": 30.0,
                        "backoff_factor": 3.0,
                    },
                    "timeout_seconds": 60,
                    "circuit_breaker": True,
                }
            }
        )
        assert config.retry.max_retries == 5
        assert config.retry.base_delay == 0.5
        assert config.retry.max_delay == 30.0
        assert config.retry.backoff_factor == 3.0
        assert config.timeout.timeout_seconds == 60
        assert config.circuit_breaker_enabled is True

    def test_partial_retry_config(self):
        config = ResilienceConfig.from_metadata(
            {"resilience": {"retry": {"max_retries": 2}}}
        )
        assert config.retry.max_retries == 2
        assert config.retry.base_delay == 1.0  # default
        assert config.retry.backoff_factor == 2.0  # default

    def test_timeout_only(self):
        config = ResilienceConfig.from_metadata(
            {"resilience": {"timeout_seconds": 10}}
        )
        assert config.retry.max_retries == 0
        assert config.timeout.timeout_seconds == 10


# ---------------------------------------------------------------------------
# execute_with_resilience integration tests
# ---------------------------------------------------------------------------


# Helper: an async generator that yields events
class FakeExecutor:
    """Test executor that can simulate failures and delays."""

    def __init__(self):
        self.call_count = 0
        self._fail_until = 0
        self._delay = 0.0
        self._error_type: type[Exception] = RuntimeError

    def fail_first_n(self, n: int, error_type: type[Exception] = RuntimeError):
        self._fail_until = n
        self._error_type = error_type
        return self

    def with_delay(self, delay: float):
        self._delay = delay
        return self

    async def execute(self):
        """Async generator that yields events."""
        self.call_count += 1
        if self.call_count <= self._fail_until:
            raise self._error_type(f"Failure #{self.call_count}")
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": "Hello"},
            agent_name="test-agent",
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name="test-agent",
        )


class TestExecuteWithResilience:
    """Integration tests for the resilient execution wrapper."""

    async def test_success_no_retry(self):
        fake = FakeExecutor()
        config = ResilienceConfig(retry=RetryPolicy(max_retries=0))
        events = await execute_with_resilience(
            "test-agent", fake.execute, config
        )
        assert len(events) == 2
        assert events[0].type == AgentEventType.TEXT_DELTA
        assert fake.call_count == 1

    async def test_retry_on_failure(self):
        fake = FakeExecutor().fail_first_n(2)
        config = ResilienceConfig(
            retry=RetryPolicy(max_retries=3, base_delay=0.01, jitter=False)
        )
        events = await execute_with_resilience(
            "test-agent", fake.execute, config
        )
        assert len(events) == 2
        assert fake.call_count == 3  # Failed 2x, succeeded on 3rd

    async def test_retry_exhausted(self):
        fake = FakeExecutor().fail_first_n(100)
        config = ResilienceConfig(
            retry=RetryPolicy(max_retries=2, base_delay=0.01, jitter=False)
        )
        with pytest.raises(RetryExhaustedError) as exc_info:
            await execute_with_resilience("test-agent", fake.execute, config)
        assert exc_info.value.agent_name == "test-agent"
        assert exc_info.value.attempts == 3
        assert fake.call_count == 3

    async def test_timeout(self):
        fake = FakeExecutor().with_delay(5.0)
        config = ResilienceConfig(timeout=TimeoutPolicy(timeout_seconds=0.05))
        with pytest.raises(RetryExhaustedError) as exc_info:
            await execute_with_resilience("test-agent", fake.execute, config)
        assert isinstance(exc_info.value.last_error, AgentTimeoutError)

    async def test_timeout_success(self):
        fake = FakeExecutor().with_delay(0.01)
        config = ResilienceConfig(timeout=TimeoutPolicy(timeout_seconds=2.0))
        events = await execute_with_resilience(
            "test-agent", fake.execute, config
        )
        assert len(events) == 2

    async def test_circuit_breaker_blocks(self):
        registry = CircuitBreakerRegistry(failure_threshold=2)
        # Manually open the circuit
        cb = registry.get("test-agent")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        fake = FakeExecutor()
        config = ResilienceConfig(circuit_breaker_enabled=True)
        with pytest.raises(CircuitOpenError):
            await execute_with_resilience(
                "test-agent", fake.execute, config, registry
            )
        assert fake.call_count == 0  # Never called

    async def test_circuit_breaker_records_failure(self):
        registry = CircuitBreakerRegistry(failure_threshold=3)
        fake = FakeExecutor().fail_first_n(100)
        config = ResilienceConfig(
            retry=RetryPolicy(max_retries=0),
            circuit_breaker_enabled=True,
        )
        # Call and fail
        with pytest.raises(RetryExhaustedError):
            await execute_with_resilience(
                "test-agent", fake.execute, config, registry
            )
        cb = registry.get("test-agent")
        assert cb._failure_count == 1

    async def test_circuit_breaker_records_success(self):
        registry = CircuitBreakerRegistry(failure_threshold=3)
        fake = FakeExecutor()
        config = ResilienceConfig(circuit_breaker_enabled=True)
        events = await execute_with_resilience(
            "test-agent", fake.execute, config, registry
        )
        assert len(events) == 2
        cb = registry.get("test-agent")
        assert cb._failure_count == 0

    async def test_retry_with_specific_error_type(self):
        """Only retry on specified error types."""
        fake = FakeExecutor().fail_first_n(1, error_type=ConnectionError)
        config = ResilienceConfig(
            retry=RetryPolicy(
                max_retries=3,
                base_delay=0.01,
                jitter=False,
                retryable_errors=(ConnectionError,),
            )
        )
        events = await execute_with_resilience(
            "test-agent", fake.execute, config
        )
        assert len(events) == 2
        assert fake.call_count == 2

    async def test_no_retry_on_non_retryable_error(self):
        fake = FakeExecutor().fail_first_n(1, error_type=ValueError)
        config = ResilienceConfig(
            retry=RetryPolicy(
                max_retries=3,
                base_delay=0.01,
                retryable_errors=(ConnectionError,),
            )
        )
        with pytest.raises(RetryExhaustedError):
            await execute_with_resilience("test-agent", fake.execute, config)
        assert fake.call_count == 1  # No retry for ValueError

    async def test_retry_plus_timeout_combo(self):
        """First attempt times out, second attempt succeeds."""
        call_count = 0

        async def flaky_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(5.0)  # Will timeout
            yield AgentEvent(
                type=AgentEventType.DONE, data={}, agent_name="test"
            )

        config = ResilienceConfig(
            retry=RetryPolicy(max_retries=2, base_delay=0.01, jitter=False),
            timeout=TimeoutPolicy(timeout_seconds=0.05),
        )
        events = await execute_with_resilience(
            "test-agent", flaky_execute, config
        )
        assert len(events) == 1
        assert call_count == 2


# ---------------------------------------------------------------------------
# End-to-end resilience with real workflow engine
# ---------------------------------------------------------------------------


class TestResilienceEndToEnd:
    """End-to-end tests verifying resilience through the workflow engine."""

    async def _make_engine(self, adapter, circuit_registry=None):
        """Build a workflow engine with a custom adapter instance."""
        from ngen_framework_core.executor import AgentExecutor
        from ngen_framework_core.registry import AdapterRegistry

        from workflow_engine.engine import WorkflowEngine

        registry = AdapterRegistry()
        registry.register(adapter)
        executor = AgentExecutor(registry=registry)
        engine = WorkflowEngine(
            executor=executor,
            default_framework=adapter.name,
            circuit_breaker_registry=circuit_registry,
        )
        return engine

    def _make_workflow_yaml(self, agents_config: list[dict]) -> str:
        """Build a sequential workflow YAML with per-agent config."""
        import yaml

        agents = []
        for ac in agents_config:
            agent = {"ref": ac["name"]}
            if "config" in ac:
                agent["config"] = ac["config"]
            agents.append(agent)

        workflow = {
            "apiVersion": "ngen.io/v1",
            "kind": "Workflow",
            "metadata": {"name": "resilience-test"},
            "spec": {
                "agents": agents,
                "topology": "sequential",
            },
        }
        return yaml.dump(workflow)

    async def test_workflow_with_retry_config(self):
        """Verify that retry configs are parsed from CRD metadata."""
        from ngen_framework_core.crd import WorkflowCRD

        yaml_str = self._make_workflow_yaml(
            [
                {
                    "name": "agent-a",
                    "config": {
                        "resilience": {
                            "retry": {"max_retries": 3, "base_delay": 0.1},
                            "timeout_seconds": 30,
                        }
                    },
                }
            ]
        )
        import yaml

        data = yaml.safe_load(yaml_str)
        wf = WorkflowCRD.model_validate(data)

        config = ResilienceConfig.from_metadata(wf.spec.agents[0].config)
        assert config.retry.max_retries == 3
        assert config.timeout.timeout_seconds == 30

    async def test_workflow_without_resilience_runs_normally(self, adapter):
        """Workflows without resilience config still work fine."""
        engine = await self._make_engine(adapter)
        yaml_str = self._make_workflow_yaml([{"name": "agent-a"}])

        import yaml

        from ngen_framework_core.crd import WorkflowCRD

        data = yaml.safe_load(yaml_str)
        wf = WorkflowCRD.model_validate(data)

        events = []
        async for event in engine.run_workflow(wf, {"task": "hello"}):
            events.append(event)

        event_types = [e.type for e in events]
        assert AgentEventType.DONE in event_types

    async def test_circuit_breaker_registry_wired_to_engine(self, adapter):
        """CircuitBreakerRegistry passed to engine is available."""
        registry = CircuitBreakerRegistry(failure_threshold=3)
        engine = await self._make_engine(adapter, circuit_registry=registry)
        assert engine._circuit_registry is registry
