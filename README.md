# My First Repo

A simple FastAPI application for RecoveryOS.

<!-- Test change to trigger auto-add workflow -->

## Run locally

```bash
# run
python -m uvicorn app.main:app --reload
# or: python3 -m uvicorn app.main:app --reload
```

## Tests

```bash
# test (after installing locks)
python -m pytest -q
# or: python3 -m pytest -q
```

### Install (new contributors)

```bash
python -m pip install -U pip==24.2 pip-tools==7.4.1
pip install -r requirements.lock.txt
pip install -r requirements.dev.lock.txt
```

Note: The repository pins pyenv to Python 3.12.10 for consistency across dev and CI. Ensure you have a compatible python3 available locally.

## API Documentation

- **Interactive API docs**: Visit `http://127.0.0.1:8000/docs` when running locally
- **Help endpoint**: `GET /help` for API information and troubleshooting
- **Troubleshooting guide**: See [docs/troubleshooting.md](docs/troubleshooting.md)

## CI

- Python 3.12 only. Ruff, mypy, pytest, and pip-audit (non-blocking in PR CI) run in `.github/workflows/ci.yml`.
- A nightly dependency audit blocks on High/Critical vulnerabilities (see `.github/workflows/nightly-audit.yml`).
