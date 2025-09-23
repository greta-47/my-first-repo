# Security Policy

## Logging Practices

This application implements strict logging practices to protect user privacy:

- **No plaintext user inputs**: User-provided data (mood notes, reflections, personal information) is never logged in plaintext
- **Pseudonymized identifiers**: User IDs are hashed before logging (`hash(user_id) % 10_000_000`)
- **Metadata only**: Only risk scores, bands, versions, and request metadata are logged
- **Structured logging**: All logs use JSON format with timestamps and request IDs for traceability

## Rate Limiting

Rate limiting is implemented on sensitive endpoints to prevent abuse:

- `/check-in` endpoint: 60 requests per 60 seconds per IP address
- `/consents` endpoint: 30 requests per 60 seconds per IP address
- Token bucket algorithm with automatic refill
- Returns HTTP 429 "Too Many Requests" when limits exceeded

## Secrets Management

- **SENTRY_DSN**: Optional environment variable, disabled by default
- **No hardcoded secrets**: All sensitive configuration via environment variables
- **Graceful degradation**: Application continues to function if optional secrets are missing
- **Error isolation**: Sentry initialization failures don't crash the application

## PII/PHI Stance

This application handles sensitive health information with strict privacy controls:

- **Data minimization**: Only essential data points are collected and processed
- **In-memory storage**: MVP uses in-memory storage (no persistent database)
- **No reflection storage**: Generated reflections are returned but not persisted
- **Consent management**: Users can revoke family sharing consent at any time
- **Crisis safety**: Crisis resources always provided regardless of risk level

## Data Handling

- **Risk scores**: Calculated and returned but not permanently stored in MVP
- **Consents**: Stored with timestamps and can be revoked
- **Metrics**: Aggregated counts only, no individual user data
- **Request isolation**: Each request processed independently with unique request IDs

## Vulnerability Reporting

Please report security vulnerabilities by creating an issue in this repository. Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested mitigation if known

## Security Headers

The application implements security headers via middleware:

- Content Security Policy (CSP)
- HTTPS enforcement (configurable)
- CORS controls with explicit origin allowlisting
- Security headers for XSS and clickjacking protection

## Audit Trail

- All check-ins logged with risk score metadata
- Consent changes tracked with timestamps
- Request IDs for correlation across logs
- No sensitive user data in audit logs

## Safe Testing

Do not access data you do not own. Avoid destructive testing. Respect rate limits.

## Scope

Code and configurations in this repository and deployed services controlled by this project.

## Supported Versions

- main: supported
- pre-release branches: best effort
