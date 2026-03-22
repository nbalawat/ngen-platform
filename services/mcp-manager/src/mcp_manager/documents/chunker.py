"""Text chunking — sliding window for document passages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextChunk:
    """A chunk of text from a document."""

    chunk_index: int
    text: str
    start_char: int
    end_char: int
    token_estimate: int


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[TextChunk]:
    """Split text into overlapping chunks by word count.

    Args:
        text: Full document text.
        chunk_size: Target words per chunk.
        overlap: Words of overlap between adjacent chunks.

    Returns:
        List of TextChunk with position metadata.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    # If text fits in one chunk, return it directly
    if len(words) <= chunk_size:
        return [TextChunk(
            chunk_index=0,
            text=text.strip(),
            start_char=0,
            end_char=len(text),
            token_estimate=len(words),
        )]

    chunks: list[TextChunk] = []
    step = max(chunk_size - overlap, 1)
    chunk_idx = 0
    i = 0

    while i < len(words):
        end = min(i + chunk_size, len(words))
        chunk_words = words[i:end]
        chunk_text_str = " ".join(chunk_words)

        # Calculate character positions in original text
        # This is approximate — good enough for retrieval
        start_char = text.find(chunk_words[0], sum(len(w) + 1 for w in words[:i])) if i > 0 else 0
        if start_char < 0:
            start_char = 0
        end_char = min(start_char + len(chunk_text_str), len(text))

        chunks.append(TextChunk(
            chunk_index=chunk_idx,
            text=chunk_text_str,
            start_char=start_char,
            end_char=end_char,
            token_estimate=len(chunk_words),
        ))

        chunk_idx += 1
        i += step

        # Don't create tiny trailing chunks
        if i < len(words) and len(words) - i < overlap:
            break

    return chunks
