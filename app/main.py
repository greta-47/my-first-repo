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


class JsonFormatter(logging.Formatter):
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
    ip = request.client.host if request.client else "0.0.0.0"
    ua = request.headers.get("user-agent", "unknown")
    return anon_key(ip, ua)


app = FastAPI(title="Single Compassionate Loop API", version="0.0.1")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method.upper() == "POST" and request.url.path == "/check-in":
        key = get_rate_key(request)
        if not RATE_LIMIT.allow(key):
            logger.info("rate_limited")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "rate_limited"},
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
    lines = [
        "# HELP app_uptime_seconds Application uptime in seconds",
        "# TYPE app_uptime_seconds gauge",
        f"app_uptime_seconds {int(time.time() - APP_START_TS)}",
        "# HELP app_checkins_total Total check-ins received",
        "# TYPE app_checkins_total counter",
        f"app_checkins_total {sum(len(v) for v in CHECKINS.values())}",
    ]
    return PlainTextResponse("\n".join(lines))


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
    c = CONSENTS.get(user_id)
    if not c:
        return {"detail": "not_found"}
    return c


@app.post("/check-in", response_model=CheckInResponse)
async def check_in(payload: CheckIn, response: Response) -> CheckInResponse:
    CHECKINS[payload.user_id].append(payload)
    history = CHECKINS[payload.user_id]
    if len(history) < 3:
        logger.info("insufficient_data")
        return CheckInResponse(state="insufficient_data")

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

    logger.info(
        "check_in_scored %s",
        json.dumps(
            {
                "user": "redacted",
                "band": band,
                "score": score,
            },
            separators=(",", ":"),
        ),
    )
    return CheckInResponse(
        state="ok",
        band=band,
        score=score,
        reflection=reflection,
        footer=footer,
    )
