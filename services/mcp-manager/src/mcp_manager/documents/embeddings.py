"""Embedding generation for document chunks.

Two implementations:
- LocalEmbeddingClient: deterministic hash-based vectors (no external API)
- GatewayEmbeddingClient: calls model-gateway /v1/embeddings endpoint
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        ...

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        ...


class LocalEmbeddingClient:
    """Deterministic hash-based embedding client.

    Generates consistent vectors from text using MD5 hashing.
    No external API needed — used for tests and as fallback.
    Produces vectors where semantically similar texts (sharing words)
    have higher cosine similarity.
    """

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    async def embed_single(self, text: str) -> list[float]:
        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> list[float]:
        """Generate a deterministic embedding from text.

        Uses word-level hashing to ensure texts sharing words
        have partially aligned vectors (higher cosine similarity).
        """
        vector = [0.0] * self._dimension
        words = text.lower().split()

        for word in words:
            # Hash each word to a set of dimensions
            h = hashlib.md5(word.encode()).hexdigest()
            for i in range(0, len(h), 2):
                dim = int(h[i:i + 2], 16) % self._dimension
                # Add contribution — same word always activates same dimensions
                value = (int(h[i:i + 2], 16) / 255.0) * 2 - 1  # [-1, 1]
                vector[dim] += value

        # Normalize to unit vector
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector


class GatewayEmbeddingClient:
    """Embedding client that calls model-gateway /v1/embeddings.

    Falls back to LocalEmbeddingClient if the gateway is unavailable.
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:8002",
        model: str = "text-embedding-3-small",
        batch_size: int = 20,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._model = model
        self._batch_size = batch_size
        self._fallback = LocalEmbeddingClient()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings, batching to avoid request limits."""
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            batch_result = await self._embed_batch(batch)
            all_embeddings.extend(batch_result)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call gateway for a batch. Falls back to local on failure."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._gateway_url}/v1/embeddings",
                    json={"model": self._model, "input": texts},
                    headers={"x-tenant-id": "default"},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # OpenAI-compatible response format
                    embeddings_data = data.get("data", [])
                    if embeddings_data:
                        # Sort by index to ensure correct ordering
                        sorted_data = sorted(embeddings_data, key=lambda x: x.get("index", 0))
                        return [item["embedding"] for item in sorted_data]

                logger.debug("Gateway returned %d, falling back to local", resp.status_code)
        except Exception as e:
            logger.debug("Gateway embedding failed, using local fallback: %s", e)

        return await self._fallback.embed(texts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
