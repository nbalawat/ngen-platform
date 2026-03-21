FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-common/ libs/ngen-common/
COPY libs/ngen-framework-core/ libs/ngen-framework-core/
COPY services/workflow-engine/ services/workflow-engine/

RUN uv sync --frozen --no-dev --package workflow-engine

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/workflow-engine/src/ /app/src/
COPY libs/ngen-common/src/ /app/libs/ngen-common/src/
COPY libs/ngen-framework-core/src/ /app/libs/ngen-framework-core/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8003

CMD ["uvicorn", "workflow_engine.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8003"]
