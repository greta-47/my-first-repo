# My First Repo

A simple FastAPI application for RecoveryOS.

## Run locally
```bash
python -m uvicorn api.main:app --reload
curl -fsS http://127.0.0.1:8000/health
```

## Deploy (Render)
Start Command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
# Trigger CI
