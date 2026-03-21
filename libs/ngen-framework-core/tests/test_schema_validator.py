"""Tests for JSON schema validation of CRD documents."""

from __future__ import annotations

from ngen_framework_core.schema_validator import validate_crd, validate_crd_yaml


class TestValidateCRD:
    def test_valid_workflow(self):
        doc = {
            "apiVersion": "ngen.io/v1",
            "kind": "Workflow",
            "metadata": {"name": "test-wf"},
            "spec": {"topology": "sequential", "agents": [{"ref": "a"}]},
        }
        errors = validate_crd(doc)
        assert errors == []

    def test_missing_api_version(self):
        doc = {
            "kind": "Workflow",
            "metadata": {"name": "test"},
            "spec": {"topology": "sequential"},
        }
        errors = validate_crd(doc)
        assert any("apiVersion" in e for e in errors)

    def test_missing_metadata(self):
        doc = {
            "apiVersion": "ngen.io/v1",
            "kind": "Workflow",
            "spec": {"topology": "sequential"},
        }
        errors = validate_crd(doc)
        assert any("metadata" in e for e in errors)

    def test_unknown_kind_no_errors(self):
        """Unknown kinds should pass (no schema to validate against)."""
        doc = {
            "apiVersion": "ngen.io/v1",
            "kind": "UnknownThing",
            "metadata": {"name": "x"},
        }
        errors = validate_crd(doc)
        assert errors == []

    def test_valid_agent(self):
        doc = {
            "apiVersion": "ngen.io/v1",
            "kind": "Agent",
            "metadata": {"name": "my-agent"},
            "spec": {
                "framework": "langgraph",
                "model": {"name": "claude"},
                "systemPrompt": "You are helpful.",
            },
        }
        errors = validate_crd(doc)
        assert errors == []


class TestValidateCRDYaml:
    def test_valid_yaml(self):
        yaml_str = """
apiVersion: ngen.io/v1
kind: Workflow
metadata:
  name: test
spec:
  topology: sequential
  agents:
    - ref: agent-a
"""
        errors = validate_crd_yaml(yaml_str)
        assert errors == []

    def test_invalid_yaml(self):
        errors = validate_crd_yaml("not: valid: yaml: [")
        assert len(errors) == 1
        assert "Invalid YAML" in errors[0]

    def test_non_mapping(self):
        errors = validate_crd_yaml("- just\n- a\n- list")
        assert any("mapping" in e for e in errors)
