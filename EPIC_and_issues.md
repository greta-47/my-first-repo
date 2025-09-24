EPIC: Single Compassionate Loop MVP

- Implement rule-based check-in scoring (/check-in) with deterministic reflections
- Consent endpoints (/consents)
- Health endpoints (/healthz, /readyz) and /metrics
- Structured JSON logging and in-memory rate limiting
- CI: ruff, mypy, pip-audit (non-blocking), pytest
- Nightly pip-audit job blocking on High/Critical

Issues:
- [ ] Backend: implement MVP endpoints
- [ ] Observability: JSON logs + /metrics
- [ ] Security: rate limiting and privacy-safe behaviors
- [ ] CI: configure py312-only CI and nightly audit
- [ ] Docs: data classification and evidence briefs
