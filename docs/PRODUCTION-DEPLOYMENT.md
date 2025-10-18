# Production Deployment Guide

## Overview

This guide covers end-to-end production deployment of RecoveryOS API with:
- **Database**: Digital Ocean Managed PostgreSQL
- **Secrets Management**: File-based (.env.prod)
- **Migrations**: One-shot migration job before API startup
- **Observability**: JSON logs + OpenTelemetry traces to Grafana Cloud
- **Monitoring**: Digital Ocean Managed Postgres alerts + Grafana Cloud traces

## Prerequisites

### Required Services

1. **Digital Ocean Account** with:
   - Managed PostgreSQL database provisioned
   - Container registry or use GitHub Container Registry (GHCR)
   - Droplet or App Platform for hosting (optional)

2. **Grafana Cloud Account**:
   - Free tier available at https://grafana.com/products/cloud/
   - OpenTelemetry endpoint configured
   - API token generated for trace ingestion

3. **GitHub Account** (for CI/CD and container registry)

### Local Requirements

- Docker and Docker Compose
- Git
- Access to production secrets

## Database Setup (Digital Ocean Managed Postgres)

### 1. Provision Database

1. Log into Digital Ocean Console
2. Navigate to **Databases** → **Create Database**
3. Select configuration:
   - **Database Engine**: PostgreSQL 16
   - **Plan**: Choose based on your needs (Starter: $15/mo, Basic: $60/mo)
   - **Region**: Select closest to your application
   - **Database Name**: `recoveryos`

4. Note connection details:
   - **Host**: `db-postgresql-nyc1-xxxxx-do-user-xxxxx-0.b.db.ondigitalocean.com`
   - **Port**: `25060`
   - **Username**: `doadmin`
   - **Password**: (provided by Digital Ocean)
   - **Database**: `recoveryos`
   - **SSL Mode**: `require`

### 2. Configure Database Alerts

In Digital Ocean Console → Databases → Alerts, enable:

**Connection Alerts**:
- Alert when connection count > 80% of max connections
- Notification channels: Email/Slack

**CPU Alerts**:
- Alert when CPU usage > 80% for 5 minutes
- Notification channels: Email/Slack

**Latency Alerts**:
- Alert when query latency p95 > 100ms for 5 minutes
- Notification channels: Email/Slack

### 3. Monitor Database Insights

Regularly check **Insights** tab for:
- Slowest queries (optimize queries > 1s)
- Connection pool saturation (scale up if consistently high)
- Query patterns (identify N+1 queries)

### 4. Connection String Format

```
postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE?sslmode=require
```

Example:
```
postgresql://doadmin:SECURE_PASSWORD@db-postgresql-nyc1-12345-do-user-12345-0.b.db.ondigitalocean.com:25060/recoveryos?sslmode=require
```

## Secrets Management

### Production Secrets File

Create `.env.prod` in repository root (NEVER commit this file):

```bash
# Copy from template
cp .env.prod.template .env.prod

# Edit with actual values
nano .env.prod
```

Required secrets:

```bash
# Database (from Digital Ocean)
DATABASE_URL=postgresql://doadmin:PASSWORD@HOST:PORT/recoveryos?sslmode=require

# OpenTelemetry (from Grafana Cloud)
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic BASE64_ENCODED_CREDENTIALS

# Application
APP_ENV=production
APP_VERSION=1.0.0
STRICT_STARTUP=true
```

### Grafana Cloud Setup

1. Log into Grafana Cloud Console
2. Navigate to **Connections** → **Add new connection** → **OpenTelemetry**
3. Generate credentials:
   - **Instance ID**: Your Grafana Cloud instance
   - **API Token**: Generate new token with "MetricsPublisher" role
   - **Endpoint**: Copy OTLP endpoint URL

4. Create base64-encoded header:
```bash
echo -n "INSTANCE_ID:API_TOKEN" | base64
```

5. Add to `.env.prod`:
```
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <BASE64_OUTPUT>
```

## Migration Strategy

### One-Shot Migration Job

The migration job runs **before** the API starts to ensure schema is up-to-date.

#### Build Migration Container

```bash
docker build -f Dockerfile.migrate -t ghcr.io/greta-47/my-first-repo-migrate:latest .
docker push ghcr.io/greta-47/my-first-repo-migrate:latest
```

#### Run Locally (Testing)

```bash
# With local postgres
docker run --rm \
  --env-file .env.prod \
  -e DATABASE_URL=postgresql://recoveryos:changeme@host.docker.internal:5432/recoveryos \
  ghcr.io/greta-47/my-first-repo-migrate:latest
```

#### Run in Production

**Option 1: Docker Compose** (simplest for VM deployment)

```bash
# Runs migration job first, then API
docker compose -f docker-compose.prod.yml up -d
```

**Option 2: Kubernetes Job** (for K8s deployments)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: recoveryos-migrate-001
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migrate
        image: ghcr.io/greta-47/my-first-repo-migrate:latest
        envFrom:
        - secretRef:
            name: recoveryos-prod-secrets
  backoffLimit: 3
```

**Option 3: Manual Execution** (for debugging)

```bash
# Connect to application server
ssh user@production-server

# Run migration
docker run --rm \
  --env-file /opt/recoveryos/.env.prod \
  ghcr.io/greta-47/my-first-repo-migrate:latest
```

### Migration Safety Practices

1. **Always test migrations in staging first**
   ```bash
   # Create staging database
   DATABASE_URL=<staging-url> docker run ghcr.io/.../migrate:latest
   ```

2. **Backup before migrations**
   ```bash
   # Digital Ocean automatic backups are enabled by default
   # Or create manual snapshot in DO Console → Databases → Backups
   ```

3. **Monitor migration execution**
   ```bash
   # View migration logs
   docker logs <container-id> -f
   ```

4. **Rollback strategy**
   ```bash
   # Downgrade to previous migration
   alembic downgrade -1
   ```

## Deployment Process

### Step 1: Build and Push Containers

```bash
# Build API container
docker build -t ghcr.io/greta-47/my-first-repo:v1.0.0 .
docker push ghcr.io/greta-47/my-first-repo:v1.0.0

# Build migration container
docker build -f Dockerfile.migrate -t ghcr.io/greta-47/my-first-repo-migrate:v1.0.0 .
docker push ghcr.io/greta-47/my-first-repo-migrate:v1.0.0
```

### Step 2: Deploy with Docker Compose

```bash
# On production server
cd /opt/recoveryos

# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Stop existing services
docker compose -f docker-compose.prod.yml down

# Start services (migration runs first automatically)
docker compose -f docker-compose.prod.yml up -d

# Verify API health
curl http://localhost:8000/healthz
```

### Step 3: Verify Deployment

```bash
# Check API logs
docker compose -f docker-compose.prod.yml logs api -f

# Check migration logs
docker compose -f docker-compose.prod.yml logs migrate

# Test endpoints
curl http://localhost:8000/readyz
curl http://localhost:8000/metrics
curl http://localhost:8000/version
```

## Observability Setup

### JSON Structured Logging

Logs are already formatted as JSON. View logs:

```bash
# View recent logs
docker compose logs api --tail=100

# Stream logs
docker compose logs api -f

# Filter by level
docker compose logs api | jq 'select(.level=="ERROR")'
```

### OpenTelemetry Traces (Grafana Cloud)

#### Verify Trace Export

1. Make test requests to your API:
```bash
curl -X POST http://localhost:8000/check-in \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "adherence": 80,
    "mood_trend": 5,
    "cravings": 20,
    "sleep_hours": 7.5,
    "isolation": 15
  }'
```

2. View traces in Grafana Cloud:
   - Navigate to **Explore** → **Tempo** (traces data source)
   - Search for service: `recoveryos-api`
   - View trace spans for request flow

#### Trace Configuration

Traces capture:
- HTTP request/response (method, path, status code)
- Database queries (via SQLAlchemy instrumentation)
- Request duration and latency
- Error traces (when exceptions occur)

Sampling rate controlled by:
```bash
TRACES_SAMPLE_RATE=0.05  # 5% of requests (adjust as needed)
```

### Monitoring Dashboard (Grafana Cloud)

Create dashboard with panels:

1. **API Request Rate**
   - Query: `rate(http_server_requests_total{service="recoveryos-api"}[5m])`

2. **API Latency (p95)**
   - Query: `histogram_quantile(0.95, http_server_duration_bucket{service="recoveryos-api"})`

3. **Error Rate**
   - Query: `rate(http_server_requests_total{service="recoveryos-api",status=~"5.."}[5m])`

4. **Database Connection Pool**
   - Monitor via `/metrics` endpoint: `app_checkins_total`, `app_consents_total`

5. **Trace Visualization**
   - Use **Service Map** to visualize API → Database flow

### Alerting Rules

Configure in Grafana Cloud:

```yaml
# High Error Rate
- alert: HighErrorRate
  expr: rate(http_server_requests_total{service="recoveryos-api",status=~"5.."}[5m]) > 0.05
  for: 5m
  annotations:
    summary: "API error rate is high (>5%)"

# High Latency
- alert: HighLatency
  expr: histogram_quantile(0.95, http_server_duration_bucket{service="recoveryos-api"}) > 1000
  for: 5m
  annotations:
    summary: "API p95 latency is high (>1s)"

# Service Down
- alert: ServiceDown
  expr: up{service="recoveryos-api"} == 0
  for: 1m
  annotations:
    summary: "API service is down"
```

## Health Checks and Monitoring

### Endpoint Health Checks

```bash
# Liveness probe (simple status)
curl http://localhost:8000/healthz
# Response: "ok"

# Readiness probe (includes uptime)
curl http://localhost:8000/readyz
# Response: {"ok": true, "uptime_s": 3600}

# Metrics (Prometheus format)
curl http://localhost:8000/metrics
# Response:
# app_uptime_seconds 3600
# app_checkins_total 150
# app_consents_total 42
```

### Digital Ocean Monitoring

Enable monitoring in DO Console:

1. **App Platform Monitoring** (if using App Platform):
   - Navigate to App → Insights
   - View CPU, memory, request metrics

2. **Droplet Monitoring** (if using Droplet):
   - Navigate to Droplet → Graphs
   - View system metrics

3. **Database Monitoring**:
   - Navigate to Database → Metrics
   - View connection count, CPU, disk usage

## Troubleshooting

### Migration Failures

**Issue**: Migration job fails with "connection refused"

**Solution**:
```bash
# Verify DATABASE_URL is correct
docker run --rm --env-file .env.prod alpine sh -c 'echo $DATABASE_URL'

# Test database connectivity
docker run --rm --env-file .env.prod python:3.12-slim python -c "
from sqlalchemy import create_engine
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as c:
    print('Connected successfully')
"
```

### OpenTelemetry Not Working

**Issue**: No traces appearing in Grafana Cloud

**Solution**:
```bash
# Check OTEL configuration in logs
docker compose logs api | grep opentelemetry

# Expected output:
# {"level":"INFO","msg":"opentelemetry_enabled ...",\"endpoint\":\"https://...\"}

# Verify environment variables
docker exec <api-container> env | grep OTEL

# Test endpoint connectivity
curl -v https://otlp-gateway-prod-us-central-0.grafana.net/otlp
```

### High Database Connection Count

**Issue**: Digital Ocean alerts for connection saturation

**Solution**:
```bash
# Scale down connection pool in .env.prod
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Restart API
docker compose -f docker-compose.prod.yml restart api

# Monitor connections
# In Digital Ocean Console → Database → Metrics
```

### API Not Starting

**Issue**: API container exits immediately

**Solution**:
```bash
# Check logs for startup errors
docker compose logs api

# Common issues:
# 1. DATABASE_URL incorrect → verify connection string
# 2. STRICT_STARTUP=true with unreachable DB → check database status
# 3. Missing required secrets → verify .env.prod is complete

# Test with STRICT_STARTUP=false for debugging
docker run --rm --env-file .env.prod -e STRICT_STARTUP=false ghcr.io/.../api:latest
```

## Security Checklist

- [ ] `.env.prod` is NOT committed to git (listed in `.gitignore`)
- [ ] Database uses TLS (`sslmode=require` in connection string)
- [ ] Digital Ocean database has IP allowlist configured (optional)
- [ ] Grafana Cloud API tokens are rotated regularly
- [ ] API container runs as non-root user (UID 10001)
- [ ] Health check endpoints don't expose sensitive data
- [ ] Logs don't contain PHI/PII (enforced by JsonFormatter)
- [ ] Database backups are enabled in Digital Ocean
- [ ] Digital Ocean alerts are configured and tested

## Cost Optimization

### Database (Digital Ocean)

- **Starter Plan** ($15/mo): 1GB RAM, 10GB storage, 25 connections
  - Good for: Development, staging, low-traffic production
  - Connection pool settings: `DB_POOL_SIZE=5, DB_MAX_OVERFLOW=10`

- **Basic Plan** ($60/mo): 4GB RAM, 80GB storage, 60 connections
  - Good for: Production with moderate traffic
  - Connection pool settings: `DB_POOL_SIZE=10, DB_MAX_OVERFLOW=20`

- **Professional Plan** ($180/mo): 16GB RAM, 200GB storage, 120 connections
  - Good for: High-traffic production
  - Connection pool settings: `DB_POOL_SIZE=20, DB_MAX_OVERFLOW=40`

### Observability (Grafana Cloud)

- **Free Tier**:
  - 10,000 traces/month
  - 50GB logs/month
  - Perfect for starting out

- **Optimization**:
  - Set `TRACES_SAMPLE_RATE=0.01` (1%) for high-traffic APIs
  - Use trace filtering to exclude health check endpoints
  - Archive old logs to reduce storage costs

## Next Steps

1. **Set up CI/CD pipeline** to automate builds and deployments
2. **Configure automated backups** beyond Digital Ocean defaults
3. **Add metrics export** to Grafana Cloud (beyond just traces)
4. **Implement canary deployments** for safer releases
5. **Set up staging environment** that mirrors production

## Support

For issues or questions:
- **GitHub Issues**: https://github.com/greta-47/my-first-repo/issues
- **Documentation**: https://docs.recoveryos.org
- **Email**: support@recoveryos.org
