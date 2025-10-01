Data classification and handling

- No secrets in code or logs.
- Structured JSON logs with no PHI/PII; user identifiers are redacted.
- In-memory storage for MVP only; not for production persistence.
- Rate limiting is per-client (IP+UA hash) and returns 429 without details.
- Optional SENTRY_DSN env may be set; SDK not bundled; logs remain privacy-safe.

## API Endpoints

### Core endpoints
- `/check-in` - Submit check-in data for scoring and feedback
- `/consents` - Manage user consent records
- `/healthz`, `/readyz`, `/metrics` - Health and monitoring

### Support endpoints
- `/troubleshoot` - Get structured troubleshooting steps for common issues
  - Supports issue types: login, connection, data, performance, general
  - Returns step-by-step guidance with actions and resources
  - Includes context-specific steps when error messages are provided
