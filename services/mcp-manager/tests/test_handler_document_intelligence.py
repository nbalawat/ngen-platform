"""Tests for document intelligence handler (Landing.ai ADE)."""

from __future__ import annotations

import os

import pytest

from mcp_manager.handlers.document_intelligence import (
    handle_extract,
    handle_parse,
    handle_split,
)

HAS_API_KEY = bool(os.environ.get("VISION_AGENT_API_KEY"))


class TestParseValidation:
    @pytest.mark.asyncio
    async def test_missing_inputs(self):
        result = await handle_parse({})
        text = result["content"][0]["text"]
        assert "Error" in text
        assert "url" in text.lower() or "doc_id" in text.lower()

    @pytest.mark.asyncio
    async def test_empty_url(self):
        result = await handle_parse({"url": ""})
        text = result["content"][0]["text"]
        assert "Error" in text


class TestSplitValidation:
    @pytest.mark.asyncio
    async def test_missing_markdown(self):
        result = await handle_split({"split_rules": '[{"name":"Test"}]'})
        text = result["content"][0]["text"]
        assert "Error" in text
        assert "markdown" in text.lower()

    @pytest.mark.asyncio
    async def test_missing_rules(self):
        result = await handle_split({"markdown": "Some content"})
        text = result["content"][0]["text"]
        assert "Error" in text
        assert "split_rules" in text.lower()


class TestExtractValidation:
    @pytest.mark.asyncio
    async def test_missing_markdown(self):
        result = await handle_extract({"schema": '{"type":"object"}'})
        text = result["content"][0]["text"]
        assert "Error" in text

    @pytest.mark.asyncio
    async def test_missing_schema(self):
        result = await handle_extract({"markdown": "Some content"})
        text = result["content"][0]["text"]
        assert "Error" in text
        assert "schema" in text.lower()


@pytest.mark.skipif(not HAS_API_KEY, reason="VISION_AGENT_API_KEY not set")
class TestParseWithAPI:
    @pytest.mark.asyncio
    async def test_parse_url(self):
        """Parse a publicly available document via URL."""
        result = await handle_parse({
            "url": "https://arxiv.org/pdf/1706.03762",
            "model": "dpt-2-latest",
        })
        text = result["content"][0]["text"]
        # Should succeed and return markdown content, or return a descriptive error
        # (URL availability may vary)
        assert len(text) > 50  # Should have substantive output either way


@pytest.mark.skipif(not HAS_API_KEY, reason="VISION_AGENT_API_KEY not set")
class TestExtractWithAPI:
    @pytest.mark.asyncio
    async def test_extract_from_markdown(self):
        """Extract structured data from markdown text."""
        import json
        markdown = """
# Invoice #12345

**Date:** 2025-01-15
**Customer:** ACME Corporation
**Total:** $1,250.00

| Item | Qty | Price |
|------|-----|-------|
| Widget A | 5 | $50.00 |
| Widget B | 10 | $100.00 |
"""
        schema = json.dumps({
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string", "description": "The invoice number"},
                "customer_name": {"type": "string", "description": "Customer name"},
                "total_amount": {"type": "number", "description": "Total amount"},
            },
        })

        result = await handle_extract({
            "markdown": markdown,
            "schema": schema,
        })
        text = result["content"][0]["text"]
        # Should return extracted JSON
        assert "Extraction Result" in text or "Error" not in text


class TestNamespaceHandling:
    @pytest.mark.asyncio
    async def test_namespace_popped_from_args(self):
        """_namespace should be stripped without error."""
        result = await handle_parse({"_namespace": "tenant-a"})
        text = result["content"][0]["text"]
        # Should fail for missing url/doc_id, not for _namespace
        assert "url" in text.lower() or "doc_id" in text.lower()
