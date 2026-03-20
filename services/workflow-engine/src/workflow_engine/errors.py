"""Domain exceptions for the Workflow Engine."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base exception for all workflow-engine errors."""


class WorkflowNotFoundError(WorkflowError):
    """Raised when a workflow run ID is not found."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Workflow run '{run_id}' not found")


class AgentNotFoundError(WorkflowError):
    """Raised when a referenced agent cannot be resolved."""

    def __init__(self, agent_ref: str) -> None:
        self.agent_ref = agent_ref
        super().__init__(f"Agent '{agent_ref}' not found")


class TopologyError(WorkflowError):
    """Raised for invalid topology configurations."""


class ConditionEvalError(WorkflowError):
    """Raised when an edge condition cannot be safely evaluated."""

    def __init__(self, condition: str, reason: str) -> None:
        self.condition = condition
        self.reason = reason
        super().__init__(f"Cannot evaluate condition '{condition}': {reason}")


class HumanApprovalRequired(WorkflowError):
    """Raised when a workflow is paused waiting for human approval."""

    def __init__(self, run_id: str, gate: str) -> None:
        self.run_id = run_id
        self.gate = gate
        super().__init__(f"Workflow run '{run_id}' waiting for approval at gate '{gate}'")


class HumanApprovalTimeout(WorkflowError):
    """Raised when a human approval times out."""

    def __init__(self, run_id: str, gate: str, timeout: int) -> None:
        self.run_id = run_id
        self.gate = gate
        self.timeout = timeout
        super().__init__(
            f"Approval for run '{run_id}' at gate '{gate}' timed out after {timeout}s"
        )
