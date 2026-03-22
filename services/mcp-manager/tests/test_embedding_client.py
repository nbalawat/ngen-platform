"""Tests for embedding client — uses real LocalEmbeddingClient."""

from __future__ import annotations

import pytest

from mcp_manager.documents.embeddings import LocalEmbeddingClient, cosine_similarity


@pytest.fixture()
def client():
    return LocalEmbeddingClient(dimension=256)


class TestLocalEmbeddingClient:
    @pytest.mark.asyncio
    async def test_consistent_vectors(self, client):
        """Same input always produces the same vector."""
        v1 = await client.embed_single("hello world")
        v2 = await client.embed_single("hello world")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_inputs_different_vectors(self, client):
        v1 = await client.embed_single("machine learning algorithms")
        v2 = await client.embed_single("cooking pasta recipes")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_batch_embedding(self, client):
        texts = ["hello", "world", "test"]
        results = await client.embed(texts)
        assert len(results) == 3
        assert all(len(v) == 256 for v in results)

    @pytest.mark.asyncio
    async def test_unit_vectors(self, client):
        """Vectors should be normalized to unit length."""
        import math
        v = await client.embed_single("some text here")
        magnitude = math.sqrt(sum(x * x for x in v))
        assert abs(magnitude - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_similar_texts_higher_cosine(self, client):
        """Texts sharing words should have higher cosine similarity than unrelated texts."""
        v_ml = await client.embed_single("machine learning deep neural networks")
        v_ai = await client.embed_single("deep learning neural network architectures")
        v_cook = await client.embed_single("baking chocolate cake recipe oven")

        sim_related = cosine_similarity(v_ml, v_ai)
        sim_unrelated = cosine_similarity(v_ml, v_cook)

        assert sim_related > sim_unrelated, (
            f"Related texts similarity ({sim_related:.3f}) should be > "
            f"unrelated ({sim_unrelated:.3f})"
        )

    @pytest.mark.asyncio
    async def test_empty_text(self, client):
        """Empty text should produce a valid vector."""
        v = await client.embed_single("")
        assert len(v) == 256


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(v1, v2)) < 0.001

    def test_opposite_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        assert abs(cosine_similarity(v1, v2) - (-1.0)) < 0.001
