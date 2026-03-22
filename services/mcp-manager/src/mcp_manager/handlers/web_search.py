"""Web search handler — real web search via DuckDuckGo.

Provides two tools:
- search: Search the web for information
- fetch_page: Fetch and extract text from a URL
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _mcp_text(text: str) -> dict[str, Any]:
    """Wrap text in MCP content format."""
    return {"content": [{"type": "text", "text": text}]}


def _mcp_error(message: str) -> dict[str, Any]:
    """Return an error in MCP content format."""
    return {"content": [{"type": "text", "text": f"Error: {message}"}]}


def _strip_html(raw_html: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def handle_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the web using DuckDuckGo."""
    arguments.pop("_namespace", None)  # Not used by web search
    query = arguments.get("query", "").strip()
    if not query:
        return _mcp_error("Missing required parameter: query")

    max_results = min(int(arguments.get("max_results", 5)), 10)

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return _mcp_text(f"No results found for: {query}")

        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", r.get("snippet", "")),
            })

        output = f"Found {len(formatted)} results for \"{query}\":\n\n"
        for i, r in enumerate(formatted, 1):
            output += f"{i}. **{r['title']}**\n"
            output += f"   {r['url']}\n"
            output += f"   {r['snippet']}\n\n"

        return _mcp_text(output)

    except ImportError:
        return _mcp_error(
            "duckduckgo-search package not installed. "
            "Install with: pip install duckduckgo-search"
        )
    except Exception as e:
        logger.warning("Web search failed for query '%s': %s", query, e)
        return _mcp_error(f"Search failed: {e}")


async def handle_fetch_page(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch and extract text content from a URL."""
    arguments.pop("_namespace", None)  # Not used by fetch
    url = arguments.get("url", "").strip()
    if not url:
        return _mcp_error("Missing required parameter: url")

    if not url.startswith(("http://", "https://")):
        return _mcp_error(f"Invalid URL: {url}. Must start with http:// or https://")

    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True
        ) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "NGEN-Platform/1.0 (Tool Fetch)"},
            )
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            text = _strip_html(resp.text)
        else:
            text = resp.text

        # Truncate to reasonable size
        if len(text) > 4000:
            text = text[:4000] + "\n\n[Content truncated at 4000 characters]"

        return _mcp_text(f"Content from {url}:\n\n{text}")

    except httpx.HTTPStatusError as e:
        return _mcp_error(f"HTTP {e.response.status_code} from {url}")
    except httpx.ConnectError:
        return _mcp_error(f"Could not connect to {url}")
    except httpx.TimeoutException:
        return _mcp_error(f"Timeout fetching {url}")
    except Exception as e:
        return _mcp_error(f"Failed to fetch {url}: {e}")
