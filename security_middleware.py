# security_middleware.py
from dataclasses import dataclass
from typing import Iterable, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send

# If you already have Settings in settings.py, import it; otherwise inline a minimal shim.
try:
    from settings import Settings  # expects .CSP_REPORT_ONLY: bool
except ImportError:

    @dataclass
    class _Settings:
        CSP_REPORT_ONLY: bool = False

    Settings = _Settings  # type: ignore[assignment]


# --- Strict default CSP used for all API routes ---
def build_strict_csp() -> str:
    parts = {
        "default-src": "'none'",
        "base-uri": "'none'",
        "object-src": "'none'",
        "frame-ancestors": "'none'",
        "img-src": "'self'",
        "font-src": "'self'",
        "connect-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self'",
    }
    return "; ".join(f"{k} {v}" for k, v in parts.items())


# --- Relaxed CSP ONLY for Swagger docs assets ---
def build_docs_csp() -> str:
    parts = {
        "default-src": "'none'",
        "base-uri": "'none'",
        "object-src": "'none'",
        "frame-ancestors": "'none'",
        "img-src": "'self' data:",
        "font-src": "'self'",
        "connect-src": "'self'",
        "script-src": "'self' https://cdn.jsdelivr.net",
        "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    }
    return "; ".join(f"{k} {v}" for k, v in parts.items())


DOCS_PATHS: Tuple[str, ...] = (
    "/docs",
    "/docs/",
    "/docs/oauth2-redirect",
    "/openapi.json",
)


class SecurityHeadersMiddleware:
    """
    Adds CSP headers (strict by default), with a docs-only override so /docs works.
    If Settings.CSP_REPORT_ONLY is True, emits Content-Security-Policy-Report-Only instead.
    """

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self.settings = settings or Settings()
        self._strict_csp = build_strict_csp()
        self._docs_csp = build_docs_csp()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        use_docs_csp = any(path.startswith(p) for p in DOCS_PATHS)

        header_name = (
            b"content-security-policy-report-only"
            if self.settings.CSP_REPORT_ONLY
            else b"content-security-policy"
        )
        policy_value = (self._docs_csp if use_docs_csp else self._strict_csp).encode("utf-8")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers: Iterable[Tuple[bytes, bytes]] = message.get("headers", [])
                # Filter out any pre-existing CSP header
                filtered = [
                    (k, v)
                    for (k, v) in headers
                    if k.lower()
                    not in (
                        b"content-security-policy",
                        b"content-security-policy-report-only",
                    )
                ]
                message = {
                    **message,
                    "headers": list(filtered) + [(header_name, policy_value)],
                }
            await send(message)

        await self.app(scope, receive, send_wrapper)
