# CI/CD Workflow Documentation

This document describes the conventions, patterns, and design decisions for the GitHub Actions deployment workflow in this repository.

## Overview

The deployment workflow (`.github/workflows/deploy.yml`) handles building, testing, and deploying the RecoveryOS API to DigitalOcean App Platform. It follows a robust, production-ready approach with comprehensive error handling, progress logging, and automated verification.

## Workflow Architecture

### Single Image Strategy

The workflow builds a single Docker image used for both the API service and database migrations. This approach provides several benefits:

- **Eliminates drift**: API and migration code always come from the same artifact
- **Faster builds**: One image build instead of two (halves build time)
- **Simpler pipeline**: Fewer moving parts to debug and maintain
- **Guaranteed consistency**: Code and DB schema are always in sync

**Implementation**: The same image is pushed to GHCR with two tags (`:latest` and `:${{ github.sha }}`), and both the API service and migrate job reference this single image in `.do/app.yaml`.

### Docker Build and Push

**Location**: Lines 31-41 in `deploy.yml`

**Tags pushed to GHCR**:
- `ghcr.io/greta-47/my-first-repo:latest` - Always points to the most recent main branch build
- `ghcr.io/greta-47/my-first-repo:${{ github.sha }}` - Immutable tag for specific commit

**Why both tags**: 
- `:latest` simplifies local development and testing
- `:${{ github.sha }}` enables deterministic rollbacks and audit trails

**Cache strategy**: Uses GitHub Actions cache (`type=gha`) to speed up subsequent builds by reusing layers.

## Deployment ID Extraction

### Three-Tier Fallback Strategy

The workflow uses a robust three-tier strategy to capture the deployment ID from DigitalOcean, handling API inconsistencies gracefully.

**Location**: Lines 193-239 in `deploy.yml`

#### Strategy 1: Parse from `doctl apps update` JSON output

```bash
DEPLOY_JSON=$(doctl apps update "$APP_ID" --spec .do/app-deploy.yaml -o json 2>&1 || true)
DEPLOYMENT_ID=$(echo "$DEPLOY_JSON" | jq -er '.active_deployment.id // .pending_deployment.id // empty' 2>/dev/null || true)
```

**Why it might fail**: The `doctl apps update` command doesn't always include deployment ID in its JSON response, depending on the doctl version and API response format.

#### Strategy 2: Use `doctl apps create-deployment` (if available)

```bash
if [ "${{ env.DOCTL_HAS_CREATE_DEPLOYMENT }}" = "true" ]; then
  CREATE_JSON=$(doctl apps create-deployment "$APP_ID" -o json 2>&1 || true)
  DEPLOYMENT_ID=$(echo "$CREATE_JSON" | jq -er '.id // empty' 2>/dev/null || true)
fi
```

**Why it might fail**: The `create-deployment` command was added in later doctl versions and may not be available in v1.146.0.

#### Strategy 3: List deployments and get most recent

```bash
LIST_JSON=$(doctl apps list-deployments "$APP_ID" -o json 2>&1 || true)
DEPLOYMENT_ID=$(echo "$LIST_JSON" | jq -er 'sort_by(.created_at // .CreatedAt) | last | .id // empty' 2>/dev/null || true)
```

**Why this works**: This fallback always succeeds because it queries the deployment list and sorts by creation timestamp to get the most recent deployment.

**Retry logic**: Strategy 3 includes a 3-attempt retry loop with 2-second delays to handle API propagation delays.

### Architectural Alignment

This three-tier approach aligns with the production deployment principle of **migration retry logic with exponential backoff**. While not exponential in this case, it demonstrates the same pattern: handle transient failures gracefully with multiple fallback strategies.

## Deployment Polling

### Progress Tracking

**Location**: Lines 245-298 in `deploy.yml`

The polling script monitors deployment progress with time-based percentage calculation:

```bash
PERCENT=$((ELAPSED * 100 / TIMEOUT_SECONDS))
REMAINING=$((TIMEOUT_SECONDS - ELAPSED))
echo "[$i/$MAX_ITERATIONS | ~${PERCENT}% of timeout] Phase: $PHASE | Elapsed: ${ELAPSED}s | ETA: ~${REMAINING}s remaining"
```

**Configuration**:
- **Timeout**: 15 minutes (900 seconds)
- **Poll interval**: 10 seconds
- **Max iterations**: 90 (90 × 10s = 900s)

**Why time-based percentage**: DigitalOcean doesn't provide deployment progress percentage, so we calculate based on elapsed time vs. timeout. This gives users a sense of progress even when the deployment phase doesn't change frequently.

### Terminal State Detection

The polling script correctly handles all terminal deployment states:

| Phase | Exit Code | Log Prefix | Description |
|-------|-----------|------------|-------------|
| `ACTIVE` | 0 | `[SUCCESS]` | Deployment completed successfully |
| `ERROR` | 1 | `[FAILED]` | Deployment failed with error |
| `FAILED` | 1 | `[FAILED]` | Deployment failed |
| `CANCELED` | 1 | `[FAILED]` | Deployment was canceled |
| `CANCELLED` | 1 | `[FAILED]` | Deployment was cancelled (UK spelling) |
| `UNKNOWN` | - | `[WARN]` | API unavailable, continues polling |

**Why handle both spellings**: DigitalOcean API may return either `CANCELED` or `CANCELLED` depending on the API version.

## Logging Conventions

### Plain Text Prefixes (No Emojis)

All log messages use plain text prefixes for better CI log readability and parsing:

- `[OK]` - Successful operation or validation
- `[WARN]` - Warning that doesn't block execution
- `[FAILED]` - Operation failed, workflow will exit
- `[SUCCESS]` - Terminal success state

**Why no emojis**: Emojis can cause rendering issues in CI logs, make logs harder to grep/parse, and don't work well in all terminals. Plain text prefixes are more professional and universally compatible.

### Structured Logging

All deployment steps follow a consistent logging pattern:

1. **Announce action**: "Initiating deployment..."
2. **Show progress**: "Attempting to extract deployment ID from update command..."
3. **Report result**: "[OK] Deployment ID from update: abc123"
4. **Provide context**: "Monitor progress at: https://cloud.digitalocean.com/apps/..."

This structure makes it easy to follow deployment progress in CI logs and debug issues.

## Pre-Deploy Validation

### Sanity Checks

**Location**: Lines 84-132 in `deploy.yml`

The workflow performs comprehensive pre-deploy validation before attempting deployment:

1. **File existence**: Verify `.do/app.yaml` exists
2. **YAML syntax**: Validate YAML is parseable
3. **Service port**: Confirm port is 8000 (matches Dockerfile EXPOSE)
4. **Image registry**: Verify GHCR registry and repository are configured
5. **Migrate job**: Confirm migrate job exists with correct configuration

**Why validate before deploy**: Catching configuration errors early prevents failed deployments and wasted CI time. These checks run in seconds and can save 5-10 minutes of deployment time.

### Post-Mutation Validation

**Location**: Lines 165-190 in `deploy.yml`

After mutating the app spec with the new image tag, the workflow validates the mutation succeeded:

1. **API service image**: Verify registry_type, registry, repository, and tag
2. **Migrate job image**: Verify registry_type, registry, repository, and tag

**Why validate mutations**: The `yq` mutation could fail silently or produce incorrect output. Explicit validation ensures the deployment spec is correct before sending to DigitalOcean.

## Error Handling

### Bash Strict Mode

All deployment steps use bash strict mode for better error handling:

```bash
set -Eeuo pipefail
IFS=$'\n\t'
```

**What this does**:
- `-e`: Exit on any command failure
- `-E`: Inherit ERR trap in functions
- `-u`: Exit on undefined variable usage
- `-o pipefail`: Exit if any command in a pipeline fails
- `IFS=$'\n\t'`: Prevent word splitting on spaces

### Error Handler Function

```bash
die() {
  echo "Error: $1" >&2
  exit 1
}
```

**Usage**: `[ -n "$DEPLOYMENT_ID" ] || die "Could not retrieve deployment ID"`

**Why use die()**: Provides consistent error messaging and ensures errors are written to stderr for proper log filtering.

### Cleanup Trap

**Location**: Line 147 in `deploy.yml`

```bash
trap 'rm -f .do/app-deploy.yaml' EXIT
```

**What this does**: Automatically removes the temporary deployment spec file when the script exits, even if it exits due to an error.

**Belt-and-suspenders approach**: A separate cleanup step (lines 300-310) also runs with `if: always()` to ensure cleanup happens even if the trap fails.

## Dependency Management

### Runtime Dependency Detection

**Location**: Lines 66-82 in `deploy.yml`

The workflow detects and installs required dependencies:

1. **jq**: Required for parsing JSON output from doctl
   - Checks if installed: `command -v jq`
   - Installs if missing: `apt-get install -y jq`

2. **doctl capabilities**: Detects which commands are available
   - Checks for `create-deployment`: `doctl apps --help | grep -q 'create-deployment'`
   - Sets environment variable: `DOCTL_HAS_CREATE_DEPLOYMENT=true/false`

**Why detect capabilities**: Different doctl versions have different commands. Detecting capabilities allows the workflow to adapt to the installed version.

## App Spec Mutation Strategy

### Name-Based Selection (Not Index-Based)

**Location**: Lines 160-163 in `deploy.yml`

```yaml
yq eval '
  (.services[] | select(.name == "api") | .image.tag) = "${{ github.sha }}" |
  (.jobs[] | select(.name == "migrate") | .image.tag) = "${{ github.sha }}"
' .do/app.yaml > .do/app-deploy.yaml
```

**Why name-based**: Using `.services[0]` would break if service order changes in `app.yaml`. Selecting by name (`select(.name == "api")`) is robust to reordering.

**Why mutate instead of templating**: The base `app.yaml` contains all configuration. Mutating just the image tag preserves all other settings and makes the workflow simpler.

## Secrets Management

### Required Secrets

The workflow requires two GitHub secrets:

1. **DIGITALOCEAN_ACCESS_TOKEN**: DigitalOcean Personal Access Token with read+write permissions
2. **DIGITALOCEAN_APP_ID**: The UUID of the DigitalOcean App Platform app

**Security considerations**:
- Secrets are never logged or echoed
- App ID is masked in logs with `***`
- Secrets are only accessible in the `deploy` job (not in other jobs)

### Secret Validation

**Location**: Lines 150-154 in `deploy.yml`

```bash
if [ -z "$APP_ID" ]; then
  die "DIGITALOCEAN_APP_ID secret not set. Create app first: doctl apps create --spec .do/app.yaml"
fi
```

**Why validate**: Provides clear error message with remediation steps if secrets are missing.

## Workflow Triggers

The workflow runs on:

1. **Push to main**: Automatic deployment on every main branch push
2. **Manual dispatch**: Can be triggered manually via GitHub Actions UI

**Why these triggers**: 
- Push to main enables continuous deployment
- Manual dispatch allows deploying specific commits or testing the workflow

## Health Check Configuration

The app spec (`.do/app.yaml`) configures health checks:

```yaml
health_check:
  http_path: /healthz
  initial_delay_seconds: 10
  period_seconds: 30
  timeout_seconds: 5
  success_threshold: 1
  failure_threshold: 3
```

**What this means**:
- DigitalOcean waits 10 seconds after container start before first health check
- Checks `/healthz` endpoint every 30 seconds
- Considers deployment healthy after 1 successful check
- Marks deployment failed after 3 consecutive failures

**Alignment with FastAPI**: The FastAPI app listens on `0.0.0.0:8000` and exposes `/healthz`, which now asserts database connectivity and returns HTTP 503 if the DB is unavailable.

## Migration Strategy

### Pre-Deploy Migration Job

**Location**: Lines 82-98 in `.do/app.yaml`

```yaml
jobs:
  - name: migrate
    kind: PRE_DEPLOY
    image:
      registry_type: GHCR
      registry: greta-47
      repository: my-first-repo
      tag: latest
    run_command: /app/scripts/migrate.sh
```

**What this does**: Runs database migrations before deploying the new API version.

**Why PRE_DEPLOY**: Ensures migrations complete successfully before traffic is routed to the new version. If migrations fail, deployment is rolled back automatically.

**Single image approach**: The migrate job uses the same image as the API service, just with a different entrypoint (`/app/scripts/migrate.sh`). This eliminates drift between API and migration code.

## Rollback Strategy

### Immutable Image Tags

Every deployment uses an immutable image tag based on the git commit SHA:

```
ghcr.io/greta-47/my-first-repo:80f9616a030c31685465633185025cdeb9fa313e
```

**Why immutable tags**: Enables deterministic rollbacks. To rollback, simply update `.do/app.yaml` with the previous commit SHA and redeploy.

### Rollback Process

1. Find the previous successful deployment commit SHA
2. Update `.do/app.yaml` with that SHA: `tag: <previous-sha>`
3. Run: `doctl apps update $APP_ID --spec .do/app.yaml`
4. Or trigger the workflow manually with the previous commit

## Performance Optimizations

### Docker Build Cache

**Location**: Lines 40-41 in `deploy.yml`

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

**What this does**: Caches Docker layers in GitHub Actions cache, speeding up subsequent builds by reusing unchanged layers.

**Impact**: Can reduce build time from 5-10 minutes to 1-2 minutes for incremental changes.

### Parallel Execution

The workflow uses GitHub Actions job dependencies to parallelize where possible:

- Build and push Docker image (runs first)
- Deploy to DigitalOcean (waits for build)
- Wait for deployment (waits for deploy)
- Cleanup (always runs, even on failure)

## Monitoring and Observability

### Deployment Monitoring

The workflow provides multiple ways to monitor deployment progress:

1. **GitHub Actions logs**: Real-time logs in the Actions UI
2. **DigitalOcean console**: Link provided in logs: `https://cloud.digitalocean.com/apps/$APP_ID`
3. **doctl CLI**: `doctl apps get-deployment $APP_ID $DEPLOYMENT_ID`

### Log Retention

GitHub Actions logs are retained for 90 days (default). For longer retention, consider:

- Exporting logs to external logging service (e.g., Datadog, CloudWatch)
- Archiving logs as workflow artifacts
- Using DigitalOcean's built-in log forwarding

## Future Improvements

### Potential Enhancements

1. **Health endpoint verification**: Add post-deployment step to verify health endpoints respond correctly
2. **Smoke tests**: Run basic API tests against deployed app before marking deployment successful
3. **Deployment notifications**: Send Slack/email notifications on deployment success/failure
4. **Deployment metrics**: Track deployment duration, success rate, and failure reasons
5. **Canary deployments**: Gradually roll out new versions to a subset of users

### Feature Flags for Observability

Following the production deployment principle of **observability feature flags**, consider gating OpenTelemetry tracing behind a feature flag:

```yaml
envs:
  - key: ENABLE_OTEL_TRACING
    value: "false"  # Default off until backend ready
  - key: OTEL_TRACES_SAMPLER
    value: "parentbased_traceidratio"
  - key: OTEL_TRACES_SAMPLER_ARG
    value: "0.1"  # 10% sampling in staging, 1-5% in prod
```

**Benefits**:
- Per-environment control of tracing
- Prevents startup failures if collector unreachable
- Enables staged PII-scrubbing rollout
- Allows cost tuning via sampling rates

## Troubleshooting

### Common Issues

#### Deployment ID Not Captured

**Symptoms**: Workflow fails with "Could not retrieve deployment ID after all strategies"

**Cause**: All three extraction strategies failed

**Solution**:
1. Check DigitalOcean API status: https://status.digitalocean.com/
2. Verify `DIGITALOCEAN_ACCESS_TOKEN` has correct permissions
3. Check doctl version: `doctl version`
4. Manually verify deployment was created: `doctl apps list-deployments $APP_ID`

#### Deployment Canceled Immediately

**Symptoms**: Polling shows `Phase: CANCELED` on first iteration

**Cause**: DigitalOcean canceled the deployment (not a workflow issue)

**Possible reasons**:
1. Image pull authentication failure (GHCR access)
2. Resource/billing limits on DigitalOcean account
3. App configuration issue in app spec
4. Previous deployment still running

**Solution**:
1. Check DigitalOcean console for cancellation reason
2. Verify GHCR image pull permissions
3. Check DigitalOcean account status/limits
4. Review app logs: `doctl apps logs $APP_ID --type deploy`

#### Deployment Timeout

**Symptoms**: Workflow fails with "Deployment timeout after 900s (15 minutes)"

**Cause**: Deployment didn't reach terminal state within timeout

**Solution**:
1. Check DigitalOcean console for deployment status
2. Review deployment logs for errors
3. Verify health check endpoint is responding
4. Consider increasing timeout if deployments consistently take >15 minutes

## Related Documentation

- [DigitalOcean Deployment Guide](./DIGITALOCEAN-DEPLOYMENT.md) - Complete setup guide
- [Production Deployment Notes](./PRODUCTION-DEPLOYMENT.md) - Production best practices
- [Environment Variables](./ENVIRONMENT.md) - Configuration reference
- [API Documentation](./API.md) - API endpoint reference

## Changelog

### 2025-11-01: Workflow Improvements (PR #137)

- Added three-tier deployment ID extraction strategy
- Implemented time-based progress percentage calculation
- Added comprehensive pre-deploy and post-mutation validation
- Improved error handling with bash strict mode and die() helper
- Added cleanup trap and belt-and-suspenders cleanup step
- Enhanced logging with structured output

### 2025-11-01: Logging Cleanup (PR #TBD)

- Removed emojis from all log messages
- Replaced with plain text prefixes: `[OK]`, `[WARN]`, `[FAILED]`, `[SUCCESS]`
- Improved CI log readability and parsing
- Added comprehensive workflow documentation (this file)
