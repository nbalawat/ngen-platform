"""Workflow Engine — orchestrates multi-agent workflows from WorkflowCRD definitions."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ngen_framework_core.crd import WorkflowCRD
from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
)

from workflow_engine.errors import (
    HumanApprovalRequired,
    HumanApprovalTimeout,
    WorkflowNotFoundError,
)
from workflow_engine.governance import GovernanceGuard
from workflow_engine.models import WorkflowRunStatus
from workflow_engine.resilience import (
    CircuitBreakerRegistry,
    ResilienceConfig,
)
from workflow_engine.state import WorkflowState
from workflow_engine.topology import get_topology_executor

logger = logging.getLogger(__name__)


@dataclass
class WorkflowRun:
    """Internal state of a single workflow execution."""

    run_id: str
    workflow: WorkflowCRD
    status: WorkflowRunStatus
    state: WorkflowState
    events: list[AgentEvent] = field(default_factory=list)
    approval_event: asyncio.Event | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None


class WorkflowEngine:
    """Orchestrates workflow execution using AgentExecutor and topology executors."""

    def __init__(
        self,
        executor: AgentExecutor,
        max_concurrent: int = 50,
        human_approval_timeout: int = 3600,
        default_framework: str = "default",
        governance_guard: GovernanceGuard | None = None,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
    ) -> None:
        self._executor = executor
        self._max_concurrent = max_concurrent
        self._human_approval_timeout = human_approval_timeout
        self._default_framework = default_framework
        self._governance = governance_guard
        self._circuit_registry = circuit_breaker_registry
        self._runs: dict[str, WorkflowRun] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run_workflow(
        self,
        workflow: WorkflowCRD,
        input_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a workflow and yield all agent events.

        Creates agents from the workflow spec, selects the appropriate
        topology executor, runs the workflow, and handles HITL gates.
        """
        run_id = str(uuid.uuid4())
        wf_state = WorkflowState(input_data)

        run = WorkflowRun(
            run_id=run_id,
            workflow=workflow,
            status=WorkflowRunStatus.PENDING,
            state=wf_state,
        )
        self._runs[run_id] = run

        async with self._semaphore:
            try:
                run.status = WorkflowRunStatus.RUNNING
                run.updated_at = time.time()

                # Set governance namespace from workflow metadata
                if self._governance:
                    ns = workflow.metadata.namespace or "default"
                    self._governance.set_namespace(ns)
                    self._governance.reset()

                # Create agents from workflow spec
                agent_names = await self._create_agents(workflow)

                # Get topology executor
                topo_executor = get_topology_executor(workflow.spec.topology)

                # Build initial input
                agent_input = AgentInput(
                    messages=[{"role": "user", "content": str(input_data or {})}],
                    context=input_data or {},
                    session_id=session_id,
                )

                # Pre-execution governance check on input
                if self._governance:
                    for agent_name in agent_names:
                        guard_events = await self._governance.check_input(
                            agent_name, agent_input
                        )
                        for ge in guard_events:
                            run.events.append(ge)
                            yield ge

                    if self._governance.is_blocked():
                        run.status = WorkflowRunStatus.FAILED
                        run.error = "Blocked by governance policy"
                        run.updated_at = time.time()
                        yield AgentEvent(
                            type=AgentEventType.ERROR,
                            data={"error": "Workflow blocked by governance policy"},
                        )
                        return

                # Check for HITL gate
                hitl = workflow.spec.human_in_the_loop
                approval_gate = hitl.approval_gate if hitl else None

                # Build per-agent resilience configs from CRD metadata
                agent_resilience = self._build_resilience_configs(workflow)

                # Execute topology
                async for event in topo_executor.execute(
                    agents=agent_names,
                    edges=list(workflow.spec.edges),
                    executor=self._executor,
                    state=wf_state,
                    input_data=agent_input,
                    resilience_configs=agent_resilience,
                    circuit_registry=self._circuit_registry,
                ):
                    run.events.append(event)
                    run.updated_at = time.time()

                    # Post-event governance check on tool calls
                    if (
                        self._governance
                        and event.type == AgentEventType.TOOL_CALL_START
                        and "tool" in event.data
                    ):
                        tool_events = await self._governance.check_tool(
                            event.agent_name or "", event.data["tool"]
                        )
                        for te in tool_events:
                            run.events.append(te)
                            yield te

                    # Post-event governance check on agent output
                    if (
                        self._governance
                        and event.type == AgentEventType.TEXT_DELTA
                        and event.data.get("text")
                    ):
                        output_events = await self._governance.check_output(
                            event.agent_name or "",
                            event.data["text"],
                        )
                        for oe in output_events:
                            run.events.append(oe)
                            yield oe

                    yield event

                    # Check if we need to pause for HITL approval
                    if (
                        approval_gate
                        and event.type == AgentEventType.DONE
                        and event.agent_name == approval_gate
                    ):
                        async for approval_event in self._wait_for_approval(
                            run, approval_gate
                        ):
                            yield approval_event

                run.status = WorkflowRunStatus.COMPLETED
                run.result = wf_state.to_dict()
                run.updated_at = time.time()

            except HumanApprovalTimeout as exc:
                run.status = WorkflowRunStatus.FAILED
                run.error = str(exc)
                run.updated_at = time.time()
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": str(exc)},
                )

            except Exception as exc:
                run.status = WorkflowRunStatus.FAILED
                run.error = str(exc)
                run.updated_at = time.time()
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": str(exc)},
                )

            finally:
                # Only tear down agents created for this workflow run,
                # not standalone agents registered via /agents endpoint
                for name in agent_names:
                    try:
                        await self._executor.teardown(name)
                    except Exception:
                        pass  # Agent may already be gone

    async def _create_agents(self, workflow: WorkflowCRD) -> list[str]:
        """Create all agents declared in the workflow spec."""
        agent_names: list[str] = []
        for agent_ref in workflow.spec.agents:
            spec = AgentSpec(
                name=agent_ref.ref,
                description=f"Agent '{agent_ref.ref}' in workflow '{workflow.metadata.name}'",
                framework=self._default_framework,
                model=ModelRef(name="default"),
                system_prompt="You are a helpful agent.",
                metadata=agent_ref.config,
            )
            await self._executor.create(spec)
            agent_names.append(agent_ref.ref)
        return agent_names

    async def _wait_for_approval(
        self, run: WorkflowRun, gate: str
    ) -> AsyncIterator[AgentEvent]:
        """Pause execution and wait for human approval."""
        run.status = WorkflowRunStatus.WAITING_APPROVAL
        run.approval_event = asyncio.Event()
        run.updated_at = time.time()

        yield AgentEvent(
            type=AgentEventType.ESCALATION,
            data={
                "run_id": run.run_id,
                "gate": gate,
                "message": f"Waiting for approval at gate '{gate}'",
            },
        )

        try:
            await asyncio.wait_for(
                run.approval_event.wait(),
                timeout=self._human_approval_timeout,
            )
            run.status = WorkflowRunStatus.RUNNING
            run.updated_at = time.time()
        except asyncio.TimeoutError:
            raise HumanApprovalTimeout(
                run.run_id, gate, self._human_approval_timeout
            )

    def approve_run(self, run_id: str) -> bool:
        """Approve a workflow run that is waiting for human approval.

        Returns True if the run was waiting and is now approved.
        """
        run = self._runs.get(run_id)
        if not run or run.status != WorkflowRunStatus.WAITING_APPROVAL:
            return False
        if run.approval_event:
            run.approval_event.set()
            return True
        return False

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running workflow.

        Returns True if the run was cancelled.
        """
        run = self._runs.get(run_id)
        if not run:
            return False
        if run.status in (WorkflowRunStatus.RUNNING, WorkflowRunStatus.WAITING_APPROVAL):
            run.status = WorkflowRunStatus.CANCELLED
            run.updated_at = time.time()
            if run.approval_event:
                run.approval_event.set()  # Unblock the waiter
            return True
        return False

    def get_run(self, run_id: str) -> WorkflowRun:
        """Get a workflow run by ID.

        Raises:
            WorkflowNotFoundError: If the run doesn't exist.
        """
        run = self._runs.get(run_id)
        if not run:
            raise WorkflowNotFoundError(run_id)
        return run

    def list_runs(
        self, status: WorkflowRunStatus | None = None
    ) -> list[WorkflowRun]:
        """List all workflow runs, optionally filtered by status."""
        runs = list(self._runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        return runs

    def _build_resilience_configs(
        self, workflow: WorkflowCRD
    ) -> dict[str, ResilienceConfig]:
        """Build per-agent ResilienceConfig from workflow CRD agent metadata."""
        configs: dict[str, ResilienceConfig] = {}
        for agent_ref in workflow.spec.agents:
            configs[agent_ref.ref] = ResilienceConfig.from_metadata(agent_ref.config)
        return configs
