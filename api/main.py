from __future__ import annotations

import os
from fastapi import FastAPI, Response
from starlette.middleware.cors import CORSMiddleware

from .settings import Settings
from .security_middleware import SecurityHeadersMiddleware, EnforceHTTPSMiddleware

settings = Settings()

app = FastAPI(title="RecoveryOS API", version=os.getenv("VERSION", "0"))

app.add_middleware(EnforceHTTPSMiddleware, settings=settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    max_age=86400,
)

app.add_middleware(SecurityHeadersMiddleware, settings=settings)


@app.get("/health", tags=["infra"])
def health() -> dict:
    return {"ok": True}


@app.head("/health", tags=["infra"])
def health_head() -> Response:
    return Response(status_code=200)


@app.get("/healthz", tags=["infra"])
def healthz() -> dict:
    return {"ok": True}


@app.head("/healthz", tags=["infra"])
def healthz_head() -> Response:
    return Response(status_code=200)
