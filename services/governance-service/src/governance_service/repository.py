"""In-memory policy repository.

Thread-safe storage for governance policies with namespace-scoped queries.
"""

from __future__ import annotations

from datetime import datetime, timezone

from governance_service.models import Policy, PolicyCreate, PolicyUpdate


class PolicyRepository:
    """In-memory policy store with namespace isolation."""

    def __init__(self) -> None:
        self._policies: dict[str, Policy] = {}

    def create(self, data: PolicyCreate) -> Policy:
        policy = Policy(
            name=data.name,
            description=data.description,
            policy_type=data.policy_type,
            namespace=data.namespace,
            action=data.action,
            severity=data.severity,
            rules=data.rules,
            enabled=data.enabled,
        )
        self._policies[policy.id] = policy
        return policy

    def get(self, policy_id: str) -> Policy | None:
        return self._policies.get(policy_id)

    def get_by_name(self, name: str, namespace: str = "default") -> Policy | None:
        for p in self._policies.values():
            if p.name == name and p.namespace == namespace:
                return p
        return None

    def list(
        self,
        namespace: str | None = None,
        policy_type: str | None = None,
        enabled_only: bool = False,
    ) -> list[Policy]:
        result = list(self._policies.values())
        if namespace is not None:
            result = [p for p in result if p.namespace == namespace]
        if policy_type is not None:
            result = [p for p in result if p.policy_type == policy_type]
        if enabled_only:
            result = [p for p in result if p.enabled]
        return result

    def update(self, policy_id: str, data: PolicyUpdate) -> Policy | None:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = policy.model_copy(update=updates)
        self._policies[policy_id] = updated
        return updated

    def delete(self, policy_id: str) -> bool:
        return self._policies.pop(policy_id, None) is not None
