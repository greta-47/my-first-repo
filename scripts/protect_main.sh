#!/usr/bin/env bash
set -euo pipefail
REPO=${REPO:-greta-47/my-first-repo}
BRANCH=${BRANCH:-main}
cat > /tmp/protection.json <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": [] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false
}
JSON
gh api -X PUT repos/$REPO/branches/$BRANCH/protection -H "Accept: application/vnd.github+json" --input /tmp/protection.json >/dev/null
echo ok
