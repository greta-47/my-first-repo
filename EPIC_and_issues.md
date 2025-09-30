EPIC: Single Compassionate Loop MVP

- Implement rule-based check-in scoring (/check-in) with deterministic reflections
- Consent endpoints (/consents)
- Health endpoints (/healthz, /readyz) and /metrics
- Structured JSON logging and in-memory rate limiting
- CI: ruff, mypy, pip-audit (non-blocking), pytest
- Nightly pip-audit job blocking on High/Critical
- Troubleshooting documentation and enhanced error responses

Issues:
- [x] Backend: implement MVP endpoints
- [x] Observability: JSON logs + /metrics
- [x] Security: rate limiting and privacy-safe behaviors
- [x] CI: configure py312-only CI and nightly audit
- [x] Docs: data classification and evidence briefs
- [x] Troubleshooting: comprehensive user guide and enhanced error handling
