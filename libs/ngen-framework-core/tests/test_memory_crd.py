"""Tests for MemoryCRD parsing and validation."""

from __future__ import annotations

import pytest

from ngen_framework_core.crd import (
    MemoryCRD,
    MemoryPolicyCRD,
    MemorySpecCRD,
    MemoryTypeConfigCRD,
    parse_crd,
    _CRD_KIND_MAP,
)


# ---------------------------------------------------------------------------
# Minimal CRD
# ---------------------------------------------------------------------------


class TestMemoryCRDMinimal:
    def test_parse_minimal(self):
        data = {
            "apiVersion": "ngen.io/v1",
            "kind": "Memory",
            "metadata": {"name": "test-memory"},
            "spec": {},
        }
        crd = MemoryCRD.model_validate(data)
        assert crd.kind == "Memory"
        assert crd.api_version == "ngen.io/v1"
        assert crd.spec.context_budget_tokens == 4000
        assert crd.spec.default_backend == "redis"
        assert crd.spec.memory_types == []

    def test_parse_crd_recognizes_memory(self):
        data = {
            "apiVersion": "ngen.io/v1",
            "kind": "Memory",
            "metadata": {"name": "test"},
            "spec": {},
        }
        crd = parse_crd(data)
        assert isinstance(crd, MemoryCRD)


# ---------------------------------------------------------------------------
# Full CRD
# ---------------------------------------------------------------------------


class TestMemoryCRDFull:
    def test_parse_full(self):
        data = {
            "apiVersion": "ngen.io/v1",
            "kind": "Memory",
            "metadata": {
                "name": "support-bot-memory",
                "namespace": "acme-corp",
                "labels": {"env": "production"},
            },
            "spec": {
                "embeddingModel": "sentence-transformers/paraphrase-mpnet-base-v2",
                "contextBudgetTokens": 8000,
                "defaultBackend": "redis",
                "defaultPolicy": {
                    "ttlSeconds": 86400,
                    "summarizationThreshold": 50,
                },
                "memoryTypes": [
                    {
                        "type": "conversational",
                        "policy": {"ttlSeconds": 3600},
                    },
                    {
                        "type": "knowledge_base",
                        "backend": "pgvector",
                    },
                    {"type": "workflow"},
                    {"type": "tool_log", "policy": {"retentionDays": 30}},
                ],
            },
        }
        crd = MemoryCRD.model_validate(data)
        assert crd.spec.embedding_model == "sentence-transformers/paraphrase-mpnet-base-v2"
        assert crd.spec.context_budget_tokens == 8000
        assert len(crd.spec.memory_types) == 4
        assert crd.spec.default_policy.ttl_seconds == 86400
        assert crd.spec.default_policy.summarization_threshold == 50

        conv = crd.spec.memory_types[0]
        assert conv.type == "conversational"
        assert conv.policy.ttl_seconds == 3600

        kb = crd.spec.memory_types[1]
        assert kb.backend == "pgvector"

        tl = crd.spec.memory_types[3]
        assert tl.policy.retention_days == 30


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestMemoryCRDValidation:
    def test_bad_api_version(self):
        data = {
            "apiVersion": "ngen.io/v999",
            "kind": "Memory",
            "metadata": {"name": "test"},
            "spec": {},
        }
        with pytest.raises(Exception):
            MemoryCRD.model_validate(data)

    def test_wrong_kind(self):
        data = {
            "apiVersion": "ngen.io/v1",
            "kind": "Agent",
            "metadata": {"name": "test"},
            "spec": {},
        }
        with pytest.raises(Exception):
            MemoryCRD.model_validate(data)


# ---------------------------------------------------------------------------
# CRD registry
# ---------------------------------------------------------------------------


class TestCRDRegistration:
    def test_kind_map_contains_memory(self):
        assert "Memory" in _CRD_KIND_MAP
        assert _CRD_KIND_MAP["Memory"] is MemoryCRD


# ---------------------------------------------------------------------------
# Policy CRD model
# ---------------------------------------------------------------------------


class TestMemoryPolicyCRD:
    def test_defaults(self):
        p = MemoryPolicyCRD()
        assert p.max_entries is None
        assert p.ttl_seconds is None
        assert p.summarization_threshold is None
        assert p.retention_days is None

    def test_from_camel_case(self):
        p = MemoryPolicyCRD.model_validate(
            {"maxEntries": 100, "ttlSeconds": 3600}
        )
        assert p.max_entries == 100
        assert p.ttl_seconds == 3600
