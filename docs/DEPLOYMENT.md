# Deployment & Container Strategy

## Container Image & Build

### Multi-Stage Dockerfile
```dockerfile
# Build stage
FROM python:3.12-slim as builder

WORKDIR /app
COPY requirements.lock.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.lock.txt

# Runtime stage
FROM python:3.12-slim

# Create non-root user
RUN groupadd --gid 1001 app && \
    useradd --uid 1001 --gid app --shell /bin/bash --create-home app

# Install wheels from build stage
COPY --from=builder /app/wheels /wheels
COPY requirements.lock.txt .
RUN pip install --no-cache /wheels/*

# Copy application code
WORKDIR /app
COPY --chown=app:app . .

# Read-only filesystem setup
USER app
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Build Pipeline
```bash
# Security scanning with Trivy
docker build -t recoveryos:${GITHUB_SHA} .
trivy image --exit-code 1 --severity HIGH,CRITICAL recoveryos:${GITHUB_SHA}

# Generate SBOM
syft recoveryos:${GITHUB_SHA} -o spdx-json=sbom.json

# Multi-platform build
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "ghcr.io/${OWNER}/recoveryos:${GITHUB_SHA}" \
  -t "ghcr.io/${OWNER}/recoveryos:v${VERSION}" \
  --push .
```

### Security Hardening
- **Non-root user**: All processes run as UID 1001
- **Read-only filesystem**: Mount `/app` as read-only, writable `/tmp` only
- **Minimal capabilities**: `CAP_NET_BIND_SERVICE` only if binding to port 80/443
- **Distroless base**: Consider `gcr.io/distroless/python3` for production

## Runtime Configuration

### 12-Factor Compliance
```python
# settings.py - Environment-driven configuration
class Settings(BaseSettings):
    app_env: str = Field(default="production")
    log_level: str = Field(default="INFO")
    database_url: SecretStr
    jwt_public_keys_url: HttpUrl
    
    class Config:
        env_file = ".env"  # Dev only, never in production images
```

### Security Headers & TLS
- **TLS termination**: At load balancer/ingress (ALB, NGINX, Envoy)
- **HSTS**: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **Strong ciphers**: TLS 1.2+ only, disable weak cipher suites
- **Certificate management**: Auto-renewal with Let's Encrypt or managed certificates

### Logging Standards
```python
# Structured JSON logging
{
    "timestamp": "2025-09-27T10:30:00Z",
    "level": "INFO", 
    "logger": "app.api",
    "msg": "check_in_processed",
    "request_id": "01J123...",
    "member_id": "redacted",
    "duration_ms": 45
}
```

## Kubernetes Deployment

### Pod Security & Resources
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: recoveryos-api
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
        fsGroup: 1001
      containers:
      - name: api
        image: ghcr.io/owner/recoveryos:v1.2.3
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi" 
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
```

### Network Policies
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: recoveryos-api-netpol
spec:
  podSelector:
    matchLabels:
      app: recoveryos-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
  egress:
  - to: []  # Database and OTEL collector only
    ports:
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP  
      port: 4317  # OTEL gRPC
```

### Auto-scaling
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: recoveryos-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: recoveryos-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Secrets Management

### Production Secrets
- **AWS Secrets Manager**: Retrieve at runtime via IAM roles
- **GCP Secret Manager**: Use Workload Identity for pod authentication  
- **Kubernetes CSI**: Mount secrets as files, auto-rotation support
- **Never in images**: No `.env` files or hardcoded secrets in containers

```python
# Runtime secret retrieval
import boto3

def get_database_url() -> str:
    if os.getenv("APP_ENV") == "dev":
        return os.getenv("DATABASE_URL", "postgresql://...")
    
    # Production: fetch from Secrets Manager
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='recoveryos/database')
    return json.loads(response['SecretString'])['url']
```

## Observability

### OpenTelemetry Integration
```python
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Configure OTEL
tracer = trace.get_tracer(__name__)
FastAPIInstrumentor.instrument_app(app)

# Sample configuration
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_ENDPOINT", "http://otel-collector:4317")
OTEL_RESOURCE_ATTRIBUTES = "service.name=recoveryos-api,service.version=1.2.3"
```

### Monitoring Stack
- **Traces**: Jaeger/Tempo for request tracing
- **Metrics**: Prometheus for application metrics
- **Logs**: ELK/Loki for centralized logging
- **Alerting**: AlertManager for critical error notifications

## Backup & Recovery

### Database Backups
```bash
# Point-in-time recovery setup
pg_basebackup --pgdata=/backup/base --format=tar --gzip --progress
pg_receivewal --directory=/backup/wal --synchronous

# Automated restore testing
pg_restore --clean --if-exists --dbname=recovery_test backup.tar
```

### SMS Provider Configuration
- **Webhook allowlist**: Only accept webhooks from verified Twilio IPs
- **Signature verification**: Validate `X-Twilio-Signature` header
- **Failover**: Configure backup SMS provider for critical alerts

## Golden Path Deployment

### Local Development
```bash
# Docker Compose stack
docker compose up api db redis otel-collector

# Services:
# - api: FastAPI application (port 8000)
# - db: PostgreSQL with test data
# - redis: Rate limiting and session storage  
# - otel-collector: Local telemetry collection
```

### CI/CD Pipeline
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  build-test-deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Build Docker image
      run: docker build -t recoveryos:${GITHUB_SHA} .
      
    - name: Run tests  
      run: docker run --rm recoveryos:${GITHUB_SHA} python -m pytest
      
    - name: Security scan
      run: |
        trivy image --exit-code 1 --severity HIGH,CRITICAL recoveryos:${GITHUB_SHA}
        
    - name: Push to registry
      run: |
        docker tag recoveryos:${GITHUB_SHA} ghcr.io/${GITHUB_REPOSITORY}:${GITHUB_SHA}
        docker push ghcr.io/${GITHUB_REPOSITORY}:${GITHUB_SHA}
        
    - name: Deploy to staging
      run: |
        kubectl set image deployment/recoveryos-api api=ghcr.io/${GITHUB_REPOSITORY}:${GITHUB_SHA}
        kubectl rollout status deployment/recoveryos-api --timeout=300s
```

### Production Deployment Strategy
- **Blue/Green**: Zero-downtime deployments with instant rollback
- **Database migrations**: Gated behind readiness probes, backward compatible
- **Canary releases**: Route 5% traffic to new version, monitor error rates
- **Circuit breakers**: Fail fast on external service degradation