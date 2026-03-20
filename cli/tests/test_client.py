"""Tests for NgenClient output formatting and SSE parsing."""

from __future__ import annotations

from ngen_cli.output import print_sse_event


class TestOutputFormatting:
    def test_print_sse_keepalive_silent(self, capsys):
        """Keepalive events produce no output."""
        print_sse_event("keepalive", None)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_sse_done_event(self, capsys):
        """Done event prints status and run_id."""
        print_sse_event("done", {"status": "completed", "run_id": "abc123"})
        captured = capsys.readouterr()
        assert "completed" in captured.out
        assert "abc123" in captured.out

    def test_print_sse_error_event(self, capsys):
        """Error event prints the error message."""
        print_sse_event("error", {"error": "something broke"})
        captured = capsys.readouterr()
        assert "something broke" in captured.out

    def test_print_sse_waiting_approval(self, capsys):
        """Waiting approval event shows gate and run_id."""
        print_sse_event("waiting_approval", {"run_id": "r1", "gate": "review"})
        captured = capsys.readouterr()
        assert "Approval required" in captured.out
        assert "review" in captured.out
