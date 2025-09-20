# syntax=docker/dockerfile:1.7

#############################################
# my-first-repo API — production-ready image
# - Builds wheels in a separate stage
# - Installs only wheels in runtime (small, fast)
#############################################

########## Stage 1: build wheels ##########
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Build deps only (removed later)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

# Copy only requirement spec first (better layer caching)
COPY requirements.txt /wheels/requirements.txt

# Build all deps into wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -U pip setuptools wheel pip-tools && \
    pip wheel --wheel-dir=/wheels/dist -r /wheels/requirements.txt

########## Stage 2: slim runtime ##########
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_NAME="my-first-repo API" \
    APP_VERSION="0.1.0" \
    PORT=8000 \
    WORKERS=1 \
    TIMEOUT=45

# Minimal runtime tools (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user first so we can chown on COPY
RUN useradd -m -u 10001 appuser
WORKDIR /app

# Install prebuilt wheels from builder (no source build here)
COPY --from=builder /wheels/dist /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application source (owned by non-root)
COPY --chown=appuser:appuser . /app

# Entrypoint wrapper
RUN echo '#!/usr/bin/env sh' > /app/entrypoint.sh && \
    echo 'set -euo pipefail' >> /app/entrypoint.sh && \
    echo 'if [ -x /app/prestart.sh ]; then /app/prestart.sh; fi' >> /app/entrypoint.sh && \
    echo 'exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS}' >> /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

USER appuser

# Simple container healthcheck (expects /health endpoint)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

LABEL org.opencontainers.image.title="my-first-repo API" \
      org.opencontainers.image.description="A simple FastAPI application for RecoveryOS" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/greta-47/my-first-repo"

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

