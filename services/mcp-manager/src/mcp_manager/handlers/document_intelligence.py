"""Document intelligence handler — Landing.ai ADE integration.

Provides three tools powered by Landing.ai's Agentic Document Extraction:
- parse_document: Parse documents into structured markdown with chunk metadata
- split_document: Split multi-document files into classified sub-documents
- extract_data: Extract structured data from documents using JSON schemas

Requires VISION_AGENT_API_KEY environment variable to be set.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_API_KEY_ENV = "VISION_AGENT_API_KEY"


def _mcp_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _mcp_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {message}"}]}


def _get_client():
    """Get Landing.ai ADE client. Returns None if not configured."""
    api_key = os.environ.get(_API_KEY_ENV)
    if not api_key:
        return None

    try:
        from landingai_ade import LandingAIADE
        return LandingAIADE()
    except ImportError:
        logger.error("landingai-ade package not installed")
        return None
    except Exception as e:
        logger.error("Failed to initialize ADE client: %s", e)
        return None


async def handle_parse(arguments: dict[str, Any]) -> dict[str, Any]:
    """Parse a document into structured markdown.

    Accepts either a URL or raw file content from the knowledge base.
    """
    arguments.pop("_namespace", None)

    url = arguments.get("url", "").strip()
    doc_id = arguments.get("doc_id", "").strip()
    model = arguments.get("model", "dpt-2-latest")

    if not url and not doc_id:
        return _mcp_error(
            "Missing required parameter: provide 'url' (document URL) "
            "or 'doc_id' (ID of a document in the knowledge base)"
        )

    client = _get_client()
    if client is None:
        return _mcp_error(
            f"Document intelligence not configured. "
            f"Set the {_API_KEY_ENV} environment variable."
        )

    try:
        if url:
            response = client.parse(document_url=url, model=model)
        elif doc_id:
            # Load from knowledge base document store
            # For now, return an error — full KB integration requires
            # access to the DocumentStore which is on app.state
            return _mcp_error(
                "Parsing by doc_id is not yet supported. "
                "Please provide a 'url' parameter instead."
            )
        else:
            return _mcp_error("No document source provided")

        # Format output
        chunk_count = len(response.chunks) if hasattr(response, 'chunks') and response.chunks else 0
        markdown = response.markdown if hasattr(response, 'markdown') else ""

        output = f"## Document Parse Result\n\n"
        output += f"**Chunks:** {chunk_count}\n"
        output += f"**Model:** {model}\n\n"

        if markdown:
            # Truncate if very long
            if len(markdown) > 8000:
                output += markdown[:8000]
                output += f"\n\n[Content truncated — {len(markdown)} total characters]"
            else:
                output += markdown

        # Add chunk metadata summary
        if hasattr(response, 'chunks') and response.chunks:
            output += f"\n\n---\n### Chunk Summary\n"
            for i, chunk in enumerate(response.chunks[:20]):
                chunk_type = getattr(chunk, 'type', 'unknown')
                chunk_text = getattr(chunk, 'markdown', '')[:100]
                output += f"- Chunk {i}: [{chunk_type}] {chunk_text}...\n"
            if chunk_count > 20:
                output += f"- ... and {chunk_count - 20} more chunks\n"

        return _mcp_text(output)

    except Exception as e:
        logger.error("ADE parse failed: %s", e)
        return _mcp_error(f"Document parsing failed: {e}")


async def handle_split(arguments: dict[str, Any]) -> dict[str, Any]:
    """Split a multi-document file into classified sub-documents.

    Requires parsed markdown and split rules (classification categories).
    """
    arguments.pop("_namespace", None)

    markdown = arguments.get("markdown", "").strip()
    split_rules = arguments.get("split_rules", "")
    model = arguments.get("model", "split-latest")

    if not markdown:
        return _mcp_error("Missing required parameter: 'markdown' (parsed document text)")

    if not split_rules:
        return _mcp_error(
            "Missing required parameter: 'split_rules' — a JSON array of "
            "classification categories, e.g. "
            '[{"name": "Invoice", "description": "A payment request document"}]'
        )

    client = _get_client()
    if client is None:
        return _mcp_error(
            f"Document intelligence not configured. "
            f"Set the {_API_KEY_ENV} environment variable."
        )

    try:
        # Parse split_rules if it's a string
        if isinstance(split_rules, str):
            rules_json = split_rules
        else:
            rules_json = json.dumps(split_rules)

        response = client.split(
            split_class=rules_json,
            markdown=markdown,
            model=model,
        )

        # Format output
        splits = response.splits if hasattr(response, 'splits') and response.splits else []

        output = f"## Document Split Result\n\n"
        output += f"**Sub-documents found:** {len(splits)}\n"
        output += f"**Model:** {model}\n\n"

        for i, split in enumerate(splits):
            classification = getattr(split, 'classification', 'Unknown')
            identifier = getattr(split, 'identifier', None)
            pages = getattr(split, 'pages', [])

            output += f"### {i + 1}. {classification}\n"
            if identifier:
                output += f"**Identifier:** {identifier}\n"
            if pages:
                output += f"**Pages:** {pages}\n"

            # Include first bit of markdown content
            markdowns = getattr(split, 'markdowns', [])
            if markdowns and markdowns[0]:
                preview = markdowns[0][:500]
                output += f"\n{preview}\n"
                if len(markdowns[0]) > 500:
                    output += "...\n"
            output += "\n"

        return _mcp_text(output)

    except Exception as e:
        logger.error("ADE split failed: %s", e)
        return _mcp_error(f"Document splitting failed: {e}")


async def handle_extract(arguments: dict[str, Any]) -> dict[str, Any]:
    """Extract structured data from a document using a JSON schema.

    The schema defines what fields to extract (names, types, descriptions).
    """
    arguments.pop("_namespace", None)

    markdown = arguments.get("markdown", "").strip()
    schema = arguments.get("schema", "")
    model = arguments.get("model", "extract-latest")

    if not markdown:
        return _mcp_error("Missing required parameter: 'markdown' (parsed document text)")

    if not schema:
        return _mcp_error(
            "Missing required parameter: 'schema' — a JSON schema defining "
            "the fields to extract, e.g. "
            '{"type": "object", "properties": {"name": {"type": "string", "description": "Person name"}}}'
        )

    client = _get_client()
    if client is None:
        return _mcp_error(
            f"Document intelligence not configured. "
            f"Set the {_API_KEY_ENV} environment variable."
        )

    try:
        # Parse schema if it's a dict
        if isinstance(schema, dict):
            schema_json = json.dumps(schema)
        else:
            schema_json = schema

        response = client.extract(
            schema=schema_json,
            markdown=markdown,
            model=model,
        )

        # Format output
        extraction = getattr(response, 'extraction', {})
        metadata = getattr(response, 'extraction_metadata', {})

        output = f"## Data Extraction Result\n\n"
        output += f"**Model:** {model}\n\n"
        output += "### Extracted Data\n\n"
        output += "```json\n"
        output += json.dumps(extraction, indent=2, default=str)
        output += "\n```\n"

        if metadata:
            output += "\n### Extraction Metadata\n\n"
            output += "```json\n"
            output += json.dumps(metadata, indent=2, default=str)
            output += "\n```\n"

        return _mcp_text(output)

    except Exception as e:
        logger.error("ADE extract failed: %s", e)
        return _mcp_error(f"Data extraction failed: {e}")
