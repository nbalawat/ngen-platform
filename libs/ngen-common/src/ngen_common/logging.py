"""Structured logging configuration for NGEN platform services.

Provides a consistent logging setup across all services with JSON-formatted
output suitable for container environments and log aggregation.
"""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service_name: str = "unknown") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Merge any extra fields attached via `extra={}` in log calls
        for key in ("request_id", "tenant_id", "namespace", "workflow_id", "agent_name"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, default=str)


def setup_logging(
    service_name: str,
    level: str = "INFO",
    json_output: bool = True,
) -> logging.Logger:
    """Configure and return a logger for an NGEN service.

    Args:
        service_name: Name of the service (e.g. "workflow-engine").
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, use JSON formatting; otherwise use human-readable.

    Returns:
        Configured root logger for the service.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on repeated calls
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JSONFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                f"%(asctime)s | {service_name} | %(levelname)-8s | %(name)s | %(message)s"
            )
        )
    logger.addHandler(handler)
    return logger


def get_logger(service_name: str, module: str | None = None) -> logging.Logger:
    """Get a child logger for a specific module within a service.

    Args:
        service_name: Parent service name.
        module: Optional module name (e.g. "routes", "engine").

    Returns:
        Logger instance.
    """
    name = f"{service_name}.{module}" if module else service_name
    return logging.getLogger(name)
