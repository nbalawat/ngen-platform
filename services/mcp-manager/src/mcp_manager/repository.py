"""In-memory repository for MCP server registrations and tool catalog.

Provides server CRUD, tool catalog queries, and namespace-scoped lookups.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp_manager.models import (
    Server,
    ServerCreate,
    ServerUpdate,
    ToolDefinition,
    ToolEntry,
)


class MCPRepository:
    """In-memory MCP server and tool registry."""

    def __init__(self) -> None:
        self._servers: dict[str, Server] = {}
        self._tools: dict[str, ToolEntry] = {}

    # -----------------------------------------------------------------------
    # Server CRUD
    # -----------------------------------------------------------------------

    def create_server(self, data: ServerCreate) -> Server:
        server = Server(
            name=data.name,
            description=data.description,
            namespace=data.namespace,
            endpoint=data.endpoint,
            transport=data.transport,
            auth=data.auth,
            tools=data.tools,
            health_check_path=data.health_check_path,
            metadata=data.metadata,
        )
        self._servers[server.id] = server

        # Index tools in the catalog
        for tool_def in data.tools:
            entry = ToolEntry(
                server_id=server.id,
                server_name=server.name,
                name=tool_def.name,
                description=tool_def.description,
                parameters=tool_def.parameters,
                tags=tool_def.tags,
            )
            self._tools[entry.id] = entry

        return server

    def get_server(self, server_id: str) -> Server | None:
        return self._servers.get(server_id)

    def get_server_by_name(
        self, name: str, namespace: str = "default"
    ) -> Server | None:
        for s in self._servers.values():
            if s.name == name and s.namespace == namespace:
                return s
        return None

    def list_servers(
        self,
        namespace: str | None = None,
        status: str | None = None,
    ) -> list[Server]:
        result = list(self._servers.values())
        if namespace is not None:
            result = [s for s in result if s.namespace == namespace]
        if status is not None:
            result = [s for s in result if s.status == status]
        return result

    def update_server(
        self, server_id: str, data: ServerUpdate
    ) -> Server | None:
        server = self._servers.get(server_id)
        if server is None:
            return None

        updates = data.model_dump(exclude_unset=True)
        updates["updated_at"] = datetime.now(timezone.utc)

        # If tools are being updated, rebuild the catalog entries
        if "tools" in updates:
            self._remove_server_tools(server_id)
            raw_tools = updates["tools"]
            parsed_tools = [
                ToolDefinition(**t) if isinstance(t, dict) else t
                for t in raw_tools
            ]
            updates["tools"] = parsed_tools
            for tool_def in parsed_tools:
                entry = ToolEntry(
                    server_id=server_id,
                    server_name=server.name,
                    name=tool_def.name,
                    description=tool_def.description,
                    parameters=tool_def.parameters,
                    tags=tool_def.tags,
                )
                self._tools[entry.id] = entry

        updated = server.model_copy(update=updates)
        self._servers[server_id] = updated
        return updated

    def delete_server(self, server_id: str) -> bool:
        if server_id not in self._servers:
            return False
        self._remove_server_tools(server_id)
        del self._servers[server_id]
        return True

    # -----------------------------------------------------------------------
    # Tool catalog
    # -----------------------------------------------------------------------

    def list_tools(
        self,
        server_name: str | None = None,
        tag: str | None = None,
    ) -> list[ToolEntry]:
        result = list(self._tools.values())
        if server_name is not None:
            result = [t for t in result if t.server_name == server_name]
        if tag is not None:
            result = [t for t in result if tag in t.tags]
        return result

    def get_tool(self, tool_id: str) -> ToolEntry | None:
        return self._tools.get(tool_id)

    def find_tool(
        self, server_name: str, tool_name: str
    ) -> ToolEntry | None:
        for t in self._tools.values():
            if t.server_name == server_name and t.name == tool_name:
                return t
        return None

    def search_tools(self, query: str) -> list[ToolEntry]:
        """Simple keyword search across tool names, descriptions, and tags."""
        query_lower = query.lower()
        results = []
        for t in self._tools.values():
            if (
                query_lower in t.name.lower()
                or query_lower in t.description.lower()
                or any(query_lower in tag.lower() for tag in t.tags)
            ):
                results.append(t)
        return results

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _remove_server_tools(self, server_id: str) -> None:
        to_remove = [
            tid for tid, t in self._tools.items() if t.server_id == server_id
        ]
        for tid in to_remove:
            del self._tools[tid]
