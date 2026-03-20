"""Unit tests for SSE formatting utilities."""

from __future__ import annotations

import json

from workflow_engine.sse import format_keepalive, format_sse


class TestFormatSSE:
    def test_basic_event(self):
        result = format_sse("thinking", {"text": "hello"})
        assert result.startswith("event: thinking\n")
        assert "data: " in result
        assert result.endswith("\n\n")

        # Parse the data line
        lines = result.strip().split("\n")
        assert lines[0] == "event: thinking"
        data = json.loads(lines[1].removeprefix("data: "))
        assert data == {"text": "hello"}

    def test_nested_data(self):
        payload = {"agent": "a", "nested": {"key": [1, 2, 3]}}
        result = format_sse("update", payload)
        lines = result.strip().split("\n")
        data = json.loads(lines[1].removeprefix("data: "))
        assert data == payload

    def test_special_characters(self):
        payload = {"text": 'He said "hello" & <goodbye>'}
        result = format_sse("msg", payload)
        data = json.loads(result.strip().split("\n")[1].removeprefix("data: "))
        assert data["text"] == 'He said "hello" & <goodbye>'

    def test_non_serializable_uses_str(self):
        """format_sse uses default=str for non-JSON-serializable values."""
        from datetime import datetime

        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = format_sse("event", {"timestamp": dt})
        data = json.loads(result.strip().split("\n")[1].removeprefix("data: "))
        assert "2024" in data["timestamp"]

    def test_empty_data(self):
        result = format_sse("done", {})
        lines = result.strip().split("\n")
        data = json.loads(lines[1].removeprefix("data: "))
        assert data == {}


class TestFormatKeepalive:
    def test_format(self):
        result = format_keepalive()
        assert result == ": keepalive\n\n"

    def test_is_sse_comment(self):
        result = format_keepalive()
        assert result.startswith(":")
