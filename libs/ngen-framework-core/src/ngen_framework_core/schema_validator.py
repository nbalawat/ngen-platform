"""JSON Schema validation for NGEN CRD documents.

Validates raw YAML/JSON documents against the JSON schemas defined
in the ``/schemas/`` directory. This provides an additional validation
layer on top of Pydantic model validation.

Usage::

    from ngen_framework_core.schema_validator import validate_crd

    raw = yaml.safe_load(yaml_string)
    errors = validate_crd(raw)
    if errors:
        raise ValueError(f"Schema validation failed: {errors}")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Schema directory relative to repo root
_SCHEMA_DIR: Path | None = None

# Map CRD kind to schema filename
KIND_TO_SCHEMA: dict[str, str] = {
    "Agent": "agent.schema.json",
    "Workflow": "workflow.schema.json",
    "Tool": "tool.schema.json",
    "Skill": "skill.schema.json",
    "Memory": "memory.schema.json",
    "Model": "model.schema.json",
    "MCPServer": "mcpserver.schema.json",
}

# Cache loaded schemas
_schema_cache: dict[str, dict] = {}


def _find_schema_dir() -> Path | None:
    """Locate the schemas/ directory by walking up from this file."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        schemas = current / "schemas"
        if schemas.is_dir():
            return schemas
        current = current.parent
    return None


def _load_schema(kind: str) -> dict | None:
    """Load a JSON schema for a CRD kind."""
    if kind in _schema_cache:
        return _schema_cache[kind]

    filename = KIND_TO_SCHEMA.get(kind)
    if not filename:
        return None

    global _SCHEMA_DIR
    if _SCHEMA_DIR is None:
        _SCHEMA_DIR = _find_schema_dir()
    if _SCHEMA_DIR is None:
        logger.debug("schemas/ directory not found")
        return None

    schema_path = _SCHEMA_DIR / filename
    if not schema_path.exists():
        logger.debug("Schema file not found: %s", schema_path)
        return None

    with open(schema_path) as f:
        schema = json.load(f)

    _schema_cache[kind] = schema
    return schema


def validate_crd(document: dict[str, Any]) -> list[str]:
    """Validate a raw CRD document against its JSON schema.

    Args:
        document: Parsed YAML/JSON document with ``kind`` field.

    Returns:
        List of validation error messages. Empty if valid.
    """
    kind = document.get("kind", "")
    schema = _load_schema(kind)
    if schema is None:
        return []  # No schema available — skip validation

    errors: list[str] = []

    # Basic structural checks from schema
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field in required:
        if field not in document:
            errors.append(f"Missing required field: '{field}'")

    # Validate apiVersion
    api_version = document.get("apiVersion", "")
    api_schema = properties.get("apiVersion", {})
    allowed_versions = api_schema.get("enum", [])
    if allowed_versions and api_version not in allowed_versions:
        errors.append(
            f"Invalid apiVersion: '{api_version}'. Allowed: {allowed_versions}"
        )

    # Validate kind matches
    kind_schema = properties.get("kind", {})
    allowed_kinds = kind_schema.get("enum", [])
    if allowed_kinds and kind not in allowed_kinds:
        errors.append(f"Invalid kind: '{kind}'. Allowed: {allowed_kinds}")

    # Validate spec required fields
    spec = document.get("spec", {})
    spec_schema = properties.get("spec", {})
    spec_required = spec_schema.get("required", [])
    for field in spec_required:
        if field not in spec:
            errors.append(f"Missing required spec field: '{field}'")

    return errors


def validate_crd_yaml(yaml_string: str) -> list[str]:
    """Validate a YAML string as a CRD document.

    Convenience wrapper that parses YAML and validates.
    """
    import yaml

    try:
        document = yaml.safe_load(yaml_string)
    except Exception as exc:
        return [f"Invalid YAML: {exc}"]

    if not isinstance(document, dict):
        return ["Document must be a YAML mapping"]

    return validate_crd(document)
