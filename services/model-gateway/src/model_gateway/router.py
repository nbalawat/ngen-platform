"""Model routing logic — resolves model name to upstream endpoint."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelRoute:
    model_id: str
    upstream_url: str
    provider: str = "mock"
    api_key: str = ""


class ModelRouter:
    """Routes model requests to the correct upstream provider."""

    def __init__(self) -> None:
        self._routes: dict[str, ModelRoute] = {}

    def register(
        self,
        model_id: str,
        upstream_url: str,
        provider: str = "mock",
        api_key: str = "",
    ) -> None:
        self._routes[model_id] = ModelRoute(
            model_id=model_id,
            upstream_url=upstream_url,
            provider=provider,
            api_key=api_key,
        )

    def unregister(self, model_id: str) -> bool:
        """Remove a model route. Returns True if it existed."""
        return self._routes.pop(model_id, None) is not None

    def resolve(self, model_id: str) -> ModelRoute | None:
        return self._routes.get(model_id)

    def list_models(self) -> list[ModelRoute]:
        return list(self._routes.values())
