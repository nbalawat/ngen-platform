FROM python:3.13-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock ./
COPY libs/ngen-common/ libs/ngen-common/
COPY libs/ngen-sdk/ libs/ngen-sdk/
COPY services/onboarding-agent/ services/onboarding-agent/

RUN uv sync --frozen --no-dev --package onboarding-agent

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
COPY services/onboarding-agent/src/ /app/src/
COPY libs/ngen-common/src/ /app/libs/ngen-common/src/
COPY libs/ngen-sdk/src/ /app/libs/ngen-sdk/src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8006

CMD ["uvicorn", "onboarding_agent.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8006"]
