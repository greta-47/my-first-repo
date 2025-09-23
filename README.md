# RecoveryOS MVP — Single Compassionate Loop

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## How to run tests

```bash
# Run all tests
python -m pytest tests/

# Run tests with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_checkin.py
```

## How to run CI locally

```bash
# Format check
python -m ruff format --check .

# Lint check
python -m ruff check .

# Type checking
python -m mypy .

# Security audit
python -m pip-audit

# Run all checks
python -m ruff format --check . && \
python -m ruff check . && \
python -m mypy . && \
python -m pip-audit && \
python -m pytest tests/
```

## Test endpoints

```bash
curl -X POST http://127.0.0.1:8000/check-in   -H "Content-Type: application/json"   -d '{
    "user_id":"u123",
    "checkins_count": 3,
    "days_since_last_checkin": 2,
    "craving": 6,
    "mood": 2,
    "previous_mood": 3,
    "sleep_quality": "average",
    "sleep_hours": 5.5,
    "isolation_level": "sometimes"
  }'
```

## Metrics endpoints

Available endpoints: `/healthz`, `/readyz`, `/metrics`, `/consents`.

- `/healthz` - Health check endpoint
- `/readyz` - Readiness check endpoint  
- `/metrics` - Application metrics (check-in completion, risk band distribution, consent toggles)
- `/consents` - GET/POST consent management for family sharing
