"""Tests for web search handler — real DuckDuckGo search."""

from __future__ import annotations

import pytest

from mcp_manager.handlers.web_search import handle_fetch_page, handle_search


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Real web search should return results."""
        result = await handle_search({"query": "Python programming language"})
        text = result["content"][0]["text"]
        # Should have found something
        assert "Found" in text
        assert "Python" in text or "python" in text

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self):
        result = await handle_search({"query": "machine learning", "max_results": 2})
        text = result["content"][0]["text"]
        # Count numbered results
        lines = [l for l in text.split("\n") if l.strip().startswith("3.")]
        assert len(lines) == 0  # should be at most 2 results

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_error(self):
        result = await handle_search({})
        text = result["content"][0]["text"]
        assert "Error" in text

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_error(self):
        result = await handle_search({"query": ""})
        text = result["content"][0]["text"]
        assert "Error" in text


class TestFetchPage:
    @pytest.mark.asyncio
    async def test_fetch_returns_text(self):
        """Fetch a known stable URL."""
        result = await handle_fetch_page({"url": "https://httpbin.org/html"})
        text = result["content"][0]["text"]
        assert "Content from" in text
        assert len(text) > 50

    @pytest.mark.asyncio
    async def test_fetch_invalid_url_returns_error(self):
        result = await handle_fetch_page({"url": "not-a-url"})
        text = result["content"][0]["text"]
        assert "Error" in text

    @pytest.mark.asyncio
    async def test_fetch_missing_url_returns_error(self):
        result = await handle_fetch_page({})
        text = result["content"][0]["text"]
        assert "Error" in text

    @pytest.mark.asyncio
    async def test_fetch_unreachable_host_returns_error(self):
        result = await handle_fetch_page({"url": "http://192.0.2.1:9999/test"})
        text = result["content"][0]["text"]
        assert "Error" in text
