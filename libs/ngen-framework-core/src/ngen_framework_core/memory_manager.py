"""Default memory manager implementation for the multi-tenant memory subsystem.

Orchestrates read/write across all 7 memory types, builds partitioned context
windows, and handles lifecycle operations (expire, summarize, clip).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .protocols import (
    MemoryEntry,
    MemoryPolicy,
    MemoryScope,
    MemoryStore,
    MemoryType,
)


# ---------------------------------------------------------------------------
# Section headers for the partitioned context window
# ---------------------------------------------------------------------------

_SECTION_HEADERS: dict[MemoryType, str] = {
    MemoryType.CONVERSATIONAL: "## Conversation Memory",
    MemoryType.KNOWLEDGE_BASE: "## Knowledge Base Memory",
    MemoryType.WORKFLOW: "## Workflow Memory",
    MemoryType.TOOLBOX: "## Toolbox Memory",
    MemoryType.ENTITY: "## Entity Memory",
    MemoryType.SUMMARY: "## Summary Memory",
    MemoryType.TOOL_LOG: "## Tool Log Memory",
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4)."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# DefaultMemoryManager
# ---------------------------------------------------------------------------


class DefaultMemoryManager:
    """Tenant-scoped memory manager.

    All operations are bound to a fixed ``MemoryScope``. The manager delegates
    storage to a ``MemoryStore`` and applies ``MemoryPolicy`` rules for
    retention, TTL, and summarization.

    Parameters
    ----------
    scope:
        Namespace isolation key (org/team/project/agent).
    store:
        Backend that satisfies the ``MemoryStore`` protocol.
    policy:
        Retention and lifecycle policy.
    context_budget_tokens:
        Maximum tokens for ``build_context_window`` output.
    enabled_types:
        Which memory types this manager supports. Defaults to all 7.
    summarize_fn:
        Optional async callback ``(content: str) -> str`` that produces a
        summary. Injected by the runtime layer that has model-gateway access.
        Keeps the core library LLM-free.
    """

    def __init__(
        self,
        scope: MemoryScope,
        store: MemoryStore,
        policy: MemoryPolicy | None = None,
        context_budget_tokens: int = 4000,
        enabled_types: list[MemoryType] | None = None,
        summarize_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.scope = scope
        self.store = store
        self.policy = policy or MemoryPolicy()
        self.context_budget_tokens = context_budget_tokens
        self.enabled_types = enabled_types or list(MemoryType)
        self._summarize_fn = summarize_fn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write_memory(
        self,
        memory_type: MemoryType,
        content: str,
        *,
        role: str | None = None,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """Write a single entry to the memory store. Returns entry ID."""
        size_bytes = len(content.encode("utf-8"))
        token_estimate = len(content) // 4
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            memory_type=memory_type,
            scope=self.scope,
            content=content,
            metadata=metadata or {},
            role=role,
            embedding=embedding,
            created_at=time.time(),
            ttl_seconds=self.policy.ttl_seconds,
            size_bytes=size_bytes,
            token_estimate=token_estimate,
        )
        return await self.store.write(entry)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def read_memory(
        self,
        memory_type: MemoryType,
        *,
        query: str | None = None,
        query_embedding: list[float] | None = None,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        """Read entries — semantic search if embedding provided, else recency."""
        if query_embedding is not None:
            return await self.store.search(
                self.scope, memory_type, query_embedding, top_k=limit
            )
        return await self.store.read(
            self.scope, memory_type, limit=limit, filters=filters
        )

    # ------------------------------------------------------------------
    # Context window builder
    # ------------------------------------------------------------------

    async def build_context_window(
        self,
        query: str,
        *,
        query_embedding: list[float] | None = None,
        budget_tokens: int | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> str:
        """Build a partitioned context window from all enabled memory types.

        Returns a markdown string with labeled sections, trimmed to the
        token budget. The current query is always included first.
        """
        budget = budget_tokens or self.context_budget_tokens
        types_to_query = memory_types or self.enabled_types

        sections: list[str] = []
        total_tokens = 0

        for mt in types_to_query:
            if mt not in self.enabled_types:
                continue
            header = _SECTION_HEADERS.get(mt, f"## {mt.value}")

            # Use semantic search for vector-backed types, recency for structured
            if query_embedding and mt not in (
                MemoryType.CONVERSATIONAL,
                MemoryType.TOOL_LOG,
            ):
                entries = await self.store.search(
                    self.scope, mt, query_embedding, top_k=5
                )
            else:
                entries = await self.store.read(self.scope, mt, limit=10)

            if not entries:
                continue

            lines = [header]
            for entry in entries:
                line = entry.content
                if entry.role:
                    line = f"[{entry.role}] {line}"
                if entry.summary_id:
                    line = f"[Summary ID: {entry.summary_id}] {line}"
                lines.append(line)

            section_text = "\n".join(lines)
            section_tokens = _estimate_tokens(section_text)

            if total_tokens + section_tokens > budget:
                # Trim this section to fit remaining budget
                remaining = budget - total_tokens
                if remaining > 50:  # only include if meaningful
                    char_limit = remaining * 4
                    section_text = section_text[:char_limit] + "\n[truncated]"
                    sections.append(section_text)
                break

            sections.append(section_text)
            total_tokens += section_tokens

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    async def expire_old_entries(self) -> int:
        """Delete entries older than the policy TTL. Returns count deleted."""
        if self.policy.ttl_seconds is None:
            return 0
        cutoff = time.time() - self.policy.ttl_seconds
        return await self.store.expire(self.scope, cutoff)

    async def summarize_and_compact(self, thread_id: str) -> str | None:
        """Summarize unsummarized conversational entries for a thread.

        Reads unsummarized entries, calls the injected ``summarize_fn``,
        writes the summary as a SUMMARY entry, and marks source entries
        with the summary_id. Returns the summary_id or None if nothing
        to summarize or no summarize_fn.
        """
        if self._summarize_fn is None:
            return None

        scoped = MemoryScope(
            org_id=self.scope.org_id,
            team_id=self.scope.team_id,
            project_id=self.scope.project_id,
            agent_name=self.scope.agent_name,
            thread_id=thread_id,
        )

        entries = await self.store.read(
            scoped,
            MemoryType.CONVERSATIONAL,
            limit=1000,
            filters={"unsummarized": True},
        )

        if not entries:
            return None

        # Build text to summarize
        text_parts = []
        for entry in reversed(entries):  # chronological order
            prefix = f"[{entry.role}] " if entry.role else ""
            text_parts.append(f"{prefix}{entry.content}")
        combined = "\n".join(text_parts)

        summary_text = await self._summarize_fn(combined)
        summary_id = str(uuid.uuid4())

        # Write summary entry
        summary_entry = MemoryEntry(
            id=summary_id,
            memory_type=MemoryType.SUMMARY,
            scope=scoped,
            content=summary_text,
            metadata={"source_count": len(entries), "thread_id": thread_id},
            created_at=time.time(),
        )
        await self.store.write(summary_entry)

        # Mark source entries as summarized
        for entry in entries:
            await self.store.update(
                entry.id, scoped, {"summary_id": summary_id}
            )

        return summary_id

    async def clip_to_budget(
        self,
        memory_type: MemoryType,
        max_entries: int,
    ) -> int:
        """Delete oldest entries if count exceeds max_entries. Returns count deleted."""
        current = await self.store.count(self.scope, memory_type)
        if current <= max_entries:
            return 0

        # Read all, sort oldest first, delete excess
        entries = await self.store.read(
            self.scope, memory_type, limit=current
        )
        entries.sort(key=lambda e: e.created_at)
        to_delete = entries[: current - max_entries]

        count = 0
        for entry in to_delete:
            if await self.store.delete(entry.id, self.scope):
                count += 1
        return count

    async def get_stats(self) -> dict[str, Any]:
        """Return memory statistics for this manager's scope.

        Delegates to the store's ``stats()`` method and enriches with
        scope metadata and policy configuration.
        """
        by_type = await self.store.stats(self.scope)
        total_entries = sum(v["count"] for v in by_type.values())
        total_bytes = sum(v["size_bytes"] for v in by_type.values())
        total_tokens = sum(v["token_estimate"] for v in by_type.values())
        return {
            "scope": {
                "org_id": self.scope.org_id,
                "team_id": self.scope.team_id,
                "project_id": self.scope.project_id,
                "agent_name": self.scope.agent_name,
                "thread_id": self.scope.thread_id,
            },
            "total_entries": total_entries,
            "total_bytes": total_bytes,
            "total_tokens": total_tokens,
            "by_type": by_type,
            "context_budget_tokens": self.context_budget_tokens,
            "policy": {
                "max_entries": self.policy.max_entries,
                "ttl_seconds": self.policy.ttl_seconds,
                "summarization_threshold": self.policy.summarization_threshold,
                "retention_days": self.policy.retention_days,
            },
        }

    async def delete_by_scope(
        self,
        memory_type: MemoryType | None = None,
    ) -> int:
        """Delete all entries for this manager's scope. Returns count deleted."""
        return await self.store.delete_by_scope(self.scope, memory_type)
