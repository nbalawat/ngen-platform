FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-common/ libs/ngen-common/
COPY services/governance-service/ services/governance-service/

RUN uv sync --frozen --no-dev --package governance-service

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/governance-service/src/ /app/src/
COPY libs/ngen-common/src/ /app/libs/ngen-common/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8004

CMD ["uvicorn", "governance_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8004"]
