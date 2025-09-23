# app/main.py
import os
import time
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# Optional Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
try:
    if SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)
except Exception:
    SENTRY_DSN = ""  # don't crash if sentry isn't available

APP_VERSION = "0.1.0"
RISK_SCORE_VERSION = "0.1.0"
PROMPT_VERSION = "0.1.0"

# --------------------------
# In-memory stores (MVP)
# --------------------------
CONSENTS: dict[str, dict[str, Any]] = {}
METRICS: dict[str, Any] = {
    "checkin_completion_count": 0,
    "reflection_viewed": 0,
    "consent_toggled_count": 0,
    "risk_band_distribution": {
        "low": 0,
        "moderate": 0,
        "elevated": 0,
        "high": 0,
        "insufficient": 0,
    },
    "app_version": APP_VERSION,
}

# Simple in-memory token bucket rate limiter per IP+route
RATE_LIMITS = {
    "/check-in:POST": (60, 60),  # 60 requests per 60 seconds
    "/consents:POST": (30, 60),
}
RATE_BUCKETS: dict[str, dict[str, Any]] = {}  # key -> {tokens, last_refill, capacity, refill_time}


def _rate_key(ip: str, route_key: str) -> str:
    return f"{ip}|{route_key}"


def rate_limit(ip: str, route_key: str):
    capacity, per = RATE_LIMITS.get(route_key, (120, 60))
    now = time.time()
    key = _rate_key(ip, route_key)
    bucket = RATE_BUCKETS.get(key)
    if not bucket:
        bucket = {"tokens": capacity, "last": now, "capacity": capacity, "per": per}
        RATE_BUCKETS[key] = bucket
    # refill
    elapsed = now - bucket["last"]
    refill = (bucket["capacity"] / bucket["per"]) * elapsed
    bucket["tokens"] = min(bucket["capacity"], bucket["tokens"] + refill)
    bucket["last"] = now
    if bucket["tokens"] < 1:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    bucket["tokens"] -= 1


# --------------------------
# Models
# --------------------------
class SleepQuality(str):
    pass  # for typing doc only


class IsolationLevel(str):
    pass


class CheckInRequest(BaseModel):
    user_id: str = Field(..., description="De-identified user key or pseudonym")
    checkins_count: int = Field(
        ..., ge=0, description="Number of historical check-ins for grace period"
    )
    # Adherence proxy: days since last check-in (0=engaged, higher=worse)
    days_since_last_checkin: int | None = Field(0, ge=0)

    # Craving 0-10 Likert (general or substance-specific – wording handled by UI)
    craving: float | None = Field(None, ge=0, le=10)

    # Mood 1-5 (1=very down, 3=neutral, 5=very up). We'll compute "risk" from low mood and downward trend.
    mood: int | None = Field(None, ge=1, le=5)
    previous_mood: int | None = Field(
        None, ge=1, le=5, description="Most recent prior mood for simple trend"
    )

    # Sleep: either quality OR hours (client can send one or both; we pick strongest risk interpretation)
    sleep_quality: Literal["poor", "average", "good"] | None = None
    sleep_hours: float | None = Field(None, ge=0, le=24)

    # Isolation: frequency of loneliness/social (mapped by UI): none/sometimes/often
    isolation_level: Literal["none", "sometimes", "often"] | None = None

    # Optional note – sanitized to avoid storing raw PHI (we will drop in logs)
    note: str | None = Field(None, max_length=500)


class CheckInResponse(BaseModel):
    risk_score_version: str
    score: int | None = None
    band: Literal["low", "moderate", "elevated", "high"] | None = None
    state: Literal["insufficient_data"] | None = None
    reflection: str
    crisis_footer: str
    prompt_version: str


class ConsentPayload(BaseModel):
    user_id: str
    family_sharing: bool
    scope: str | None = "weekly_summary"
    timestamp: str | None = None


# --------------------------
# Middleware: request_id + JSON logs
# --------------------------
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            # Minimal structured error log without inputs
            print(
                json_log(
                    {
                        "event": "error",
                        "request_id": rid,
                        "path": request.url.path,
                        "method": request.method,
                        "error": str(e),
                    }
                )
            )
            raise
        duration_ms = int((time.time() - start) * 1000)
        # Access log (do not include body, IPs)
        print(
            json_log(
                {
                    "event": "access",
                    "request_id": rid,
                    "path": request.url.path,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            )
        )
        response.headers["x-request-id"] = rid
        return response


def json_log(d: dict[str, Any]) -> str:
    d2 = dict(d)
    d2["ts"] = datetime.utcnow().isoformat() + "Z"
    d2["app_version"] = APP_VERSION
    return __import__("json").dumps(d2, ensure_ascii=False)


# --------------------------
# Scoring utilities (v0 priors)
# --------------------------
WEIGHTS = {
    "adherence": 25,
    "craving": 30,
    "mood": 15,
    "sleep": 15,
    "isolation": 15,
}


def normalize_adherence(days_since: int) -> float:
    # 0 days -> 0 risk; ≥5 days -> 100 risk (cap)
    return max(0.0, min(100.0, (days_since / 5.0) * 100.0))


def normalize_craving(craving_0_10: float | None) -> float:
    if craving_0_10 is None:
        return 0.0
    return (craving_0_10 / 10.0) * 100.0


def normalize_mood(mood_1_5: int | None, prev_1_5: int | None) -> float:
    if mood_1_5 is None:
        return 0.0
    # Base risk: lower mood -> higher risk
    base = (5 - mood_1_5) / 4.0 * 100.0  # mood=1 -> 100 risk; mood=5 -> 0
    trend_penalty = 0.0
    if prev_1_5 is not None:
        if mood_1_5 < prev_1_5:
            trend_penalty = 10.0  # simple downward trend bump
        elif mood_1_5 > prev_1_5:
            trend_penalty = -10.0  # upward trend reduces risk modestly
    return max(0.0, min(100.0, base + trend_penalty))


def normalize_sleep(quality: str | None, hours: float | None) -> float:
    vals = []
    if quality:
        mapping = {"poor": 100.0, "average": 50.0, "good": 0.0}
        vals.append(mapping.get(quality, 50.0))
    if hours is not None:
        # <6h poor; 6-8 ok; >9 may also increase risk slightly
        if hours < 6:
            vals.append(90.0)
        elif 6 <= hours <= 8:
            vals.append(20.0)
        elif 8 < hours <= 9:
            vals.append(30.0)
        else:
            vals.append(40.0)
    if not vals:
        return 0.0
    return max(vals)  # pick the more concerning interpretation


def normalize_isolation(level: str | None) -> float:
    mapping = {"none": 0.0, "sometimes": 50.0, "often": 100.0}
    return mapping.get(level or "none", 0.0)


def band_from_score(score: int) -> str:
    if score <= 29:
        return "low"
    if score <= 54:
        return "moderate"
    if score <= 74:
        return "elevated"
    return "high"


# Templates (deterministic); GPT enrichment can be added later
TEMPLATES = {
    "insufficient": "We don’t yet have enough check-ins to assess risk. Keep checking in; every entry strengthens your recovery.",
    "low": "You’re steady today. Let’s keep building on what’s working—one small healthy choice at a time.",
    "moderate": "Some stress signals showed up. What’s one support or coping tool you can use in the next hour?",
    "elevated": "Several stress points are present. Consider pausing now to breathe, text a supporter, or use a craving coping skill.",
    "high": "Today looks tough. You’re not alone—reach out to your supports now. Safety first, one step at a time.",
}
CRISIS_FOOTER = "You’re not alone. If you’re in crisis, text 988 (or your local equivalent)."

# --------------------------
# FastAPI app
# --------------------------
app = FastAPI(title="RecoveryOS MVP", version=APP_VERSION)
app.add_middleware(RequestIdMiddleware)


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/readyz")
def readyz():
    return PlainTextResponse("ready")


@app.get("/metrics")
def metrics():
    # simple JSON for MVP (Prometheus exposition can be added later)
    return JSONResponse(METRICS)


@app.post("/check-in", response_model=CheckInResponse)
async def check_in(req: Request, payload: CheckInRequest):
    client_ip = req.client.host if req.client else "unknown"
    try:
        rate_limit(client_ip, "/check-in:POST")
    except HTTPException as e:
        raise e

    # Grace period
    if payload.checkins_count < 3:
        METRICS["risk_band_distribution"]["insufficient"] += 1
        METRICS["checkin_completion_count"] += 1
        return CheckInResponse(
            risk_score_version=RISK_SCORE_VERSION,
            score=None,
            band=None,
            state="insufficient_data",
            reflection=TEMPLATES["insufficient"],
            crisis_footer=CRISIS_FOOTER,
            prompt_version=PROMPT_VERSION,
        )

    # Normalize features
    f_adherence = normalize_adherence(payload.days_since_last_checkin or 0)
    f_craving = normalize_craving(payload.craving)
    f_mood = normalize_mood(payload.mood, payload.previous_mood)
    f_sleep = normalize_sleep(payload.sleep_quality, payload.sleep_hours)
    f_isolation = normalize_isolation(payload.isolation_level)

    # Weighted sum
    score = int(
        round(
            WEIGHTS["adherence"] * f_adherence / 100.0
            + WEIGHTS["craving"] * f_craving / 100.0
            + WEIGHTS["mood"] * f_mood / 100.0
            + WEIGHTS["sleep"] * f_sleep / 100.0
            + WEIGHTS["isolation"] * f_isolation / 100.0
        )
    )

    band = band_from_score(score)
    METRICS["risk_band_distribution"][band] += 1
    METRICS["checkin_completion_count"] += 1

    # Reflection (deterministic; enrichment would go here)
    reflection = TEMPLATES[band]

    # DO NOT log plaintext user inputs or reflection; log only metadata
    print(
        json_log(
            {
                "event": "check_in_scored",
                "request_id": getattr(req.state, "request_id", None),
                "user_id_hash": hash(payload.user_id) % 10_000_000,  # pseudonymized in log
                "risk_score_version": RISK_SCORE_VERSION,
                "prompt_version": PROMPT_VERSION,
                "score": score,
                "band": band,
            }
        )
    )

    return CheckInResponse(
        risk_score_version=RISK_SCORE_VERSION,
        score=score,
        band=band,
        state=None,
        reflection=reflection,
        crisis_footer=CRISIS_FOOTER,
        prompt_version=PROMPT_VERSION,
    )


@app.get("/consents")
def get_consent(user_id: str):
    return JSONResponse(
        CONSENTS.get(user_id)
        or {
            "user_id": user_id,
            "family_sharing": False,
            "scope": "weekly_summary",
            "timestamp": None,
        }
    )


@app.post("/consents")
def set_consent(req: Request, payload: ConsentPayload):
    client_ip = req.client.host if req.client else "unknown"
    rate_limit(client_ip, "/consents:POST")

    ts = payload.timestamp or datetime.utcnow().isoformat() + "Z"
    CONSENTS[payload.user_id] = {
        "user_id": payload.user_id,
        "family_sharing": payload.family_sharing,
        "scope": payload.scope,
        "timestamp": ts,
    }
    METRICS["consent_toggled_count"] += 1

    # Stub: confirmation SMS -> log only
    if payload.family_sharing:
        confirmation = "You’ve enabled family updates. Jane Doe will receive weekly summaries unless you change this."
        print(
            json_log(
                {
                    "event": "consent_enabled_confirmation_stub",
                    "user_id_hash": hash(payload.user_id) % 10_000_000,
                    "message": confirmation,
                }
            )
        )

    return JSONResponse(CONSENTS[payload.user_id])
