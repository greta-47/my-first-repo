# RecoveryOS MVP — Single Compassionate Loop

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

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

Endpoints: `/healthz`, `/readyz`, `/metrics`, `/consents`.
