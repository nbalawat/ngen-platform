FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY services/model-registry/ services/model-registry/

RUN uv sync --frozen --no-dev --package model-registry

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/model-registry/src/ /app/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8001

CMD ["uvicorn", "model_registry.app:app", "--host", "0.0.0.0", "--port", "8001"]
