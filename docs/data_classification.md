Data classification and handling

- No secrets in code or logs.
- Structured JSON logs with no PHI/PII; user identifiers are redacted.
- In-memory storage for MVP only; not for production persistence.
- Rate limiting is per-client (IP+UA hash) and returns 429 without details.
- Optional SENTRY_DSN env may be set; SDK not bundled; logs remain privacy-safe.
