# My First Repo

A simple FastAPI application for RecoveryOS.

## MVP: Single Compassionate Loop

Endpoints (FastAPI):
- `POST /check-in` – v0 rule-based scoring over adherence, mood trend, cravings, sleep, isolation
  - Fewer than 3 check-ins → `state="insufficient_data"`
  - Scoring bands: 0–29 low, 30–54 elevated, 55–74 moderate, 75–100 high
  - Deterministic reflections; high band includes crisis footer
- `POST /consents` and `GET /consents/{user_id}`
- `GET /healthz`, `GET /readyz`, `GET /metrics`

Privacy & safety:
- Structured JSON logs; no secrets/PII. Optional `SENTRY_DSN` env is supported but not required.
- In-memory per-client rate limiting (IP+UA hash) returns 429.

Docs:
- See docs/data_classification.md and docs/evidence_briefs.md.
- EPIC_and_issues.md outlines tasks; scripts/seed_issues.sh seeds GitHub issues.

## Requirements

- Python 3.12

## Setup

```bash
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-dev.txt
```

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
