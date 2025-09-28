# Copilot Instructions: RecoveryOS Single Compassionate Loop MVP

## Architecture Overview

This is a **privacy-first FastAPI application** for mental health check-ins with two distinct entry points:
- `/app/main.py` - Main application with business logic (check-ins, consents, scoring)
- `/api/main.py` - API wrapper with security middleware and CORS

**Key principle**: Zero PHI/PII logging or persistence. All data is in-memory only for MVP.

## Security-First Patterns

### 1. Privacy-Safe Logging
```python
# NEVER log user data directly - always redact
logger.info("check_in_scored %s", json.dumps({"user": "redacted", "band": band, "score": score}))
```
- Use `JsonFormatter` for structured logs with `ts/level/logger/msg`
- Intentionally omit stack traces to prevent data leakage
- Rate limiting uses `anon_key(ip, ua)` - derived hash, never raw IP/UA

### 2. Security Headers & Middleware
Security middleware in `/api/` applies strict CSP, HTTPS enforcement, and security headers:
- `EnforceHTTPSMiddleware` - Redirects HTTP to HTTPS in production
- `SecurityHeadersMiddleware` - Adds CSP with default-deny policy
- Settings-based configuration via `ENV`, `ENFORCE_HTTPS`, `CSP_REPORT_ONLY`

## Development Workflow

### Local Development
```bash
# Primary development server (business logic)
python -m uvicorn app.main:app --reload

# API server (with security middleware)  
python -m uvicorn api.main:app --reload

# Health check
curl -fsS http://127.0.0.1:8000/healthz
```

### Code Quality (Python 3.12 only)
```bash
# Pre-commit formatting & linting
./scripts/precommit.sh

# Full CI checks
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
```

## Business Logic Patterns

### Check-In Scoring System
- Requires 3+ check-ins before scoring (`insufficient_data` state)
- Rule-based `v0_score()` algorithm with deterministic bands: low/elevated/moderate/high
- Crisis messaging automatically added for "high" band
- Rate limiting only on `POST /check-in` (5 requests per 10 seconds per client)

### In-Memory Storage
```python
CONSENTS: Dict[str, ConsentRecord] = {}
CHECKINS: Dict[str, List[CheckIn]] = defaultdict(list)
```
- No database - all state is ephemeral
- Use this pattern for MVP features requiring temporary persistence

## Testing Philosophy

Write tests that validate:
1. **Privacy compliance** - No user data in logs/responses
2. **Rate limiting behavior** - 429 responses after limits exceeded  
3. **Business rules** - Scoring thresholds, insufficient data handling
4. **Security headers** - Middleware applies correct CSP/security headers

See `/tests/test_app.py` for examples testing insufficient data, high-risk scoring, and rate limits.

## CI/CD Configuration

- **Python 3.12 only** - No version matrix
- Nightly pip-audit blocks on High/Critical vulnerabilities
- PR CI includes non-blocking pip-audit for visibility
- Use `/scripts/precommit.sh` before commits to match CI checks

## Documentation Requirements

When adding features, update:
- `/docs/data_classification.md` - Privacy/security implications
- `/EPIC_and_issues.md` - Feature tracking and completion status
- Tests demonstrating privacy-safe behavior

## Extended Documentation

For comprehensive patterns beyond MVP scope:
- `/docs/DATA-MODEL.md` - Database schema, RLS patterns, PHI handling
- `/docs/DEPLOYMENT.md` - Container security, K8s configs, CI/CD pipelines  
- `/docs/API.md` - REST conventions, error handling, pagination standards
- `/docs/ENVIRONMENT.md` - Configuration management, secrets rotation