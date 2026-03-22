"""Tests for text chunker — sliding window."""

from __future__ import annotations

from mcp_manager.documents.chunker import chunk_text


class TestChunker:
    def test_short_text_single_chunk(self):
        text = "This is a short text."
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0].text == text.strip()
        assert chunks[0].chunk_index == 0

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_long_text_multiple_chunks(self):
        # Create text with 1000 words
        words = [f"word{i}" for i in range(1000)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) > 1
        # Each chunk should have roughly chunk_size words (except last)
        for c in chunks[:-1]:
            assert c.token_estimate >= 150  # at least chunk_size - overlap

    def test_overlap_between_chunks(self):
        words = [f"w{i}" for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        assert len(chunks) >= 2

        # Verify overlap: some words at the end of chunk 0 should appear at the start of chunk 1
        words_0 = set(chunks[0].text.split()[-10:])
        words_1 = set(chunks[1].text.split()[:10])
        overlap_words = words_0 & words_1
        assert len(overlap_words) > 0, "Chunks should overlap"

    def test_chunk_indices_are_sequential(self):
        words = [f"word{i}" for i in range(500)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_token_estimate(self):
        text = "one two three four five"
        chunks = chunk_text(text, chunk_size=100)
        assert chunks[0].token_estimate == 5

    def test_no_tiny_trailing_chunks(self):
        # With 110 words, chunk_size=100, overlap=50 — should not create a tiny 10-word trailing chunk
        words = [f"w{i}" for i in range(110)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, overlap=50)
        # Should be 1 or 2 chunks, not a tiny trailing one
        for chunk in chunks:
            assert chunk.token_estimate >= 10
