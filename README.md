# My First Repo

A simple FastAPI application for RecoveryOS.

<!-- Test change to trigger auto-add workflow -->

## Run locally

```bash
python -m uvicorn app.main:app --reload
curl -fsS http://127.0.0.1:8000/healthz
```

## Tests

```bash
python -m pytest -q
```

## CI

- Python 3.12 only. Ruff, mypy, pytest, and pip-audit (non-blocking in PR CI) run in `.github/workflows/ci.yml`.
- A nightly dependency audit blocks on High/Critical vulnerabilities (see `.github/workflows/nightly-audit.yml`).
