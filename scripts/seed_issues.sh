#!/usr/bin/env zsh
set -euo pipefail

: "${GITHUB_TOKEN:?Set GITHUB_TOKEN}"
: "${REPO:=greta-47/my-first-repo}"

create_issue() {
  local title="$1"
  local body="$2"
  gh issue create --repo "$REPO" --title "$title" --body "$body" >/dev/null
}

create_issue "MVP endpoints: /check-in and /consents" "Implement rule-based scoring and consent storage."
create_issue "Observability: JSON logs and /metrics" "Ensure privacy-safe JSON logs and minimal metrics."
create_issue "Security: in-memory rate limiting" "Add per-client rate limiting with 429 response."
create_issue "CI: py312 ruff/mypy/pytest + pip-audit" "Non-blocking pip-audit in PR; nightly blocking job."
create_issue "Docs: data classification and evidence" "Add docs/data_classification.md and evidence briefs."

echo "Seeded issues to $REPO"
