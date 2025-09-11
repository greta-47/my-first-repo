from __future__ import annotations

import os
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .settings import Settings
from .security_middleware import SecurityHeadersMiddleware, EnforceHTTPSMiddleware

settings = Settings()

app = FastAPI(title="RecoveryOS API", version=os.getenv("VERSION", "0"))

# 1) HTTPS enforcement
app.add_middleware(EnforceHTTPSMiddleware, settings=settings)

# 2) CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,
)

# 3) Security headers
app.add_middleware(SecurityHeadersMiddleware, settings=settings)


@app.get("/health", tags=["infra"])
def health() -> dict:
    return {"ok": True}

