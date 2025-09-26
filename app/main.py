from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

APP_START_TS = time.time()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -----------------------------
# Secure, PHI/PII-safe logging
# -----------------------------

# Optional (OFF by default): route exception stacks to Sentry WITHOUT leaking them into JSON logs.
SENTRY_DSN = os.getenv("SENTRY_DSN")
LOG_STACKS_TO_SENTRY = os.getenv("LOG_STACKS_TO_SENTRY", "false").lower() == "true"
if SENTRY_DSN and LOG_STACKS_TO_SENTRY:
    try:
        import sentry_sdk  # type: ignore
        # Keep lightweight: no performance tracing; error-only.
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)
    except Exception:
        # Never let observability break the app.
        pass


class JsonFormatter(logging.Formatter):
    """
    Security-hardened JSON log formatter.
    - Emits compact JSON with ts/level/logger/msg.
    - Intentionally omits stack traces/exception text (exc_info) to prevent PHI/PII leakage.
    - If stack capture is needed, enable Sentry via env (see flags above).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # DO NOT serialize record.exc_info or "Traceback" text into structured logs.
        return json.dumps(payload, separators=(",", ":"))


logger = logging.getLogger("app")
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger.setLevel(logging.INFO)
logger.handlers = [_handler]

# Note: we intentionally do NOT touch Uvicorn access logs here; ensure deployment config avoids IP/UA in sinks.


@dataclass
class RateLimitConfig:
    capacity: int = 5
    window_seconds: int = 10


class InMemoryRateLimiter:
    def __init__(self, cfg: RateLimitConfig) -> None:
        self.cfg = cfg
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = now or time.time()
        dq = self.hits[key]
        cutoff = now - self.cfg.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self.cfg.capacity:
            return False
        dq.append(now)
        return True


RATE_LIMIT = InMemoryRateLimiter(RateLimitConfig())
CONSENTS: Dict[str, "ConsentRecord"] = {}
CHECKINS: Dict[str, List["CheckIn"]] = defaultdict(list)


def anon_key(ip: str, ua: str) -> str:
    """
    Derive an anonymous, deterministic rate-limit key from IP/UA **without** logging them.
    Inputs are never logged or returned; only a hash is kept in-memory.
    """
    h = hashlib.sha256
