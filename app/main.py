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


class TroubleshootingRequest(BaseModel):
    issue_type: Literal["login", "connection", "data", "performance", "general"] = "general"
    error_message: Optional[str] = None
    user_agent: Optional[str] = None
    additional_context: Optional[str] = None


class TroubleshootingStep(BaseModel):
    step: int
    title: str
    description: str
    action: Optional[str] = None


class TroubleshootingResponse(BaseModel):
    issue_type: str
    steps: List[TroubleshootingStep]
    emergency_contact: Optional[str] = None
    additional_resources: List[str] = []


def generate_troubleshooting_steps(request: TroubleshootingRequest) -> TroubleshootingResponse:
    """Generate structured troubleshooting steps based on issue type."""

    common_steps = {
        "login": [
            TroubleshootingStep(
                step=1,
                title="Verify Credentials",
                description="Double-check your username/email and password for accuracy.",
                action="Re-enter login information carefully",
            ),
            TroubleshootingStep(
                step=2,
                title="Check Network Connection",
                description="Ensure you have a stable internet connection.",
                action="Try accessing other websites or restart your connection",
            ),
            TroubleshootingStep(
                step=3,
                title="Clear Browser Data",
                description="Clear cache, cookies, and browser data that might be interfering.",
                action="Clear browser cache and cookies, then try again",
            ),
            TroubleshootingStep(
                step=4,
                title="Try Different Browser",
                description="Test with a different browser or incognito/private mode.",
                action="Use Chrome, Firefox, or Safari in private browsing mode",
            ),
            TroubleshootingStep(
                step=5,
                title="Check Service Status",
                description="Verify that the service is not experiencing outages.",
                action="Visit our status page or contact support if issues persist",
            ),
        ],
        "connection": [
            TroubleshootingStep(
                step=1,
                title="Check Internet Connection",
                description="Verify your device is connected to the internet.",
                action="Test connection by visiting other websites",
            ),
            TroubleshootingStep(
                step=2,
                title="Restart Network",
                description="Restart your router/modem or reconnect to WiFi.",
                action="Unplug router for 30 seconds, then reconnect",
            ),
            TroubleshootingStep(
                step=3,
                title="Check Firewall Settings",
                description="Ensure no firewall or security software is blocking access.",
                action="Temporarily disable firewall or add exception",
            ),
        ],
        "data": [
            TroubleshootingStep(
                step=1,
                title="Verify Data Format",
                description="Ensure all required fields are filled with valid values.",
                action="Check that dates, numbers, and text fields contain appropriate data",
            ),
            TroubleshootingStep(
                step=2,
                title="Check Field Limits",
                description="Verify that input doesn't exceed maximum allowed lengths.",
                action="Review character limits for text fields",
            ),
            TroubleshootingStep(
                step=3,
                title="Refresh and Retry",
                description="Refresh the page and try submitting again.",
                action="Press F5 or reload the page, then resubmit",
            ),
        ],
        "performance": [
            TroubleshootingStep(
                step=1,
                title="Check System Resources",
                description="Ensure your device has adequate memory and processing capacity.",
                action="Close unnecessary applications and browser tabs",
            ),
            TroubleshootingStep(
                step=2,
                title="Update Browser",
                description="Use the latest version of your web browser.",
                action="Update to the newest browser version available",
            ),
            TroubleshootingStep(
                step=3,
                title="Disable Extensions",
                description="Temporarily disable browser extensions that might slow performance.",
                action="Disable ad blockers and other extensions temporarily",
            ),
        ],
        "general": [
            TroubleshootingStep(
                step=1,
                title="Restart Application",
                description="Close and reopen the application or refresh the page.",
                action="Fully close and restart the application",
            ),
            TroubleshootingStep(
                step=2,
                title="Check for Updates",
                description="Ensure you're using the latest version of the application.",
                action="Check for and install any available updates",
            ),
            TroubleshootingStep(
                step=3,
                title="Review Error Messages",
                description="Look for specific error messages that can guide resolution.",
                action="Note exact error text and search for specific solutions",
            ),
        ],
    }

    steps = common_steps.get(request.issue_type, common_steps["general"])

    # Add context-specific step if error message provided
    if request.error_message:
        error_msg = request.error_message[:100]
        if len(request.error_message) > 100:
            error_msg += "..."
        context_step = TroubleshootingStep(
            step=len(steps) + 1,
            title="Address Specific Error",
            description=f"Error reported: {error_msg}",
            action="Contact support with this specific error message if other steps don't resolve",
        )
        steps.append(context_step)

    resources = [
        "Visit our Help Center for detailed guides",
        "Contact support if issues persist after trying these steps",
        "Check our Community Forum for similar issues and solutions",
    ]

    return TroubleshootingResponse(
        issue_type=request.issue_type, steps=steps, additional_resources=resources
    )


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


app = FastAPI(title="Single Compassionate Loop API", version="0.0.1")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Rate limit ONLY POST /check-in
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


@app.post("/troubleshoot", response_model=TroubleshootingResponse)
async def troubleshoot(request: TroubleshootingRequest) -> TroubleshootingResponse:
    """
    Provide structured troubleshooting steps based on the type of issue reported.
    Helps users systematically resolve common problems.
    """
    logger.info("troubleshooting_request", extra={"issue_type": request.issue_type})
    response = generate_troubleshooting_steps(request)
    return response


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
