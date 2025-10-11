from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Deque, Dict, List, Literal, Optional, Tuple, TypedDict

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.responses import Response as StarletteResponse

APP_START_TS = time.time()

MAX_ERROR_MESSAGE_LENGTH = 100


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
        import sentry_sdk  # type: ignore[import-untyped]

        # Keep lightweight: no performance tracing; error-only.
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)  # type: ignore
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

# Note: we intentionally do NOT touch Uvicorn access logs here;
# Ensure deployment config avoids IP/UA in sinks.


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


class TroubleshootPayload(BaseModel):
    issue_type: str = Field(min_length=1, max_length=100)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    user_context: Optional[str] = Field(default=None, max_length=500)


class TroubleshootStep(BaseModel):
    step_number: int
    title: str
    description: str
    action: str


class TroubleshootResponse(BaseModel):
    issue_type: str
    identified_issue: str
    steps: List[TroubleshootStep]
    additional_resources: List[str]


class ErrorDetail(BaseModel):
    type: str
    title: str
    detail: Optional[str] = None
    code: str
    help_url: Optional[str] = None


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorDetail
    meta: Optional[Dict[str, str]] = None


class HelpEndpoint(BaseModel):
    name: str
    description: str
    url: str
    status_codes: List[str]


class HelpResponse(BaseModel):
    api_version: str
    documentation_url: str
    support_contact: str
    endpoints: List[HelpEndpoint]
    error_types: Dict[str, str]
    troubleshooting: Dict[str, str]


HELP_ENDPOINTS_CATALOG: List[HelpEndpoint] = [
    HelpEndpoint(
        name="POST /check-in",
        description="Submit mental health check-in data and receive risk scoring",
        url="https://docs.recoveryos.org/api/check-in",
        status_codes=["200", "400", "422", "429"],
    ),
    HelpEndpoint(
        name="POST /consents",
        description="Record user consent for data processing",
        url="https://docs.recoveryos.org/api/consents",
        status_codes=["200", "400"],
    ),
    HelpEndpoint(
        name="GET /consents/{user_id}",
        description="Retrieve consent record for a specific user",
        url="https://docs.recoveryos.org/api/consents",
        status_codes=["200", "404"],
    ),
    HelpEndpoint(
        name="GET /healthz",
        description="Health check endpoint for monitoring",
        url="https://docs.recoveryos.org/api/health",
        status_codes=["200"],
    ),
    HelpEndpoint(
        name="GET /readyz",
        description="Readiness check with system status",
        url="https://docs.recoveryos.org/api/health",
        status_codes=["200"],
    ),
    HelpEndpoint(
        name="GET /metrics",
        description="Prometheus-compatible metrics endpoint",
        url="https://docs.recoveryos.org/api/metrics",
        status_codes=["200"],
    ),
]
HELP_ERROR_TYPES: Dict[str, str] = {
    "validation": "https://docs.recoveryos.org/api/validation-errors",
    "business-rule": "https://docs.recoveryos.org/api/business-logic-errors",
    "rate-limit": "https://docs.recoveryos.org/api/rate-limiting",
    "not-found": "https://docs.recoveryos.org/api/not-found-errors",
    "authorization": "https://docs.recoveryos.org/api/authorization-errors",
}
HELP_TROUBLESHOOTING_GUIDANCE: Dict[str, str] = {
    "rate_limited": (
        "If you're hitting rate limits, wait 10 seconds between check-in requests. "
        "Each client is limited to 5 requests per 10-second window."
    ),
    "insufficient_data": (
        "Risk scoring requires at least 3 check-ins. "
        "Continue submitting check-ins to receive meaningful risk assessment."
    ),
    "validation_failed": (
        "Check that all required fields are present and within valid ranges. "
        "See endpoint documentation for field specifications."
    ),
    "consent_not_found": (
        "Ensure a consent record has been created before attempting to retrieve it."
    ),
    "high_risk_response": (
        "High-risk responses include crisis messaging. "
        "If you're in danger, contact emergency services immediately."
    ),
}


def create_error_response(
    error_type: str,
    title: str,
    detail: Optional[str] = None,
    code: str = "",
    help_url: Optional[str] = None,
    status_code: int = 400,
) -> JSONResponse:
    """Create a standardized error response following Problem Details format."""
    error_detail = ErrorDetail(
        type=f"https://recoveryos.org/errors/{error_type}",
        title=title,
        detail=detail,
        code=code,
        help_url=help_url or f"https://docs.recoveryos.org/api/{error_type}",
    )
    error_response = ErrorResponse(
        error=error_detail,
        meta={
            "timestamp": iso_now(),
            "request_id": "redacted",
        },
    )
    content = error_response.model_dump()
    content["help_url"] = error_detail.help_url
    return JSONResponse(status_code=status_code, content=content)


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


class TroubleshootConfig(TypedDict):
    identified_issue: str
    steps: List[TroubleshootStep]
    additional_resources: List[str]


def generate_troubleshoot_steps(
    issue_type: str, error_message: Optional[str] = None
) -> TroubleshootResponse:
    """
    Generate structured troubleshooting steps for common issues.
    Privacy-first: no user data is logged, only issue types and structured responses.
    """
    # Normalize issue type for matching
    normalized_issue = issue_type.lower().strip()

    # Define troubleshooting knowledge base
    troubleshoot_db: Dict[str, TroubleshootConfig] = {
        "login": {
            "identified_issue": "Authentication or login difficulties",
            "steps": [
                TroubleshootStep(
                    step_number=1,
                    title="Verify credentials",
                    description="Check username and password",
                    action="Re-enter login credentials carefully",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Clear browser cache",
                    description="Browser data may be corrupted",
                    action="Clear cache and cookies for this site",
                ),
                TroubleshootStep(
                    step_number=3,
                    title="Try different browser",
                    description="Browser-specific issues may occur",
                    action="Use Chrome, Firefox, or Safari",
                ),
                TroubleshootStep(
                    step_number=4,
                    title="Check internet connection",
                    description="Verify network connectivity",
                    action="Test with other websites",
                ),
            ],
            "additional_resources": [
                "Password reset link available on login page",
                "Contact support if issues persist",
            ],
        },
        "check-in": {
            "identified_issue": "Issues with submitting or viewing check-ins",
            "steps": [
                TroubleshootStep(
                    step_number=1,
                    title="Validate input data",
                    description="Check all required fields are filled",
                    action="Ensure all values are within expected ranges",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Check rate limits",
                    description="Too many requests may be blocked",
                    action="Wait a few seconds before retrying",
                ),
                TroubleshootStep(
                    step_number=3,
                    title="Refresh the page",
                    description="Clear any temporary state issues",
                    action="Reload the page and try again",
                ),
                TroubleshootStep(
                    step_number=4,
                    title="Verify consent status",
                    description="Check if consent has been given",
                    action="Complete consent process if required",
                ),
            ],
            "additional_resources": [
                "Check-in requires 3 submissions before scoring",
                "Contact support for persistent issues",
            ],
        },
        "consent": {
            "identified_issue": "Problems with consent management",
            "steps": [
                TroubleshootStep(
                    step_number=1,
                    title="Review terms",
                    description="Ensure you understand the consent terms",
                    action="Read the terms and conditions carefully",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Check required fields",
                    description="All consent fields must be completed",
                    action="Verify user ID and terms version are provided",
                ),
                TroubleshootStep(
                    step_number=3,
                    title="Refresh consent status",
                    description="Check current consent state",
                    action="Use the consent lookup endpoint",
                ),
                TroubleshootStep(
                    step_number=4,
                    title="Re-submit consent",
                    description="Clear and resubmit consent data",
                    action="Submit new consent with correct information",
                ),
            ],
            "additional_resources": [
                "Consent can be updated at any time",
                "Terms version must match current system version",
            ],
        },
        "network": {
            "identified_issue": "Network connectivity or API communication issues",
            "steps": [
                TroubleshootStep(
                    step_number=1,
                    title="Check internet connection",
                    description="Verify basic connectivity",
                    action="Test internet access with other sites",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Try different network",
                    description="Switch networks if possible",
                    action="Use mobile data or different WiFi",
                ),
                TroubleshootStep(
                    step_number=3,
                    title="Check service status",
                    description="Verify API availability",
                    action="Check system status page or contact support",
                ),
                TroubleshootStep(
                    step_number=4,
                    title="Review request format",
                    description="Ensure API calls are properly formatted",
                    action="Verify request headers and data structure",
                ),
            ],
            "additional_resources": [
                "API documentation available for developers",
                "Service status updates posted on status page",
            ],
        },
    }

    # Find matching issue type or provide generic response
    config: TroubleshootConfig
    if normalized_issue in troubleshoot_db:
        config = troubleshoot_db[normalized_issue]
    elif any(key in normalized_issue for key in troubleshoot_db.keys()):
        # Partial match - find the best match
        best_match = next(
            (key for key in troubleshoot_db.keys() if key in normalized_issue), "login"
        )
        config = troubleshoot_db[best_match]
    else:
        # Generic troubleshooting steps for unknown issues
        config = {
            "identified_issue": "General technical difficulties",
            "steps": [
                TroubleshootStep(
                    step_number=1,
                    title="Refresh the page",
                    description="Clear temporary browser state",
                    action="Reload the current page",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Clear browser cache",
                    description="Remove stored data that may be corrupted",
                    action="Clear cache and cookies",
                ),
                TroubleshootStep(
                    step_number=3,
                    title="Try different browser",
                    description="Browser compatibility issues",
                    action="Use a different web browser",
                ),
                TroubleshootStep(
                    step_number=4,
                    title="Check system requirements",
                    description="Verify browser and system compatibility",
                    action="Ensure using supported browser version",
                ),
                TroubleshootStep(
                    step_number=5,
                    title="Contact support",
                    description="Get personalized assistance",
                    action="Provide specific error details to support team",
                ),
            ],
            "additional_resources": [
                "System requirements documentation available",
                "Support available during business hours",
            ],
        }

    return TroubleshootResponse(
        issue_type=issue_type,
        identified_issue=config["identified_issue"],
        steps=config["steps"],
        additional_resources=config["additional_resources"],
    )


APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
app = FastAPI(title="Single Compassionate Loop API", version=APP_VERSION)


@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[StarletteResponse]],
) -> StarletteResponse:
    # Rate limit ONLY POST /check-in
    if request.method.upper() == "POST" and request.url.path == "/check-in":
        key = get_rate_key(request)
        if not RATE_LIMIT.allow(key):
            logger.info("rate_limited")
            return create_error_response(
                error_type="rate-limit",
                title="Rate Limit Exceeded",
                detail="Maximum 5 check-ins per 10 seconds allowed",
                code="E_RATE_LIMITED",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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


@app.get("/help", response_model=HelpResponse)
async def help_endpoint() -> HelpResponse:
    return HelpResponse(
        api_version=APP_VERSION,
        documentation_url="https://docs.recoveryos.org/api",
        support_contact="support@recoveryos.org",
        endpoints=HELP_ENDPOINTS_CATALOG,
        error_types=HELP_ERROR_TYPES,
        troubleshooting=HELP_TROUBLESHOOTING_GUIDANCE,
    )


@app.get("/version")
def version() -> dict:
    return {"app_version": APP_VERSION}


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


@app.get("/consents/{user_id}", response_model=ConsentRecord)
async def get_consents(user_id: str):
    c = CONSENTS.get(user_id)
    if not c:
        return create_error_response(
            error_type="not-found",
            title="Consent Record Not Found",
            detail="No consent record found for user ID",
            code="E_CONSENT_NOT_FOUND",
            status_code=404,
        )
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


@app.post("/troubleshoot", response_model=TroubleshootResponse)
async def troubleshoot(payload: TroubleshootPayload) -> TroubleshootResponse:
    """
    Provide structured troubleshooting steps for common issues.
    Privacy-first: logs only issue type categories, never user data.
    """
    try:
        # Generate troubleshooting response
        response = generate_troubleshoot_steps(payload.issue_type, payload.error_message)

        # Privacy-safe logging: log only sanitized issue type and step count
        issue_category = payload.issue_type.lower().strip()[:20]  # Truncate for logging
        logger.info(
            "troubleshoot_requested %s",
            json.dumps(
                {
                    "issue_category": issue_category,
                    "steps_provided": len(response.steps),
                    "has_error_msg": payload.error_message is not None,
                    "has_context": payload.user_context is not None,
                },
                separators=(",", ":"),
            ),
        )

        return response

    except Exception as e:
        # Enhanced logging for debugging unexpected behaviors (no user content logged)
        logger.error(
            "troubleshoot_error %s",
            json.dumps(
                {
                    "issue_category": payload.issue_type.lower().strip()[:20],
                    "error_type": type(e).__name__,
                    "has_error_msg": payload.error_message is not None,
                    "error_msg_length": len(payload.error_message) if payload.error_message else 0,
                },
                separators=(",", ":"),
            ),
        )

        # Return generic fallback response
        return TroubleshootResponse(
            issue_type=payload.issue_type,
            identified_issue="Technical difficulties encountered",
            steps=[
                TroubleshootStep(
                    step_number=1,
                    title="Refresh and retry",
                    description="Clear current state and try again",
                    action="Reload the page and resubmit",
                ),
                TroubleshootStep(
                    step_number=2,
                    title="Contact support",
                    description="Get assistance with technical issues",
                    action="Provide error details to support team",
                ),
            ],
            additional_resources=["Support available during business hours"],
        )
