# Environment Variables & Secrets Management

## Configuration Architecture

### Settings Class (Centralized Configuration)
```python
# settings.py - Single source of truth for configuration
from pydantic import Field, SecretStr, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Application
    app_env: str = Field(default="production", description="Environment name")
    app_version: str = Field(default="unknown", description="Application version")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # Privacy & Security  
    request_log_redact: bool = Field(default=True, description="Redact PII in request logs")
    deidentify_default: bool = Field(default=True, description="Use display codes by default")
    
    # Database
    database_url: SecretStr = Field(description="Primary database connection string")
    database_ro_url: SecretStr | None = Field(default=None, description="Read-only replica URL") 
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Database pool overflow")
    
    # Authentication & JWT
    jwt_public_keys_url: HttpUrl | None = Field(default=None, description="JWKS endpoint URL")
    jwt_algorithm: str = Field(default="RS256", description="JWT signature algorithm")
    session_secret: SecretStr | None = Field(default=None, description="Session encryption key")
    
    # Rate Limiting
    rate_limit_capacity: int = Field(default=5, description="Rate limit bucket capacity")
    rate_limit_window_seconds: int = Field(default=10, description="Rate limit time window")
    
    # Observability
    otel_exporter_otlp_endpoint: HttpUrl | None = Field(default=None)
    otel_service_name: str = Field(default="recoveryos-api")
    traces_sample_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    metrics_enabled: bool = Field(default=True)
    
    # SMS Provider
    sms_provider: str = Field(default="twilio", description="SMS provider name")
    twilio_account_sid: SecretStr | None = Field(default=None)
    twilio_auth_token: SecretStr | None = Field(default=None) 
    twilio_messaging_service_sid: str | None = Field(default=None)
    
    # Risk Scoring Model
    risk_model_version: str = Field(default="v0.1.0")
    risk_grace_days: int = Field(default=3, description="Days before risk scoring starts")
    risk_bands: str = Field(default="0-29,30-54,55-74,75-100", description="Risk band thresholds")
    
    # Feature Flags
    enable_family_sharing: bool = Field(default=False)
    enable_crisis_alerts: bool = Field(default=True)
    enable_sms_notifications: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=".env",  # Dev only - never in production images
        env_file_encoding="utf-8",
        case_sensitive=True,
        validate_default=True
    )

    @classmethod
    def for_environment(cls, env: str = "production") -> "Settings":
        """Factory method with environment-specific defaults."""
        if env == "development":
            return cls(
                app_env="development",
                log_level="DEBUG", 
                debug=True,
                traces_sample_rate=1.0,
                database_url="postgresql://user:pass@localhost:5432/recoveryos_dev"
            )
        elif env == "testing":
            return cls(
                app_env="testing",
                log_level="WARNING",
                database_url="postgresql://username:password@localhost:5432/recoveryos_test",
                rate_limit_capacity=100  # Higher limits for tests
            )
        return cls()  # Production defaults

# Usage in application startup
settings = Settings.for_environment(os.getenv("APP_ENV", "production"))
```

### Configuration Precedence
1. **Default values** (in Settings class)
2. **`.env` file** (development only)
3. **Environment variables** 
4. **Secret managers** (AWS/GCP Secrets Manager)
5. **Runtime overrides** (feature flags, A/B tests)

## Environment Matrix

### Development Environment
```bash
# .env (local development only)
APP_ENV=development
LOG_LEVEL=DEBUG
DEBUG=true

# Local services
DATABASE_URL=postgresql://YOUR_USERNAME:YOUR_PASSWORD@localhost:5432/recoveryos_dev
REDIS_URL=redis://localhost:6379/0

# Disable external services for local dev
SMS_PROVIDER=mock
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
TRACES_SAMPLE_RATE=1.0

# Relaxed security for development
REQUEST_LOG_REDACT=false
DEIDENTIFY_DEFAULT=false
ENABLE_FAMILY_SHARING=true
```

### Testing Environment  
```bash
APP_ENV=testing
LOG_LEVEL=WARNING
DATABASE_URL=postgresql://test_user:test_pass@postgres:5432/recoveryos_test

# Higher rate limits for integration tests
RATE_LIMIT_CAPACITY=100
RATE_LIMIT_WINDOW_SECONDS=1

# Mock external services
SMS_PROVIDER=mock
TWILIO_ACCOUNT_SID=test_account_sid
TWILIO_AUTH_TOKEN=test_auth_token

# Observability disabled in tests
OTEL_EXPORTER_OTLP_ENDPOINT=""
METRICS_ENABLED=false
```

### Staging Environment
```bash
APP_ENV=staging
APP_VERSION=${GIT_SHA}
LOG_LEVEL=INFO

# Production-like database
DATABASE_URL=${SECRET:staging/database_url}
DATABASE_RO_URL=${SECRET:staging/database_ro_url}

# Real SMS provider with test credentials
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=${SECRET:staging/twilio_sid}
TWILIO_AUTH_TOKEN=${SECRET:staging/twilio_token}
TWILIO_MESSAGING_SERVICE_SID=MGtest123

# Full observability
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-staging.internal:4317
TRACES_SAMPLE_RATE=0.1

# Feature flags for staging
ENABLE_FAMILY_SHARING=true
ENABLE_CRISIS_ALERTS=true
ENABLE_SMS_NOTIFICATIONS=false
```

### Production Environment
```bash
APP_ENV=production
APP_VERSION=${RELEASE_TAG}
LOG_LEVEL=INFO
DEBUG=false

# Secrets from AWS Secrets Manager
DATABASE_URL=${AWS_SECRET:prod/recoveryos/database_url}
DATABASE_RO_URL=${AWS_SECRET:prod/recoveryos/database_ro_url}
SESSION_SECRET=${AWS_SECRET:prod/recoveryos/session_secret}

# JWT validation
JWT_PUBLIC_KEYS_URL=https://auth.recoveryos.org/.well-known/jwks.json
JWT_ALGORITHM=RS256

# Production SMS
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=${AWS_SECRET:prod/twilio/account_sid}
TWILIO_AUTH_TOKEN=${AWS_SECRET:prod/twilio/auth_token}
TWILIO_MESSAGING_SERVICE_SID=${AWS_SECRET:prod/twilio/messaging_service_sid}

# Production observability
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.recoveryos.org:4317
OTEL_SERVICE_NAME=recoveryos-api
TRACES_SAMPLE_RATE=0.01

# Database performance
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Production feature flags
ENABLE_FAMILY_SHARING=false  # Gradual rollout
ENABLE_CRISIS_ALERTS=true
ENABLE_SMS_NOTIFICATIONS=true

# Risk model configuration  
RISK_MODEL_VERSION=v1.0.0
RISK_GRACE_DAYS=3
RISK_BANDS="0-24,25-49,50-74,75-100"
```

## Secrets Management Strategy

### Development Secrets
```bash
# .env.example (committed to repo, no actual secrets)
DATABASE_URL=postgresql://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/recoveryos_dev
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
SESSION_SECRET=generate_with_openssl_rand_base64_32

# Developers create their own .env (gitignored)
cp .env.example .env
# Edit .env with real development credentials
```

### Production Secrets (AWS Example)
```python
# secrets.py - Runtime secret retrieval
import json
import boto3
from functools import lru_cache

@lru_cache(maxsize=32)
def get_secret(secret_name: str) -> str:
    """Retrieve secret from AWS Secrets Manager with caching."""
    if os.getenv("APP_ENV") == "development":
        # Use local .env in development
        return os.getenv(secret_name.replace("/", "_").upper(), "")
    
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in response:
            secret_dict = json.loads(response['SecretString'])
            # Extract specific key if secret_name contains a path
            if "/" in secret_name:
                _, key = secret_name.rsplit("/", 1)
                return secret_dict.get(key, "")
            return secret_dict.get('value', response['SecretString'])
        
        # Handle binary secrets
        return base64.b64decode(response['SecretBinary']).decode('utf-8')
        
    except ClientError as e:
        logger.error(f"Failed to retrieve secret {secret_name}: {e}")
        raise

# Usage in settings
class Settings(BaseSettings):
    database_url: str = Field(default_factory=lambda: get_secret("prod/recoveryos/database_url"))
    twilio_auth_token: str = Field(default_factory=lambda: get_secret("prod/twilio/auth_token"))
```

### Kubernetes Secrets (CSI Driver Example)
```yaml
# External Secrets Operator
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: recoveryos-api

---
apiVersion: external-secrets.io/v1beta1  
kind: ExternalSecret
metadata:
  name: recoveryos-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: app-secrets
    creationPolicy: Owner
  data:
  - secretKey: DATABASE_URL
    remoteRef:
      key: prod/recoveryos/database_url
  - secretKey: TWILIO_AUTH_TOKEN  
    remoteRef:
      key: prod/twilio/auth_token
```

## Secret Rotation & Security

### Rotation Policy
- **Database passwords**: Quarterly rotation with zero-downtime
- **API keys**: Monthly rotation (SMS, external services)  
- **Session secrets**: Weekly rotation with overlap period
- **JWT signing keys**: Annual rotation with key rollover

### Break-Glass Procedures
```bash
# Emergency credential reset
aws secretsmanager update-secret \
  --secret-id prod/recoveryos/database_url \
  --secret-string '{"url":"postgresql://emergency_user:temp_pass@..."}' \
  --description "Break-glass credential reset $(date)"

# Immediate application restart to pick up new secrets
kubectl rollout restart deployment/recoveryos-api
kubectl rollout status deployment/recoveryos-api --timeout=300s
```

### Local Development Setup
```bash
# Install SOPS for encrypted local secrets (optional)
brew install sops age

# Create encrypted .env.local (never committed)
sops -e -i .env.local

# Or use AWS Secrets Manager for local development
aws secretsmanager get-secret-value \
  --secret-id dev/recoveryos/local-env \
  --query SecretString --output text > .env.local
```

### Startup Validation
```python
# app/startup.py - Validate critical configuration on startup
def validate_startup_config(settings: Settings) -> None:
    """Validate critical configuration and fail fast if invalid."""
    missing_secrets = []
    
    # Check required secrets based on environment
    if settings.app_env == "production":
        required_secrets = [
            ("DATABASE_URL", settings.database_url),
            ("JWT_PUBLIC_KEYS_URL", settings.jwt_public_keys_url), 
            ("TWILIO_AUTH_TOKEN", settings.twilio_auth_token)
        ]
        
        for name, value in required_secrets:
            if not value or (isinstance(value, SecretStr) and not value.get_secret_value()):
                missing_secrets.append(name)
    
    if missing_secrets:
        logger.error(f"Missing required secrets: {missing_secrets}")
        sys.exit(1)
    
    # Log configuration presence (not values)
    logger.info(f"Configuration loaded: env={settings.app_env}, "
                f"db_configured={bool(settings.database_url)}, "
                f"sms_enabled={bool(settings.twilio_auth_token)}")

# Call during application startup
validate_startup_config(settings)
```