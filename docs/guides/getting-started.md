# Getting Started with NGEN Platform

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/) package manager

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/your-org/next-gen-multi-agentic-platform.git
cd next-gen-multi-agentic-platform
uv sync --extra dev
```

### 2. Start Infrastructure

```bash
cd infrastructure/docker-compose
docker compose up -d
```

This starts 12 containers: PostgreSQL, Redis, NATS, Mock LLM, and 8 application services.

### 3. Verify Services

```bash
for port in 8000 8001 8002 8003 8004 8005 8006 8007; do
  echo "Port $port: $(curl -s http://localhost:$port/health)"
done
```

### 4. Run Your First Workflow

```bash
curl -X POST http://localhost:8003/workflows/run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_yaml": "apiVersion: ngen.io/v1\nkind: Workflow\nmetadata:\n  name: hello-world\nspec:\n  topology: sequential\n  agents:\n  - ref: greeter\n",
    "input_data": {"message": "Hello from NGEN!"}
  }'
```

### 5. Create a Standalone Agent

```bash
# Create
curl -X POST http://localhost:8003/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "framework": "default", "description": "My first agent"}'

# Invoke
curl -X POST http://localhost:8003/agents/my-agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What can you do?"}]}'

# Check memory
curl http://localhost:8003/agents/my-agent/memory?memory_type=conversational
```

### 6. Set Up Governance

```bash
# Create a content filter policy
curl -X POST http://localhost:8004/api/v1/policies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "content-filter",
    "policy_type": "content_filter",
    "action": "block",
    "rules": {"blocked_patterns": ["\\b(password|secret)\\b"]}
  }'

# Create a cost limit policy
curl -X POST http://localhost:8004/api/v1/policies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daily-budget",
    "policy_type": "cost_limit",
    "action": "warn",
    "rules": {"daily_budget": 100.0, "alert_threshold": 0.8}
  }'
```

## Running Tests

```bash
# Unit tests (no Docker required)
uv run pytest services/ libs/ --tb=short

# Integration tests (Docker required)
uv run pytest tests/integration/ -v

# Load tests (requires locust)
pip install locust
locust -f tests/load/locustfile.py --host http://localhost
```

## Enabling Authentication

Set the `AUTH_JWT_SECRET` environment variable on any service to enable JWT auth:

```bash
# In docker-compose.yaml, add to service environment:
AUTH_JWT_SECRET: your-secret-key-here
```

Without `AUTH_JWT_SECRET`, all services run in dev mode (no auth required).

## Architecture

See [Platform Architecture](../architecture/platform-overview.md) for the full system design.
