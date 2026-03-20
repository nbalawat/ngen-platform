FROM python:3.13-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

# Copy workspace root for dependency resolution
COPY pyproject.toml uv.lock ./
COPY libs/ngen-framework-core/ libs/ngen-framework-core/
COPY services/tenant-service/ services/tenant-service/

# Install dependencies
RUN uv sync --frozen --no-dev --package tenant-service

FROM base AS runtime

# Copy installed environment
COPY --from=builder /app/.venv /app/.venv
COPY services/tenant-service/src/ /app/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

CMD ["uvicorn", "tenant_service.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
