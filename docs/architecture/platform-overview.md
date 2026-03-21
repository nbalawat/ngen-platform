# NGEN Platform Architecture

## Overview

NGEN is a multi-agent orchestration platform that provides a unified control plane
for building, deploying, and governing AI agent workflows across multiple frameworks.

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Portal UI (8080)                         │
├─────────────────────────────────────────────────────────────────┤
│                     API Gateway / Ingress                       │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Tenant   │ Model    │ Model    │ Workflow  │Governance│  MCP    │
│ Service  │ Registry │ Gateway  │ Engine   │ Service  │ Manager │
│ (8000)   │ (8001)   │ (8002)   │ (8003)   │ (8004)   │ (8005)  │
├──────────┴──────────┴──────────┴──────────┴──────────┴─────────┤
│ Onboarding Agent (8006)  │  Metering Service (8007)            │
├──────────────────────────┴─────────────────────────────────────┤
│                    NATS Event Bus (4222)                        │
├──────────┬──────────┬──────────────────────────────────────────┤
│PostgreSQL│  Redis   │  Mock LLM (9100)                         │
│ (5432)   │ (6379)   │                                          │
└──────────┴──────────┴──────────────────────────────────────────┘
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **Tenant Service** | 8000 | Multi-tenant org/team/project management (PostgreSQL) |
| **Model Registry** | 8001 | Model configuration CRUD with lifecycle events |
| **Model Gateway** | 8002 | LLM proxy with routing, rate limiting, cost tracking |
| **Workflow Engine** | 8003 | Multi-agent workflow orchestration + agent lifecycle |
| **Governance Service** | 8004 | Policy enforcement, budget tracking, audit events |
| **MCP Manager** | 8005 | MCP server registry + tool invocation via JSON-RPC |
| **Onboarding Agent** | 8006 | Guides new tenants through platform setup |
| **Metering Service** | 8007 | Usage aggregation from cost events |

## Cross-Cutting Concerns (ngen-common)

All services share these capabilities via the `ngen-common` library:

- **Auth Middleware** — JWT authentication with configurable mode (none/jwt/api_key)
- **Event Bus** — NATS pub/sub with InMemory fallback
- **Error Handlers** — Unified error response format
- **Observability** — Request metrics, logging, tracing

## Event-Driven Architecture

Services communicate via NATS subjects:

| Subject | Publisher | Subscribers |
|---------|-----------|-------------|
| `cost.recorded` | Model Gateway | Governance (budget), Metering |
| `cost.threshold_exceeded` | Governance | (alerting) |
| `lifecycle.model_*` | Model Registry | Model Gateway (auto-sync) |
| `lifecycle.server_*` | MCP Manager | — |
| `lifecycle.org/team/project_*` | Tenant Service | — |
| `lifecycle.agent_*` | Workflow Engine | — |
| `audit.workflow_*` | Workflow Engine | — |
| `audit.policy_evaluated` | Governance | — |

## Framework Adapters

The platform supports multiple agent frameworks via the adapter protocol:

- LangGraph
- Claude Agent SDK
- CrewAI
- Google ADK
- MS Agent Framework
- Default (built-in, no dependencies)

## Infrastructure

- **Docker Compose** — 12 containers for local development
- **Helm Charts** — Kubernetes deployment templates
- **Terraform** — AWS modules (EKS, RDS, ElastiCache)
- **ArgoCD** — GitOps continuous deployment
- **OPA** — Policy-as-code governance rules
