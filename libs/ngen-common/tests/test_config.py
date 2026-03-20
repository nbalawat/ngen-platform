"""Tests for ngen_common.config — configuration utilities."""

from __future__ import annotations

import os

from ngen_common.config import DatabaseConfig, ServiceConfig, ServiceURLs


class TestServiceConfig:
    def test_defaults(self) -> None:
        cfg = ServiceConfig()
        assert cfg.service_name == "unknown"
        assert cfg.port == 8000
        assert cfg.debug is False
        assert cfg.log_level == "INFO"
        assert cfg.namespace == "default"

    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("NGEN_SERVICE_NAME", "workflow-engine")
        monkeypatch.setenv("NGEN_PORT", "8003")
        monkeypatch.setenv("NGEN_DEBUG", "true")
        monkeypatch.setenv("NGEN_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("NGEN_NAMESPACE", "prod")
        cfg = ServiceConfig.from_env()
        assert cfg.service_name == "workflow-engine"
        assert cfg.port == 8003
        assert cfg.debug is True
        assert cfg.log_level == "DEBUG"
        assert cfg.namespace == "prod"

    def test_from_env_with_prefix(self, monkeypatch) -> None:
        monkeypatch.setenv("WF_SERVICE_NAME", "wf")
        monkeypatch.setenv("WF_PORT", "9000")
        cfg = ServiceConfig.from_env(prefix="WF_")
        assert cfg.service_name == "wf"
        assert cfg.port == 9000

    def test_overrides_take_precedence(self, monkeypatch) -> None:
        monkeypatch.setenv("NGEN_PORT", "8003")
        cfg = ServiceConfig.from_env(port=9999)
        assert cfg.port == 9999

    def test_defaults_when_env_missing(self) -> None:
        # Ensure no NGEN_ vars are set
        for key in ("SERVICE_NAME", "PORT", "DEBUG", "LOG_LEVEL", "NAMESPACE"):
            os.environ.pop(f"NGEN_{key}", None)
        cfg = ServiceConfig.from_env()
        assert cfg.port == 8000
        assert cfg.debug is False


class TestDatabaseConfig:
    def test_defaults(self) -> None:
        cfg = DatabaseConfig()
        assert "sqlite" in cfg.url
        assert cfg.pool_size == 5
        assert cfg.echo is False

    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("NGEN_DATABASE_URL", "postgresql+asyncpg://localhost/ngen")
        monkeypatch.setenv("NGEN_DB_POOL_SIZE", "20")
        monkeypatch.setenv("NGEN_DB_ECHO", "true")
        cfg = DatabaseConfig.from_env()
        assert cfg.url == "postgresql+asyncpg://localhost/ngen"
        assert cfg.pool_size == 20
        assert cfg.echo is True

    def test_overrides(self) -> None:
        cfg = DatabaseConfig.from_env(url="sqlite:///:memory:", pool_size=1)
        assert cfg.url == "sqlite:///:memory:"
        assert cfg.pool_size == 1


class TestServiceURLs:
    def test_defaults(self) -> None:
        urls = ServiceURLs()
        assert urls.workflow_engine == "http://localhost:8003"
        assert urls.governance == "http://localhost:8004"
        assert urls.mcp_manager == "http://localhost:8005"

    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("NGEN_WORKFLOW_URL", "http://wf:8003")
        monkeypatch.setenv("NGEN_GOVERNANCE_URL", "http://gov:8004")
        urls = ServiceURLs.from_env()
        assert urls.workflow_engine == "http://wf:8003"
        assert urls.governance == "http://gov:8004"

    def test_overrides(self) -> None:
        urls = ServiceURLs.from_env(workflow_engine="http://custom:9000")
        assert urls.workflow_engine == "http://custom:9000"
