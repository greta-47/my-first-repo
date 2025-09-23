# Data Classification & Measurement Scales (MVP)

> Jurisdictional anchor: British Columbia (PIPA). MVP is de-identified by default; consent-first for any sharing.

## Fields & Scales

| Field | Classification | Scale (App) | Notes |
|------|-----------------|-------------|------|
| user_id (pseudonymous) | **Low** (de-identified key) | UUID/alias | Never log raw identifiers. |
| days_since_last_checkin | **Low** | integer (0..n) | Operational adherence proxy. |
| craving | **Moderate** (health-related) | 0–10 Likert | Wording may be general or substance-specific; configurable later. |
| mood | **Moderate** | 1–5 (1=very down, 5=very up) | Trend-aware in scoring. |
| sleep | **Moderate** | quality: Poor/Average/Good; OR hours | Use the more concerning interpretation. |
| isolation | **Moderate** | none/sometimes/often | Proxy for social support / loneliness. |
| reflection text | **High** (may imply health state) | generated text | **Do not log plaintext**. |
| consents.family_sharing | **High** | boolean + timestamp | Revocable. Confirmations sent to user only (stub). |

## Retention (MVP defaults; confirm with counsel)

- **Logs (structured, no content):** 90 days  
- **Risk scores + bands:** 1 year (for outcomes analysis & safety audit)  
- **Consents:** Indefinite (until revoked; maintain history to prove consent)  

## Logging & Privacy

- JSON logs with `request_id`.  
- Strip IPs/geolocation unless essential for abuse mitigation.  
- Never log raw inputs or reflection plaintext. Store only metadata (score, band, versions).
