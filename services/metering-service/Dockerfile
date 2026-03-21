FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-common/ libs/ngen-common/
COPY services/metering-service/ services/metering-service/

RUN uv sync --frozen --no-dev --package metering-service

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/metering-service/src/ /app/src/
COPY libs/ngen-common/src/ /app/libs/ngen-common/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8007

CMD ["uvicorn", "metering_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8007"]
