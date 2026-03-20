"""Memory interceptor for automatic event-to-memory persistence.

The MemoryInterceptor is an EventInterceptor that writes agent execution
events to the appropriate memory type. It is an observability interceptor
— it never halts the event stream.
"""

from __future__ import annotations

import json
from typing import Any

from .memory_manager import DefaultMemoryManager
from .protocols import AgentEvent, AgentEventType, MemoryType


# Default mapping from event types to memory types
_DEFAULT_EVENT_MAPPING: dict[AgentEventType, MemoryType] = {
    AgentEventType.TOOL_CALL_END: MemoryType.TOOL_LOG,
    AgentEventType.RESPONSE: MemoryType.CONVERSATIONAL,
    AgentEventType.STATE_CHECKPOINT: MemoryType.WORKFLOW,
}


class MemoryInterceptor:
    """EventInterceptor that persists agent events to memory.

    This interceptor writes events to the appropriate memory type based
    on a configurable event→memory mapping. It never halts the event
    stream — all events pass through unchanged.

    Parameters
    ----------
    manager:
        The DefaultMemoryManager to write entries to.
    event_mapping:
        Custom mapping from AgentEventType to MemoryType. If not provided,
        uses the default mapping (TOOL_CALL_END→TOOL_LOG, RESPONSE→CONVERSATIONAL,
        STATE_CHECKPOINT→WORKFLOW).
    """

    def __init__(
        self,
        manager: DefaultMemoryManager,
        event_mapping: dict[AgentEventType, MemoryType] | None = None,
    ) -> None:
        self._manager = manager
        self._event_mapping = event_mapping or dict(_DEFAULT_EVENT_MAPPING)

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        """Persist event data to memory and pass the event through."""
        memory_type = self._event_mapping.get(event.type)
        if memory_type is None:
            return event

        content = self._format_event_content(event)
        metadata: dict[str, Any] = {
            "event_type": event.type.value,
            "agent_name": event.agent_name,
        }
        if event.timestamp:
            metadata["event_timestamp"] = event.timestamp

        role: str | None = None
        if memory_type == MemoryType.CONVERSATIONAL:
            role = "assistant"

        await self._manager.write_memory(
            memory_type,
            content,
            role=role,
            metadata=metadata,
        )

        return event

    @staticmethod
    def _format_event_content(event: AgentEvent) -> str:
        """Format event data as a string for memory storage."""
        if not event.data:
            return f"[{event.type.value}]"
        try:
            return json.dumps(event.data, default=str)
        except (TypeError, ValueError):
            return str(event.data)
