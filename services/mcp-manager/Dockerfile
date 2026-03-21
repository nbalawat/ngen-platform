FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-common/ libs/ngen-common/
COPY services/mcp-manager/ services/mcp-manager/

RUN uv sync --frozen --no-dev --package mcp-manager

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/mcp-manager/src/ /app/src/
COPY libs/ngen-common/src/ /app/libs/ngen-common/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8005

CMD ["uvicorn", "mcp_manager.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8005"]
