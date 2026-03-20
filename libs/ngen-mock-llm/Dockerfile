FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-mock-llm/ libs/ngen-mock-llm/

RUN uv sync --frozen --no-dev --package ngen-mock-llm

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY libs/ngen-mock-llm/src/ /app/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 9100

CMD ["uvicorn", "ngen_mock_llm.server:create_mock_llm_app", "--factory", "--host", "0.0.0.0", "--port", "9100"]
