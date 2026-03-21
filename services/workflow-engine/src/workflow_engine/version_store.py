"""Version store for workflow definitions and agent configurations.

Provides in-memory storage for versioned workflow YAML definitions and
agent configurations. Each save creates a new version (auto-incrementing).
Supports listing versions, loading a specific version, and comparing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowVersion:
    """A single versioned workflow definition."""

    workflow_name: str
    version: int
    yaml_content: str
    input_data: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentVersion:
    """A single versioned agent configuration."""

    agent_name: str
    version: int
    system_prompt: str = ""
    framework: str = "default"
    model: str = "default"
    description: str = ""
    tools: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class VersionStore:
    """In-memory version store for workflows and agents."""

    def __init__(self) -> None:
        # {workflow_name: [WorkflowVersion, ...]}
        self._workflows: dict[str, list[WorkflowVersion]] = {}
        # {agent_name: [AgentVersion, ...]}
        self._agents: dict[str, list[AgentVersion]] = {}

    # -----------------------------------------------------------------------
    # Workflow versions
    # -----------------------------------------------------------------------

    def save_workflow(
        self,
        name: str,
        yaml_content: str,
        input_data: dict[str, Any] | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowVersion:
        """Save a new version of a workflow definition."""
        versions = self._workflows.setdefault(name, [])
        version_num = len(versions) + 1
        v = WorkflowVersion(
            workflow_name=name,
            version=version_num,
            yaml_content=yaml_content,
            input_data=input_data or {},
            description=description,
            metadata=metadata or {},
        )
        versions.append(v)
        return v

    def list_workflow_versions(self, name: str) -> list[WorkflowVersion]:
        """List all versions of a workflow, newest first."""
        return list(reversed(self._workflows.get(name, [])))

    def get_workflow_version(
        self, name: str, version: int | None = None
    ) -> WorkflowVersion | None:
        """Get a specific version, or latest if version is None."""
        versions = self._workflows.get(name, [])
        if not versions:
            return None
        if version is None:
            return versions[-1]
        for v in versions:
            if v.version == version:
                return v
        return None

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all workflows with their latest version info."""
        result = []
        for name, versions in self._workflows.items():
            latest = versions[-1]
            result.append({
                "name": name,
                "version_count": len(versions),
                "latest_version": latest.version,
                "description": latest.description,
                "created_at": versions[0].created_at,
                "updated_at": latest.created_at,
            })
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)

    # -----------------------------------------------------------------------
    # Agent versions
    # -----------------------------------------------------------------------

    def save_agent(
        self,
        name: str,
        system_prompt: str = "",
        framework: str = "default",
        model: str = "default",
        description: str = "",
        tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentVersion:
        """Save a new version of an agent configuration."""
        versions = self._agents.setdefault(name, [])
        version_num = len(versions) + 1
        v = AgentVersion(
            agent_name=name,
            version=version_num,
            system_prompt=system_prompt,
            framework=framework,
            model=model,
            description=description,
            tools=tools or [],
            metadata=metadata or {},
        )
        versions.append(v)
        return v

    def list_agent_versions(self, name: str) -> list[AgentVersion]:
        """List all versions of an agent, newest first."""
        return list(reversed(self._agents.get(name, [])))

    def get_agent_version(
        self, name: str, version: int | None = None
    ) -> AgentVersion | None:
        """Get a specific version, or latest if version is None."""
        versions = self._agents.get(name, [])
        if not versions:
            return None
        if version is None:
            return versions[-1]
        for v in versions:
            if v.version == version:
                return v
        return None

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents with their latest version info."""
        result = []
        for name, versions in self._agents.items():
            latest = versions[-1]
            result.append({
                "name": name,
                "version_count": len(versions),
                "latest_version": latest.version,
                "description": latest.description,
                "created_at": versions[0].created_at,
                "updated_at": latest.created_at,
            })
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)
