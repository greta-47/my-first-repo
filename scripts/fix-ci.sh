#!/usr/bin/env bash
set -euo pipefail
PR="${1:-106}"
if command -v gh >/dev/null 2>&1; then gh pr checkout "$PR"; fi
python -m pip install -U pip==24.2 pip-tools==7.4.1
[ -f requirements.lock.txt ] && pip install -r requirements.lock.txt || true
[ -f requirements-dev.lock.txt ] && pip install -r requirements-dev.lock.txt || true
docker run --rm -v "$PWD":/app -w /app python:3.12-bullseye bash -lc "python -m pip install -U pip==24.2 pip-tools==7.4.1 && pip-compile --generate-hashes --allow-unsafe -o requirements.lock.txt requirements.txt && if [ -f requirements-dev.txt ]; then pip-compile --generate-hashes --allow-unsafe -o requirements-dev.lock.txt requirements-dev.txt; fi"
python -m ruff format .
python -m ruff check . --fix
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
git add requirements.lock.txt 2>/dev/null || true
[ -f requirements-dev.lock.txt ] && git add requirements-dev.lock.txt || true
git add -A
if ! git diff --cached --quiet; then git commit -m "ci: lockfile regen (Linux, pip==24.2, pip-tools==7.4.1) + lint fixes"; fi
git push
