"""Tests for model routing."""

from __future__ import annotations

from model_gateway.router import ModelRouter


class TestModelRouter:
    def test_register_and_resolve(self):
        router = ModelRouter()
        router.register("gpt-4", "http://upstream:8080", "openai")
        route = router.resolve("gpt-4")
        assert route is not None
        assert route.upstream_url == "http://upstream:8080"
        assert route.provider == "openai"

    def test_resolve_unknown_returns_none(self):
        router = ModelRouter()
        assert router.resolve("nonexistent") is None

    def test_list_models(self):
        router = ModelRouter()
        router.register("model-a", "http://a", "prov-a")
        router.register("model-b", "http://b", "prov-b")
        models = router.list_models()
        assert len(models) == 2
        ids = {m.model_id for m in models}
        assert ids == {"model-a", "model-b"}

    def test_overwrite_registration(self):
        router = ModelRouter()
        router.register("m1", "http://old")
        router.register("m1", "http://new")
        assert router.resolve("m1").upstream_url == "http://new"
