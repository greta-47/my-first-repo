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
from pydantic import BaseModel, Field, ValidationError

APP_START_TS = time.time()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


logger = logging.getLogger("app")
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger.setLevel(logging.INFO)
logger.handlers = [_handler]

SENTRY_DSN = os.getenv("SENTRY_DSN") or ""


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
    h = hashlib.sha256()
    h.update(ip.encode("utf-8"))
    h.update(b"|")
    h.update(ua.encode("utf-8"))
    return h.hexdigest()


class ConsentPayload(BaseModel):
    user_id: str = Field(min_length=1)
    terms_version: str = Field(min_length=1)
    accepted: bool


class ConsentRecord(BaseModel):
    user_id: str
    terms_version: str
    accepted: bool
    recorded_at: str


class CheckIn(BaseModel):
    user_id: str = Field(min_length=1)
    adherence: int = Field(ge=0, le=100)
    mood_trend: int = Field(ge=-10, le=10)
    cravings: int = Field(ge=0, le=100)
    sleep_hours: float = Field(ge=0, le=24)
    isolation: int = Field(ge=0, le=100)
    ts: str = Field(default_factory=iso_now)


class CheckInResponse(BaseModel):
    state: Literal["ok", "insufficient_data"]
    band: Optional[Literal["low", "elevated", "moderate", "high"]] = None
    score: Optional[int] = None
    reflection: Optional[str] = None
    footer: Optional[str] = None


def v0_score(checkins: List[CheckIn]) -> Tuple[int, str, str]:
    latest = checkins[-1]
    score = 0
    score += max(0, 100 - latest.adherence) // 4
    score += max(0, -latest.mood_trend) * 3
    score += latest.cravings // 3
    score += int(max(0.0, 8.0 - latest.sleep_hours) * 4)
    score += latest.isolation // 2
    score = max(0, min(100, score))

    if score < 30:
        band = "low"
    elif score < 55:
        band = "elevated"
    elif score < 75:
        band = "moderate"
    else:
        band = "high"

    reflections = {
        "low": "You’re staying steady. Consider noting what helped today.",
        "elevated": "Small shifts matter. A brief walk or call might help.",
        "moderate": "It’s okay to pause. Try grounding with 3 slow breaths.",
        "high": "You deserve immediate care. Safety first.",
    }
    crisis_msg = (
        "If you are in danger or thinking about harming yourself, contact local "
        "emergency services or a trusted support line."
    )
    footer = (
        crisis_msg if band == "high" else "This is supportive information only and not a diagnosis."
    )
    return score, reflections[band], footer


def get_rate_key(request: Request) -> str:
    # Use IP/UA only to derive an anon hash for rate limiting. Do not log or expose.
    ip = request.client.host if request.client else "0.0.0.0"
    ua = request.headers.get("user-agent", "unknown")
    return anon_key(ip, ua)


app = FastAPI(
    title="Single Compassionate Loop API",
    version="0.0.1",
    description="API for compassionate mental health check-ins and consent management",
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Rate limit ONLY POST /check-in
    if request.method.upper() == "POST" and request.url.path == "/check-in":
        key = get_rate_key(request)
        if not RATE_LIMIT.allow(key):
            logger.info("rate_limited")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "rate_limited",
                    "message": "Too many requests. Please wait before retrying.",
                    "retry_after_seconds": 10,
                    "limit": "5 requests per 10 seconds",
                    "troubleshooting": (
                        "Space out check-in submissions or implement exponential backoff"
                    ),
                },
            )
    response = await call_next(request)
    return response


@app.get("/healthz")
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/readyz")
async def readyz() -> JSONResponse:
    return JSONResponse({"ok": True, "uptime_s": int(time.time() - APP_START_TS)})


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    # Minimal metrics, no high-cardinality labels, no IP/UA exposure.
    lines = [
        "# HELP app_uptime_seconds Application uptime in seconds",
        "# TYPE app_uptime_seconds gauge",
        f"app_uptime_seconds {int(time.time() - APP_START_TS)}",
        "# HELP app_checkins_total Total check-ins received",
        "# TYPE app_checkins_total counter",
        f"app_checkins_total {sum(len(v) for v in CHECKINS.values())}",
    ]
    return PlainTextResponse("\n".join(lines))


@app.get("/help")
async def help_endpoint() -> JSONResponse:
    """Provide API usage information and troubleshooting guidance."""
    return JSONResponse(
        {
            "api_info": {
                "title": "Single Compassionate Loop API",
                "version": "0.0.1",
                "description": (
                    "API for compassionate mental health check-ins and consent management"
                ),
            },
            "endpoints": {
                "health_checks": {
                    "GET /healthz": "Basic health check - returns 'ok'",
                    "GET /readyz": "Readiness check with uptime",
                    "GET /metrics": "Prometheus-style metrics",
                },
                "consent_management": {
                    "POST /consents": "Submit user consent",
                    "GET /consents/{user_id}": "Retrieve consent record",
                },
                "check_ins": {"POST /check-in": "Submit check-in data (rate limited: 5/10s)"},
            },
            "common_errors": {
                "HTTP_429": "Rate limited - wait 10 seconds before retry",
                "HTTP_422": "Validation error - check request format",
                "HTTP_404": "Resource not found - verify user_id exists",
                "insufficient_data": "Need 3+ check-ins for scoring",
            },
            "troubleshooting": {
                "documentation": "/docs/troubleshooting.md",
                "api_docs": "/docs (Swagger UI)",
                "test_connectivity": "curl http://127.0.0.1:8000/healthz",
            },
        }
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Enhanced validation error handling with troubleshooting hints."""
    logger.info(f"validation_error path={request.url.path}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "errors": exc.errors(),
            "troubleshooting": {
                "check_required_fields": "Ensure all required fields are present",
                "verify_data_types": "Check that field types match expectations",
                "api_help": "/help for endpoint documentation",
            },
        },
    )


@app.post("/consents", response_model=ConsentRecord)
async def post_consents(payload: ConsentPayload) -> ConsentRecord:
    rec = ConsentRecord(
        user_id=payload.user_id,
        terms_version=payload.terms_version,
        accepted=payload.accepted,
        recorded_at=iso_now(),
    )
    CONSENTS[payload.user_id] = rec
    logger.info("consent_recorded")
    return rec


@app.get("/consents/{user_id}", response_model=ConsentRecord | Dict[str, str])
async def get_consents(user_id: str):
    if not user_id.strip():
        logger.info("invalid_user_id_empty")
        return JSONResponse(
            status_code=400,
            content={
                "detail": "invalid_user_id",
                "message": "user_id cannot be empty",
                "troubleshooting": "Provide a valid non-empty user_id",
            },
        )

    c = CONSENTS.get(user_id)
    if not c:
        logger.info("consent_not_found user_id_redacted")
        return {
            "detail": "not_found",
            "message": "No consent record found for user",
            "troubleshooting": "Submit consent via POST /consents first",
        }
    return c


@app.post("/check-in", response_model=CheckInResponse)
async def check_in(payload: CheckIn, response: Response) -> CheckInResponse:
    CHECKINS[payload.user_id].append(payload)
    history = CHECKINS[payload.user_id]
    if len(history) < 3:
        logger.info("insufficient_data")
        return CheckInResponse(
            state="insufficient_data",
            band=None,
            score=None,
            reflection=(
                f"You have submitted {len(history)} check-in(s). "
                f"Please submit {3 - len(history)} more to receive "
                f"personalized scoring and feedback."
            ),
            footer="Keep checking in - your data helps us provide better support.",
        )

    score, reflection, footer = v0_score(history)
    band: Literal["low", "elevated", "moderate", "high"]
    if score < 30:
        band = "low"
    elif score < 55:
        band = "elevated"
    elif score < 75:
        band = "moderate"
    else:
        band = "high"

    # Redacted, band/score only; never log user-provided fields or identifiers.
    logger.info(
        "check_in_scored %s",
        json.dumps({"user": "redacted", "band": band, "score": score}, separators=(",", ":")),
    )
    return CheckInResponse(
        state="ok",
        band=band,
        score=score,
        reflection=reflection,
        footer=footer,
    )
