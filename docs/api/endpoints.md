# NGEN Platform API Reference

## Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | When auth enabled | `Bearer <jwt-token>` |
| `x-tenant-id` | Gateway only | Tenant identifier for rate limiting |
| `Content-Type` | POST/PATCH | `application/json` |

## Health Check (All Services)

```
GET /health → {"status": "healthy"}
```

---

## Tenant Service (port 8000)

### Organizations
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/orgs` | Create organization |
| GET | `/api/v1/orgs` | List organizations |
| GET | `/api/v1/orgs/{id}` | Get organization |
| PATCH | `/api/v1/orgs/{id}` | Update organization |
| DELETE | `/api/v1/orgs/{id}` | Delete organization |

### Teams
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/orgs/{org_id}/teams` | Create team |
| GET | `/api/v1/orgs/{org_id}/teams` | List teams |
| DELETE | `/api/v1/orgs/{org_id}/teams/{id}` | Delete team |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/orgs/{org_id}/teams/{team_id}/projects` | Create project |
| GET | `/api/v1/orgs/{org_id}/teams/{team_id}/projects` | List projects |
| DELETE | `/api/v1/orgs/{org_id}/teams/{team_id}/projects/{id}` | Delete project |

---

## Model Registry (port 8001)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/models` | Register model |
| GET | `/api/v1/models` | List models (filter: `?provider=ANTHROPIC`) |
| GET | `/api/v1/models/{id}` | Get model by ID |
| GET | `/api/v1/models/by-name/{name}` | Get model by name |
| PATCH | `/api/v1/models/{id}` | Update model |
| DELETE | `/api/v1/models/{id}` | Delete model |

---

## Model Gateway (port 8002)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | OpenAI-compatible chat completion |
| POST | `/v1/messages` | Native Anthropic Messages API |
| GET | `/v1/models` | List available models |
| GET | `/v1/usage/{tenant_id}` | Get tenant usage stats |

---

## Workflow Engine (port 8003)

### Workflows
| Method | Path | Description |
|--------|------|-------------|
| POST | `/workflows/run` | Run workflow (blocking) |
| POST | `/workflows/run/stream` | Run workflow (SSE streaming) |
| GET | `/workflows/runs` | List runs (filter: `?status=completed`) |
| GET | `/workflows/runs/{id}` | Get run details |
| POST | `/workflows/runs/{id}/approve` | Approve HITL gate |
| DELETE | `/workflows/runs/{id}` | Cancel run |

### Agents
| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents` | Create standalone agent |
| GET | `/agents` | List agents |
| GET | `/agents/{name}` | Get agent info |
| POST | `/agents/{name}/invoke` | Invoke agent |
| DELETE | `/agents/{name}` | Delete agent |
| GET | `/agents/{name}/memory` | Get agent memory entries |
| GET | `/agents/{name}/memory/context` | Build context window |

---

## Governance Service (port 8004)

### Policies
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/policies` | Create policy |
| GET | `/api/v1/policies` | List policies |
| GET | `/api/v1/policies/{id}` | Get policy |
| PATCH | `/api/v1/policies/{id}` | Update policy |
| DELETE | `/api/v1/policies/{id}` | Delete policy |

### Evaluation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/evaluate` | Evaluate context against policies |

### Budgets
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/budgets` | List all tenant spend |
| GET | `/api/v1/budgets/{namespace}` | Get tenant spend |

---

## MCP Manager (port 8005)

### Servers
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/servers` | Register MCP server |
| GET | `/api/v1/servers` | List servers |
| GET | `/api/v1/servers/{id}` | Get server |
| PATCH | `/api/v1/servers/{id}` | Update server |
| DELETE | `/api/v1/servers/{id}` | Delete server |

### Tools
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/tools` | List tools |
| GET | `/api/v1/tools/search?q=` | Search tools |
| GET | `/api/v1/tools/{id}` | Get tool |
| POST | `/api/v1/invoke` | Invoke tool on MCP server |

---

## Onboarding Agent (port 8006)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/onboard` | Chat with onboarding agent |
| GET | `/api/v1/onboard/status` | Check platform setup status |
| GET | `/api/v1/onboard/steps` | Get onboarding checklist |

---

## Metering Service (port 8007)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/usage` | List all tenant usage |
| GET | `/api/v1/usage/{tenant_id}` | Get tenant usage (hourly/daily) |
| GET | `/api/v1/usage/summary` | Platform-wide usage summary |
