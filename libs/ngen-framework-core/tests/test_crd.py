"""Tests for CRD (Custom Resource Definition) models and parsing utilities."""

from __future__ import annotations

import tempfile

import pytest
from ngen_framework_core.crd import (
    AgentCRD,
    MCPServerCRD,
    ModelCRD,
    SkillCRD,
    ToolCRD,
    WorkflowCRD,
    parse_crd,
    parse_crd_file,
    validate_crd,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _agent_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "Agent",
        "metadata": {"name": "test-bot"},
        "spec": {
            "framework": "langgraph",
            "model": {"name": "claude-opus-4-6"},
            "systemPrompt": "You are a test agent.",
        },
    }
    base.update(overrides)
    return base


def _workflow_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "Workflow",
        "metadata": {"name": "test-workflow"},
        "spec": {
            "agents": [{"ref": "agent-a"}, {"ref": "agent-b"}],
            "topology": "sequential",
        },
    }
    base.update(overrides)
    return base


def _mcp_server_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "MCPServer",
        "metadata": {"name": "test-mcp"},
        "spec": {
            "source": {
                "type": "openapi",
                "url": "https://api.example.com/openapi.json",
            },
        },
    }
    base.update(overrides)
    return base


def _tool_crd_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "Tool",
        "metadata": {"name": "calculator"},
        "spec": {
            "handler": "my_module:calculate",
            "description": "A calculator tool",
        },
    }
    base.update(overrides)
    return base


def _skill_crd_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "Skill",
        "metadata": {"name": "summarizer"},
        "spec": {
            "model": {"name": "claude-opus-4-6"},
            "systemPrompt": "Summarize the input text.",
        },
    }
    base.update(overrides)
    return base


def _model_dict(**overrides: object) -> dict:
    base = {
        "apiVersion": "ngen.io/v1",
        "kind": "Model",
        "metadata": {"name": "claude-opus-4-6"},
        "spec": {
            "provider": "anthropic",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "capabilities": ["vision", "tool-use", "streaming"],
            "costPerMToken": {"input": 5.00, "output": 25.00},
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Agent CRD tests
# ---------------------------------------------------------------------------


class TestAgentCRD:
    def test_parse_minimal(self) -> None:
        crd = parse_crd(_agent_dict())
        assert isinstance(crd, AgentCRD)
        assert crd.metadata.name == "test-bot"
        assert crd.spec.framework.value == "langgraph"
        assert crd.spec.model.name == "claude-opus-4-6"

    def test_parse_full(self) -> None:
        data = _agent_dict()
        data["metadata"]["namespace"] = "acme-corp"
        data["metadata"]["labels"] = {"team": "support"}
        data["spec"]["model"]["fallback"] = "claude-sonnet-4-6"
        data["spec"]["tools"] = [
            {"name": "search-kb", "mcpServer": "knowledge-base"},
            {"name": "custom", "handler": "my_module:handler"},
        ]
        data["spec"]["guardrails"] = ["pii-redaction", "topic-restriction"]
        data["spec"]["scaling"] = {"minReplicas": 2, "maxReplicas": 20}
        data["spec"]["observability"] = {"tracing": True, "costTracking": True}

        crd = parse_crd(data)
        assert isinstance(crd, AgentCRD)
        assert crd.metadata.namespace == "acme-corp"
        assert crd.metadata.labels["team"] == "support"
        assert crd.spec.model.fallback == "claude-sonnet-4-6"
        assert len(crd.spec.tools) == 2
        assert crd.spec.tools[0].mcp_server == "knowledge-base"
        assert crd.spec.tools[1].handler == "my_module:handler"
        assert len(crd.spec.guardrails) == 2
        assert crd.spec.scaling.min_replicas == 2
        assert crd.spec.scaling.max_replicas == 20

    def test_all_frameworks(self) -> None:
        for fw in ["langgraph", "claude-agent-sdk", "crewai", "adk", "ms-agent-framework"]:
            data = _agent_dict()
            data["spec"]["framework"] = fw
            crd = parse_crd(data)
            assert isinstance(crd, AgentCRD)
            assert crd.spec.framework.value == fw

    def test_invalid_framework(self) -> None:
        data = _agent_dict()
        data["spec"]["framework"] = "unknown-framework"
        with pytest.raises((ValueError, KeyError)):
            parse_crd(data)

    def test_invalid_name(self) -> None:
        data = _agent_dict()
        data["metadata"]["name"] = "INVALID-UPPERCASE"
        with pytest.raises((ValueError, KeyError)):
            parse_crd(data)

    def test_invalid_api_version(self) -> None:
        data = _agent_dict()
        data["apiVersion"] = "ngen.io/v99"
        with pytest.raises((ValueError, KeyError)):
            parse_crd(data)

    def test_supported_api_versions(self) -> None:
        for version in ["ngen.io/v1", "ngen.io/v1beta1", "ngen.io/v1alpha1"]:
            data = _agent_dict()
            data["apiVersion"] = version
            crd = parse_crd(data)
            assert isinstance(crd, AgentCRD)

    def test_missing_required_fields(self) -> None:
        # Missing systemPrompt
        data = _agent_dict()
        del data["spec"]["systemPrompt"]
        with pytest.raises((ValueError, KeyError)):
            parse_crd(data)


# ---------------------------------------------------------------------------
# Workflow CRD tests
# ---------------------------------------------------------------------------


class TestWorkflowCRD:
    def test_parse_sequential(self) -> None:
        crd = parse_crd(_workflow_dict())
        assert isinstance(crd, WorkflowCRD)
        assert crd.spec.topology.value == "sequential"
        assert len(crd.spec.agents) == 2

    def test_parse_graph_with_edges(self) -> None:
        data = _workflow_dict()
        data["spec"]["topology"] = "graph"
        data["spec"]["edges"] = [
            {"from": "agent-a", "to": "agent-b", "condition": "needs_escalation"},
        ]
        crd = parse_crd(data)
        assert isinstance(crd, WorkflowCRD)
        assert len(crd.spec.edges) == 1
        assert crd.spec.edges[0].source == "agent-a"
        assert crd.spec.edges[0].condition == "needs_escalation"

    def test_human_in_the_loop(self) -> None:
        data = _workflow_dict()
        data["spec"]["humanInTheLoop"] = {
            "approvalGate": "before-deploy",
            "timeoutSeconds": 7200,
        }
        crd = parse_crd(data)
        assert isinstance(crd, WorkflowCRD)
        assert crd.spec.human_in_the_loop is not None
        assert crd.spec.human_in_the_loop.approval_gate == "before-deploy"
        assert crd.spec.human_in_the_loop.timeout_seconds == 7200

    def test_all_topologies(self) -> None:
        for topo in ["sequential", "parallel", "graph", "hierarchical"]:
            data = _workflow_dict()
            data["spec"]["topology"] = topo
            crd = parse_crd(data)
            assert crd.spec.topology.value == topo


# ---------------------------------------------------------------------------
# MCPServer CRD tests
# ---------------------------------------------------------------------------


class TestMCPServerCRD:
    def test_parse_minimal(self) -> None:
        crd = parse_crd(_mcp_server_dict())
        assert isinstance(crd, MCPServerCRD)
        assert crd.spec.source.type == "openapi"
        assert crd.spec.auth.type == "none"
        assert crd.spec.transport == "streamable-http"

    def test_with_auth(self) -> None:
        data = _mcp_server_dict()
        data["spec"]["auth"] = {"type": "oauth2", "secretRef": "my-credentials"}
        crd = parse_crd(data)
        assert crd.spec.auth.type == "oauth2"
        assert crd.spec.auth.secret_ref == "my-credentials"

    def test_custom_scaling(self) -> None:
        data = _mcp_server_dict()
        data["spec"]["scaling"] = {"minReplicas": 2, "maxReplicas": 5}
        crd = parse_crd(data)
        assert crd.spec.scaling.min_replicas == 2
        assert crd.spec.scaling.max_replicas == 5


# ---------------------------------------------------------------------------
# Model CRD tests
# ---------------------------------------------------------------------------


class TestModelCRD:
    def test_parse_full(self) -> None:
        crd = parse_crd(_model_dict())
        assert isinstance(crd, ModelCRD)
        assert crd.spec.provider == "anthropic"
        assert "vision" in crd.spec.capabilities
        assert crd.spec.cost_per_m_token["input"] == 5.00
        assert crd.spec.cost_per_m_token["output"] == 25.00

    def test_with_context_window(self) -> None:
        data = _model_dict()
        data["spec"]["contextWindow"] = 200000
        data["spec"]["maxOutputTokens"] = 128000
        crd = parse_crd(data)
        assert crd.spec.context_window == 200000
        assert crd.spec.max_output_tokens == 128000


# ---------------------------------------------------------------------------
# Parsing utility tests
# ---------------------------------------------------------------------------


class TestParseCRD:
    def test_missing_kind(self) -> None:
        with pytest.raises(ValueError, match="must have a 'kind' field"):
            parse_crd({"apiVersion": "ngen.io/v1"})

    def test_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="Unknown CRD kind"):
            parse_crd({"apiVersion": "ngen.io/v1", "kind": "Unknown"})

    def test_all_kinds(self) -> None:
        crds = [_agent_dict(), _workflow_dict(), _mcp_server_dict(), _model_dict()]
        for data in crds:
            crd = parse_crd(data)
            assert crd.kind == data["kind"]


class TestParseCRDFile:
    def test_single_document(self) -> None:
        import yaml

        content = yaml.dump(_agent_dict())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            crds = parse_crd_file(f.name)
        assert len(crds) == 1
        assert isinstance(crds[0], AgentCRD)

    def test_multi_document(self) -> None:
        import yaml

        docs = [_agent_dict(), _model_dict()]
        content = "---\n".join(yaml.dump(d) for d in docs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            crds = parse_crd_file(f.name)
        assert len(crds) == 2
        assert isinstance(crds[0], AgentCRD)
        assert isinstance(crds[1], ModelCRD)

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_crd_file("/nonexistent/path.yaml")


class TestValidateCRD:
    def test_valid(self) -> None:
        errors = validate_crd(_agent_dict())
        assert errors == []

    def test_missing_kind(self) -> None:
        errors = validate_crd({"apiVersion": "ngen.io/v1"})
        assert any("kind" in e for e in errors)

    def test_missing_api_version(self) -> None:
        errors = validate_crd({"kind": "Agent"})
        assert any("apiVersion" in e for e in errors)

    def test_unsupported_api_version(self) -> None:
        errors = validate_crd({"apiVersion": "ngen.io/v99", "kind": "Agent"})
        assert any("Unsupported" in e for e in errors)

    def test_unknown_kind(self) -> None:
        errors = validate_crd({"apiVersion": "ngen.io/v1", "kind": "Unknown"})
        assert any("Unknown kind" in e for e in errors)

    def test_invalid_spec(self) -> None:
        data = _agent_dict()
        del data["spec"]["systemPrompt"]
        errors = validate_crd(data)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Tool CRD tests
# ---------------------------------------------------------------------------


class TestToolCRD:
    def test_parse_minimal(self) -> None:
        crd = parse_crd(_tool_crd_dict())
        assert isinstance(crd, ToolCRD)
        assert crd.kind == "Tool"
        assert crd.metadata.name == "calculator"
        assert crd.spec.handler == "my_module:calculate"

    def test_parse_full(self) -> None:
        data = _tool_crd_dict()
        data["spec"]["inputSchema"] = {"type": "object", "properties": {"a": {"type": "number"}}}
        data["spec"]["outputSchema"] = {"type": "object", "properties": {"result": {"type": "number"}}}
        data["spec"]["timeoutMs"] = 5000
        data["spec"]["idempotent"] = True
        data["spec"]["healthCheck"] = "/health"
        data["spec"]["mcpServer"] = "calc-server"
        crd = parse_crd(data)
        assert isinstance(crd, ToolCRD)
        assert crd.spec.input_schema["type"] == "object"
        assert crd.spec.timeout_ms == 5000
        assert crd.spec.idempotent is True
        assert crd.spec.health_check == "/health"
        assert crd.spec.mcp_server == "calc-server"

    def test_validate(self) -> None:
        errors = validate_crd(_tool_crd_dict())
        assert errors == []

    def test_all_kinds_includes_tool(self) -> None:
        crd = parse_crd(_tool_crd_dict())
        assert crd.kind == "Tool"


# ---------------------------------------------------------------------------
# Skill CRD tests
# ---------------------------------------------------------------------------


class TestSkillCRD:
    def test_parse_minimal(self) -> None:
        crd = parse_crd(_skill_crd_dict())
        assert isinstance(crd, SkillCRD)
        assert crd.kind == "Skill"
        assert crd.metadata.name == "summarizer"
        assert crd.spec.model.name == "claude-opus-4-6"
        assert crd.spec.system_prompt == "Summarize the input text."

    def test_parse_full(self) -> None:
        data = _skill_crd_dict()
        data["spec"]["model"]["fallback"] = "claude-sonnet-4-6"
        data["spec"]["tools"] = [{"name": "lookup", "handler": "mod:fn"}]
        data["spec"]["guardrails"] = ["pii-filter"]
        data["spec"]["outputSchema"] = {"type": "object"}
        data["spec"]["eval"] = {
            "dimensions": ["accuracy", "latency"],
            "threshold": 0.9,
            "datasetRef": "eval-v1",
        }
        data["spec"]["cost"] = {
            "maxCostPerInvocation": 0.50,
            "dailyBudget": 100.0,
            "alertThreshold": 0.85,
        }
        crd = parse_crd(data)
        assert isinstance(crd, SkillCRD)
        assert crd.spec.model.fallback == "claude-sonnet-4-6"
        assert len(crd.spec.tools) == 1
        assert len(crd.spec.guardrails) == 1
        assert crd.spec.eval.threshold == 0.9
        assert crd.spec.cost.max_cost_per_invocation == 0.50

    def test_validate(self) -> None:
        errors = validate_crd(_skill_crd_dict())
        assert errors == []

    def test_missing_system_prompt(self) -> None:
        data = _skill_crd_dict()
        del data["spec"]["systemPrompt"]
        with pytest.raises((ValueError, KeyError)):
            parse_crd(data)


# ---------------------------------------------------------------------------
# Enriched Agent CRD tests (RAPIDS fields)
# ---------------------------------------------------------------------------


class TestAgentCRDRAPIDS:
    def test_parse_with_rapids_fields(self) -> None:
        data = _agent_dict()
        data["spec"]["capabilities"] = ["reasoning", "tool-use"]
        data["spec"]["decisionLoop"] = {"maxTurns": 25, "exitConditions": ["done"]}
        data["spec"]["state"] = {"persistence": "redis", "ttlSeconds": 7200}
        data["spec"]["escalation"] = {
            "target": "human-reviewer",
            "conditions": ["low_confidence"],
            "timeoutSeconds": 1800,
        }
        data["spec"]["eval"] = {
            "dimensions": ["accuracy"],
            "threshold": 0.95,
        }
        data["spec"]["cost"] = {
            "maxCostPerInvocation": 1.0,
            "dailyBudget": 500.0,
        }
        data["spec"]["labels"] = {"team": "support"}
        data["spec"]["actionGuards"] = [
            {"tool": "send-email", "policy": "human-approval"}
        ]
        crd = parse_crd(data)
        assert isinstance(crd, AgentCRD)
        assert "reasoning" in crd.spec.capabilities
        assert crd.spec.decision_loop.max_turns == 25
        assert crd.spec.state.persistence == "redis"
        assert crd.spec.escalation.target == "human-reviewer"
        assert crd.spec.eval.threshold == 0.95
        assert crd.spec.cost.max_cost_per_invocation == 1.0
        assert crd.spec.labels["team"] == "support"
        assert len(crd.spec.action_guards) == 1
        assert crd.spec.action_guards[0].tool == "send-email"

    def test_rapids_fields_defaults(self) -> None:
        """Existing agent CRDs should parse fine without RAPIDS fields."""
        crd = parse_crd(_agent_dict())
        assert isinstance(crd, AgentCRD)
        assert crd.spec.capabilities == []
        assert crd.spec.labels == {}


# ---------------------------------------------------------------------------
# Updated all-kinds test
# ---------------------------------------------------------------------------


class TestParseCRDAllKinds:
    def test_all_six_kinds(self) -> None:
        crds = [
            _agent_dict(),
            _workflow_dict(),
            _mcp_server_dict(),
            _model_dict(),
            _tool_crd_dict(),
            _skill_crd_dict(),
        ]
        for data in crds:
            crd = parse_crd(data)
            assert crd.kind == data["kind"]
