# Epic: Single Compassionate Loop MVP

**Goal:** user check-in → risk score → supportive reflection → optional family update (with consent).

**Parent label:** `epic`  
**Proposed Epic issue title:** *Single Compassionate Loop MVP*

---

## ✅ Child Issues

### 1) 📊 Risk Score v0 (with Isolation + No Data State)
**Title:** Risk Score v0: rule-based scoring with isolation + “No Data” state  
**Parent:** _link this issue to the Epic above_

**Acceptance Criteria**
- Implement rule-based scoring using: adherence, mood trend, cravings, sleep, isolation.
- Add “No Data / Grace Period” for users with <3 check-ins (return `Insufficient data` state).
- Persist risk score with version metadata (e.g., `risk_score_version = "0.1.0"`).
- API returns either **band** or **Insufficient data**.
- **High Risk** escalation: append crisis footer **always** to reflections:
  > “You’re not alone. If you’re in crisis, text 988 (or your local equivalent).”

**Notes**
- Starting priors (weights): Craving **30**, Adherence **25**, Mood trend **15**, Sleep **15**, Isolation **15** (to be recalibrated).
- Bands: 0–29 Low, 30–54 Moderate, 55–74 Elevated, 75–100 High; `<3` check-ins → “Insufficient data”.

---

### 2) 💬 Supportive Reflection Generation
**Title:** Reflection generation: deterministic templates + GPT-4o enrichment (fallback-safe)  
**Parent:** Epic

**Acceptance Criteria**
- Deterministic templates keyed by risk band.
- Optional GPT-4o enrichment with identifiers stripped.
- If GPT call fails or times out, use deterministic template (must **not** block check-in).
- Log `prompt_version` + `risk_score_version` for every reflection.
- Always append the crisis footer.

---

### 3) 🛡️ Consent & Family Sharing (Revocable, Text Only)
**Title:** Consents API: family_sharing (revocable) + confirmation SMS (stub)  
**Parent:** Epic

**Acceptance Criteria**
- POST/GET `/consents` endpoint; payload includes `family_sharing` flag, timestamp, and scope.
- User can **revoke** at any time.
- When toggled **ON** → send confirmation text message to user (stubbed log only):
  > “You’ve enabled family updates. Jane Doe will receive weekly summaries unless you change this.”
- Stub only for family update (log event; no actual SMS/email yet).

---

### 4) 📑 Data Classification Matrix
**Title:** Document data classification + measurement scales  
**Parent:** Epic

**Acceptance Criteria**
- Create `docs/data_classification.md`.
- Document measurement scales:
  - Sleep: Poor/Average/Good **OR** hours.
  - Isolation: frequency of loneliness **OR** social interactions.
  - Craving: generalized vs substance-specific wording.
- Define retention policy for each field with legal/regulatory justification (BC PIPA first principles).

---

### 5) 📈 Logging & Metrics
**Title:** Structured logging + metrics endpoints (healthz/readyz/metrics) + error tracking  
**Parent:** Epic

**Acceptance Criteria**
- Structured JSON logs with `request_id` middleware.
- Strip IPs / geolocation unless critical.
- No plaintext logging of reflections or raw inputs.
- Metrics to track: `checkin_completion_rate`, `reflection_viewed`, `consent_toggled_count`, `risk_band_distribution`.
- Add endpoints: `/healthz`, `/readyz`, `/metrics`.
- Integrate Sentry or OTel error tracking (env-driven toggle).

---

### 6) 🔐 Security Baseline
**Title:** Security baseline: field tagging, secrets, rate limiting, input sanitation  
**Parent:** Epic

**Acceptance Criteria**
- Tag sensitive fields (PII/PHI); encrypt DB at rest (provider-native).
- Manage secrets via env/secret manager.
- Pre-commit hooks: ruff, mypy, pip-audit.
- Add rate limiting to `/check-in` and `/consents`.
- Sanitize free-text inputs (e.g., mood notes).

---

## ❓ Open Questions (track as Epic comments)
- Escalation: Is the crisis footer enough at MVP, or do we stub a human escalation path?
- Craving: Should it be configurable per substance?
- Scales: Confirm final scales for sleep + isolation.
- Reflection fallback: Cache last reflection or always show a generic supportive one?
- Retention: Confirm basis for **90-day logs**, **1-year scores**, **indefinite consents**.

---

## Dev Notes
- Risk score version: `0.1.0`
- Reflection prompt version: `0.1.0`
- Deterministic templates live in code under `templates/` (or embed in app for MVP).
- Rate limiting: allowlist internal IPs if needed for testing.
