"""Domain models for the MCP Manager service.

The MCP Manager tracks MCP server registrations and their exposed tools.
Each server has a transport type, endpoint, authentication config, and a
catalog of tools it provides. Tools are discoverable by name and by
capability tags, enabling agents to find relevant tools at runtime.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TransportType(StrEnum):
    """MCP transport protocols."""

    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    STDIO = "stdio"
    BUILTIN = "builtin"


class AuthType(StrEnum):
    """Authentication types for MCP servers."""

    NONE = "none"
    API_KEY = "api-key"
    OAUTH2 = "oauth2"


class ServerStatus(StrEnum):
    """Lifecycle status of an MCP server."""

    REGISTERED = "registered"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


# ---------------------------------------------------------------------------
# Tool models
# ---------------------------------------------------------------------------


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = False


class ToolDefinition(BaseModel):
    """A tool exposed by an MCP server."""

    name: str = Field(..., min_length=1)
    description: str = ""
    parameters: list[ToolParameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ToolEntry(BaseModel):
    """A tool registered in the catalog, linked to its server."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    server_id: str
    server_name: str
    name: str
    description: str = ""
    parameters: list[ToolParameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Server models
# ---------------------------------------------------------------------------


class AuthConfig(BaseModel):
    """Authentication configuration for an MCP server."""

    type: AuthType = AuthType.NONE
    secret_ref: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ServerCreate(BaseModel):
    """Request body for registering an MCP server."""

    name: str = Field(..., min_length=3, max_length=100)
    description: str = ""
    namespace: str = Field(default="default", min_length=1)
    endpoint: str = Field(..., min_length=1)
    transport: TransportType = TransportType.STREAMABLE_HTTP
    auth: AuthConfig = Field(default_factory=AuthConfig)
    tools: list[ToolDefinition] = Field(default_factory=list)
    health_check_path: str = "/health"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Server(BaseModel):
    """A registered MCP server."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    namespace: str = "default"
    endpoint: str
    transport: TransportType = TransportType.STREAMABLE_HTTP
    auth: AuthConfig = Field(default_factory=AuthConfig)
    tools: list[ToolDefinition] = Field(default_factory=list)
    health_check_path: str = "/health"
    status: ServerStatus = ServerStatus.REGISTERED
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServerUpdate(BaseModel):
    """Request body for updating an MCP server."""

    description: str | None = None
    endpoint: str | None = None
    transport: TransportType | None = None
    auth: AuthConfig | None = None
    tools: list[ToolDefinition] | None = None
    health_check_path: str | None = None
    status: ServerStatus | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tool invocation
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """Request to invoke a tool on an MCP server."""

    server_name: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    namespace: str = "default"


class ToolCallResponse(BaseModel):
    """Response from a tool invocation."""

    server_name: str
    tool_name: str
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None
