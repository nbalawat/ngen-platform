"""Tests for WorkflowState."""

from __future__ import annotations

import pytest

from workflow_engine.state import WorkflowState


class TestWorkflowState:
    async def test_get_set(self):
        state = WorkflowState()
        assert state.get("key") is None
        assert state.get("key", "default") == "default"
        await state.set("key", "value")
        assert state.get("key") == "value"

    async def test_initial_data(self):
        state = WorkflowState({"a": 1, "b": 2})
        assert state.get("a") == 1
        assert state.get("b") == 2

    async def test_to_dict(self):
        state = WorkflowState({"x": 10})
        await state.set("y", 20)
        result = state.to_dict()
        assert result == {"x": 10, "y": 20}
        # Ensure it's a copy
        result["z"] = 30
        assert state.get("z") is None

    async def test_merge(self):
        state = WorkflowState({"a": 1})
        await state.merge({"b": 2, "c": 3})
        assert state.get("a") == 1
        assert state.get("b") == 2
        assert state.get("c") == 3

    async def test_merge_overwrites(self):
        state = WorkflowState({"a": 1})
        await state.merge({"a": 99})
        assert state.get("a") == 99

    async def test_record_agent_output(self):
        state = WorkflowState()
        await state.record_agent_output("bot-a", {"text": "hello"})
        await state.record_agent_output("bot-a", {"text": "world"})
        await state.record_agent_output("bot-b", {"text": "hi"})
        outputs = state.agent_outputs
        assert len(outputs["bot-a"]) == 2
        assert len(outputs["bot-b"]) == 1
        assert outputs["bot-a"][0]["text"] == "hello"

    async def test_current_agent(self):
        state = WorkflowState()
        assert state.current_agent is None
        await state.set_current_agent("bot-a")
        assert state.current_agent == "bot-a"
        await state.set_current_agent(None)
        assert state.current_agent is None
