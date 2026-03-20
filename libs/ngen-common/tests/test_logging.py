"""Tests for ngen_common.logging — structured logging configuration."""

from __future__ import annotations

import json
import logging

from ngen_common.logging import JSONFormatter, get_logger, setup_logging


class TestJSONFormatter:
    def test_formats_as_json(self) -> None:
        formatter = JSONFormatter(service_name="test-svc")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["service"] == "test-svc"
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello world"
        assert "timestamp" in parsed

    def test_includes_extra_fields(self) -> None:
        formatter = JSONFormatter(service_name="svc")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="event", args=(), exc_info=None,
        )
        record.request_id = "req-abc"  # type: ignore[attr-defined]
        record.tenant_id = "t-1"  # type: ignore[attr-defined]
        output = json.loads(formatter.format(record))
        assert output["request_id"] == "req-abc"
        assert output["tenant_id"] == "t-1"

    def test_includes_exception(self) -> None:
        formatter = JSONFormatter(service_name="svc")
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=1,
            msg="failed", args=(), exc_info=exc_info,
        )
        output = json.loads(formatter.format(record))
        assert "exception" in output
        assert "ValueError" in output["exception"]


class TestSetupLogging:
    def test_returns_logger(self) -> None:
        logger = setup_logging("my-service", level="DEBUG")
        assert logger.name == "my-service"
        assert logger.level == logging.DEBUG

    def test_json_handler(self) -> None:
        logger = setup_logging("json-svc", json_output=True)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_human_readable_handler(self) -> None:
        logger = setup_logging("plain-svc", json_output=False)
        assert len(logger.handlers) == 1
        assert not isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_idempotent(self) -> None:
        setup_logging("idem-svc")
        logger = setup_logging("idem-svc")
        assert len(logger.handlers) == 1  # Not duplicated


class TestGetLogger:
    def test_child_logger(self) -> None:
        logger = get_logger("parent", "routes")
        assert logger.name == "parent.routes"

    def test_no_module(self) -> None:
        logger = get_logger("standalone")
        assert logger.name == "standalone"
