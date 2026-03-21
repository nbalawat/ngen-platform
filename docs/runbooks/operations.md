# NGEN Platform Operations Runbook

## Service Health Checks

```bash
# Check all services
for port in 8000 8001 8002 8003 8004 8005 8006 8007; do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health)
  echo "Port $port: $status"
done

# Check NATS connections
curl -s http://localhost:8222/connz | python3 -m json.tool

# Check NATS subscriptions
curl -s http://localhost:8222/subsz | python3 -m json.tool
```

## Common Issues

### Service won't start

```bash
# Check logs
docker compose logs <service-name> --tail 50

# Common causes:
# 1. Missing NATS — check depends_on in docker-compose.yaml
# 2. Missing Python package — rebuild: docker compose build <service-name>
# 3. Port conflict — check: lsof -i :<port>
```

### NATS not delivering events

```bash
# Verify connections
curl -s http://localhost:8222/connz | jq '.num_connections'

# Verify subscriptions exist
curl -s http://localhost:8222/subsz | jq '.num_subscriptions'

# Check service logs for event bus errors
docker compose logs governance-service --tail 20 | grep -i "event\|nats\|bus"
```

### Rate limiting too aggressive

```bash
# Check current rate limit headers
curl -v -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: debug" \
  -d '{"model":"mock-model","messages":[{"role":"user","content":"test"}]}' \
  2>&1 | grep -i ratelimit
```

### Budget threshold alerts

```bash
# Check current spend for a tenant
curl -s http://localhost:8004/api/v1/budgets/default | python3 -m json.tool

# Check metering data
curl -s http://localhost:8007/api/v1/usage/default | python3 -m json.tool

# Platform-wide summary
curl -s http://localhost:8007/api/v1/usage/summary | python3 -m json.tool
```

## Scaling

### Docker Compose (dev)

```bash
# Scale a service
docker compose up -d --scale model-gateway=3

# Note: requires load balancer configuration for multiple instances
```

### Kubernetes (production)

```bash
# Scale via kubectl
kubectl -n ngen scale deployment model-gateway --replicas=5

# Or update Helm values
helm upgrade model-gateway infrastructure/helm/charts/model-gateway \
  --set replicaCount=5
```

## Database Operations

### PostgreSQL (Tenant Service)

```bash
# Connect to database
docker exec -it ngen-postgres psql -U ngen -d ngen

# Check table sizes
\dt+

# Run migrations
cd services/tenant-service
uv run alembic upgrade head
```

### Redis (Rate Limiting + Policy Persistence)

```bash
# Connect to Redis
docker exec -it ngen-redis redis-cli

# Check rate limit keys
KEYS ngen:ratelimit:*

# Check policy storage
HGETALL ngen:policies

# Flush rate limit data (emergency)
DEL ngen:ratelimit:rpm:*
```

## Monitoring

### Metrics

All services expose metrics at `/metrics` (when observability is enabled).

### Key metrics to watch:
- Request latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- NATS message throughput
- Redis connection pool utilization
- PostgreSQL connection count

## Disaster Recovery

### Backup

```bash
# PostgreSQL
docker exec ngen-postgres pg_dump -U ngen ngen > backup.sql

# Redis
docker exec ngen-redis redis-cli BGSAVE
docker cp ngen-redis:/data/dump.rdb ./redis-backup.rdb
```

### Restore

```bash
# PostgreSQL
docker exec -i ngen-postgres psql -U ngen ngen < backup.sql

# Redis
docker cp ./redis-backup.rdb ngen-redis:/data/dump.rdb
docker restart ngen-redis
```
