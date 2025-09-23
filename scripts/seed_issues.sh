#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-greta-47/my-first-repo}"
EPIC_TITLE="${EPIC_TITLE:-Epic: Single Compassionate Loop MVP}"
EPIC_BODY_FILE="${EPIC_BODY_FILE:-EPIC_and_issues.md}"
EPIC_LABELS="${EPIC_LABELS:-epic,mvp}"

if [[ ! -f "$EPIC_BODY_FILE" ]]; then
  echo "Missing $EPIC_BODY_FILE"; exit 1
fi

create_issue() {
  local title="$1"; local body="$2"; local labels="$3"
  local out url
  out="$(gh issue create -R "$REPO" -t "$title" -b "$body" -l "$labels")"
  url="$(printf '%s\n' "$out" | tail -n1 | tr -d '[:space:]')"
  printf '%s\n' "$url"
}

EPIC_OUT="$(gh issue create -R "$REPO" -t "$EPIC_TITLE" -F "$EPIC_BODY_FILE" -l "$EPIC_LABELS")"
EPIC_URL="$(printf '%s\n' "$EPIC_OUT" | tail -n1 | tr -d '[:space:]')"
EPIC_NUM="${EPIC_URL##*/}"
printf 'Epic: %s\n' "$EPIC_URL"

i1t='Risk Score v0: rule-based scoring with isolation + “No Data” state'
i1b='**Acceptance Criteria**
- Implement rule-based scoring using: adherence, mood trend, cravings, sleep, isolation.
- Add “No Data / Grace Period” for users with <3 check-ins (return `Insufficient data` state).
- Persist risk score with version metadata (e.g., `risk_score_version = "0.1.0"`).
- API returns either **band** or **Insufficient data**.
- **High Risk** escalation: append crisis footer **always** to reflections:
  > “You’re not alone. If you’re in crisis, text 988 (or your local equivalent).”

**Notes**
- Starting priors (weights): Craving **30**, Adherence **25**, Mood trend **15**, Sleep **15**, Isolation **15** (to be recalibrated).
- Bands: 0–29 Low, 30–54 Moderate, 55–74 Elevated, 75–100 High; `<3` check-ins → “Insufficient data”.

**Epic:** #'$EPIC_NUM
'
i2t='Reflection generation: deterministic templates + GPT-4o enrichment (fallback-safe)'
i2b='**Acceptance Criteria**
- Deterministic templates keyed by risk band.
- Optional GPT-4o enrichment with identifiers stripped.
- If GPT call fails or times out, use deterministic template (must **not** block check-in).
- Log `prompt_version` + `risk_score_version` for every reflection.
- Always append the crisis footer.

**Epic:** #'$EPIC_NUM
'
i3t='Consents API: family_sharing (revocable) + confirmation text (stub)'
i3b='**Acceptance Criteria**
- POST/GET `/consents` endpoint; payload includes `family_sharing` flag, timestamp, and scope.
- User can **revoke** at any time.
- When toggled **ON** → send confirmation text message to user (stubbed log only):
  > “You’ve enabled family updates. Jane Doe will receive weekly summaries unless you change this.”
- Stub only for family update (log event; no actual SMS/email yet).

**Epic:** #'$EPIC_NUM
'
i4t='Document data classification + measurement scales'
i4b='**Acceptance Criteria**
- Create `docs/data_classification.md`.
- Document measurement scales:
  - Sleep: Poor/Average/Good **OR** hours.
  - Isolation: frequency of loneliness **OR** social interactions.
  - Craving: generalized vs substance-specific wording.
- Define retention policy for each field with legal/regulatory justification (BC PIPA first principles).

**Epic:** #'$EPIC_NUM
'
i5t='Structured logging + metrics endpoints + error tracking'
i5b='**Acceptance Criteria**
- Structured JSON logs with `request_id` middleware.
- Strip IPs / geolocation unless critical.
- No plaintext logging of reflections or raw inputs.
- Metrics to track: `checkin_completion_rate`, `reflection_viewed`, `consent_toggled_count`, `risk_band_distribution`.
- Add endpoints: `/healthz`, `/readyz`, `/metrics`.
- Integrate Sentry or OTel error tracking (env-driven toggle).

**Epic:** #'$EPIC_NUM
'
i6t='Security baseline: field tagging, secrets, rate limiting, input sanitation'
i6b='**Acceptance Criteria**
- Tag sensitive fields (PII/PHI); encrypt DB at rest (provider-native).
- Manage secrets via env/secret manager.
- Pre-commit hooks: ruff, mypy, pip-audit.
- Add rate limiting to `/check-in` and `/consents`.
- Sanitize free-text inputs (e.g., mood notes).

**Epic:** #'$EPIC_NUM
'

u1="$(create_issue "$i1t" "$i1b" "mvp,backend")"
u2="$(create_issue "$i2t" "$i2b" "mvp,backend,ai")"
u3="$(create_issue "$i3t" "$i3b" "mvp,backend,privacy")"
u4="$(create_issue "$i4t" "$i4b" "mvp,docs,privacy")"
u5="$(create_issue "$i5t" "$i5b" "mvp,backend,observability")"
u6="$(create_issue "$i6t" "$i6b" "mvp,security,backend")"

gh issue comment -R "$REPO" "$EPIC_NUM" --body "$(cat <<EOF
### Child issues
- [ ] $u1
- [ ] $u2
- [ ] $u3
- [ ] $u4
- [ ] $u5
- [ ] $u6
EOF
)"
