#!/usr/bin/env bash
set -euo pipefail


echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting migration job..."

if [ "${DB_AUTO_MIGRATE:-false}" != "true" ]; then
    echo "[INFO] DB_AUTO_MIGRATE!=true; skipping migrations (set DB_AUTO_MIGRATE=true to enable)"
    exit 0
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[ERROR] DATABASE_URL environment variable is not set"
    exit 1
fi

echo "[INFO] Database URL configured (connection string redacted for security)"

MAX_RETRIES=10
RETRY_COUNT=0
INITIAL_DELAY=2
MAX_DELAY=10
TOTAL_TIMEOUT=120
START_TIME=$(date +%s)

check_db_connectivity() {
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        ELAPSED=$(($(date +%s) - START_TIME))
        if [ $ELAPSED -ge $TOTAL_TIMEOUT ]; then
            echo "[ERROR] Database connectivity timeout after ${TOTAL_TIMEOUT}s"
            return 1
        fi

        echo "[INFO] Testing database connectivity (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)..."
        
        if python3 -c "
from sqlalchemy import create_engine, text
import os
import sys

try:
    engine = create_engine(os.getenv('DATABASE_URL'), connect_args={'connect_timeout': 10})
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        result.fetchone()
    print('[INFO] Database connection successful')
    sys.exit(0)
except Exception as e:
    print(f'[WARN] Database connection failed: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1; then
            return 0
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            DELAY=$((INITIAL_DELAY * (2 ** (RETRY_COUNT - 1))))
            if [ $DELAY -gt $MAX_DELAY ]; then
                DELAY=$MAX_DELAY
            fi
            JITTER=$((RANDOM % (DELAY / 2 + 1)))
            TOTAL_DELAY=$((DELAY + JITTER))
            
            echo "[INFO] Retrying in ${TOTAL_DELAY}s..."
            sleep $TOTAL_DELAY
        fi
    done

    echo "[ERROR] Database connectivity check failed after $MAX_RETRIES attempts"
    return 1
}

if ! check_db_connectivity; then
    echo "[ERROR] Could not establish database connection"
    exit 1
fi

echo "[INFO] Running Alembic migrations..."
if alembic upgrade head; then
    echo "[SUCCESS] Migrations completed successfully at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
else
    echo "[ERROR] Migrations failed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 1
fi
