#!/usr/bin/env bash
set -euo pipefail


echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting migration job..."

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[ERROR] DATABASE_URL environment variable is not set"
    exit 1
fi

echo "[INFO] Database URL configured (connection string redacted for security)"

echo "[INFO] Testing database connectivity..."
python3 -c "
from sqlalchemy import create_engine, text
import os
import sys

try:
    engine = create_engine(os.getenv('DATABASE_URL'), connect_args={'connect_timeout': 10})
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        result.fetchone()
    print('[INFO] Database connection successful')
except Exception as e:
    print(f'[ERROR] Database connection failed: {e}', file=sys.stderr)
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "[ERROR] Database connectivity check failed"
    exit 1
fi

echo "[INFO] Running Alembic migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "[SUCCESS] Migrations completed successfully at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
else
    echo "[ERROR] Migrations failed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 1
fi
