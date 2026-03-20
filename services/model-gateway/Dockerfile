FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-mock-llm/ libs/ngen-mock-llm/
COPY services/model-gateway/ services/model-gateway/

RUN uv sync --frozen --no-dev --package model-gateway

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/model-gateway/src/ /app/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8002

CMD ["uvicorn", "model_gateway.app:app", "--host", "0.0.0.0", "--port", "8002"]
