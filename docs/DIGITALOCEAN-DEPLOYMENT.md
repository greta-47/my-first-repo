# DigitalOcean App Platform Deployment Guide

Complete guide for deploying RecoveryOS API to DigitalOcean App Platform.

## Quick Start

```bash
# 1. Install doctl
brew install doctl  # macOS
# or: https://github.com/digitalocean/doctl/releases

# 2. Authenticate
doctl auth init

# 3. Create app
doctl apps create --spec .do/app.yaml

# 4. Set GitHub secrets
gh secret set DIGITALOCEAN_ACCESS_TOKEN --repo greta-47/my-first-repo
gh secret set DIGITALOCEAN_APP_ID --repo greta-47/my-first-repo

# 5. Deploy
git push origin main
```

## Prerequisites

- DigitalOcean account with billing enabled
- doctl CLI installed
- GitHub CLI (gh) installed
- DigitalOcean Personal Access Token
- Repository pushed to GitHub

## Step 1: Install doctl CLI

**macOS:**
```bash
brew install doctl
```

**Linux:**
```bash
cd ~
wget https://github.com/digitalocean/doctl/releases/download/v1.104.0/doctl-1.104.0-linux-amd64.tar.gz
tar xf doctl-1.104.0-linux-amd64.tar.gz
sudo mv doctl /usr/local/bin
```

**Windows:**
```powershell
choco install doctl
```

Verify installation:
```bash
doctl version
```

## Step 2: Authenticate with DigitalOcean

1. **Create Personal Access Token:**
   - Go to: https://cloud.digitalocean.com/account/api/tokens
   - Click "Generate New Token"
   - Name: "GitHub Actions Deploy"
   - Scopes: Read + Write
   - Copy the token (you won't see it again!)

2. **Authenticate doctl:**
   ```bash
   doctl auth init
   # Paste your token when prompted
   ```

3. **Verify authentication:**
   ```bash
   doctl account get
   ```

## Step 3: Make GHCR Package Accessible

Your Docker images are stored in GitHub Container Registry. App Platform needs access to pull them.

**Option A: Make Package Public (Easiest)**

1. Go to: https://github.com/greta-47/my-first-repo/pkgs/container/my-first-repo
2. Click "Package settings"
3. Scroll to "Danger Zone"
4. Click "Change visibility" → Select "Public"
5. Confirm the change

**Option B: Use Private Package with Token (More Secure)**

1. Create GitHub PAT with `read:packages` scope
2. Add to `.do/app.yaml`:
   ```yaml
   services:
     - name: api
       image:
         registry_type: GHCR
         registry: greta-47
         repository: my-first-repo
         tag: latest
         registry_credentials: ${{ secrets.GHCR_TOKEN }}
   ```

For this guide, we'll use **Option A** (public package).

## Step 4: Create the App

```bash
# Navigate to repository
cd ~/repos/my-first-repo

# Create app from spec
doctl apps create --spec .do/app.yaml
```

**Expected output:**
```
Notice: App created
ID                                      Spec Name           Default Ingress
12345678-1234-1234-1234-123456789abc    recoveryos-api      https://recoveryos-api-xxxxx.ondigitalocean.app
```

**Save the App ID!** You'll need it for GitHub secrets.

## Step 5: Configure GitHub Secrets

Your GitHub Actions workflow needs two secrets:

### Using GitHub CLI (Recommended)

```bash
# Authenticate with GitHub (if not already)
gh auth login

# Set DigitalOcean Access Token
gh secret set DIGITALOCEAN_ACCESS_TOKEN --repo greta-47/my-first-repo
# Paste your DigitalOcean token when prompted

# Set App ID (from Step 4)
gh secret set DIGITALOCEAN_APP_ID --repo greta-47/my-first-repo
# Paste the App ID (e.g., 12345678-1234-1234-1234-123456789abc)
```

### Using GitHub Web UI

1. Go to: https://github.com/greta-47/my-first-repo/settings/secrets/actions
2. Click "New repository secret"
3. Add `DIGITALOCEAN_ACCESS_TOKEN`:
   - Name: `DIGITALOCEAN_ACCESS_TOKEN`
   - Value: Your DigitalOcean Personal Access Token
4. Add `DIGITALOCEAN_APP_ID`:
   - Name: `DIGITALOCEAN_APP_ID`
   - Value: Your App ID from Step 4

## Step 6: Configure Database

The App Platform automatically provisions a PostgreSQL database and injects the `DATABASE_URL` environment variable. No manual configuration needed!

**Verify database provisioning:**
```bash
APP_ID="your-app-id-here"

# Check app status
doctl apps get $APP_ID

# List all components (including database)
doctl apps list-components $APP_ID
```

**Database details:**
- Engine: PostgreSQL 16
- Plan: Basic (can be upgraded later)
- Connection: Automatic via `DATABASE_URL` env var
- SSL: Enabled by default
- Backups: Daily automatic backups

### Automatic database migrations

- By default, automatic migrations are **disabled** (`DB_AUTO_MIGRATE=false`) to allow the app to deploy successfully with in-memory storage before database integration is complete.
- The App Platform pre-deploy job runs `scripts/migrate.sh`, which checks the `DB_AUTO_MIGRATE` flag and skips migrations when disabled.
- To enable automatic migrations when your database is ready, set `DB_AUTO_MIGRATE` to `"true"` in `.do/app.yaml` for both the `migrate` job and the `api` service, ensure `DATABASE_URL` is configured as a secret in DigitalOcean, then redeploy.

## Step 7: Deploy Your App

Deployment happens automatically when you push to `main`:

```bash
# Ensure you're on main branch
git checkout main

# Push to trigger deployment
git push origin main
```

**Or trigger manually via GitHub Actions:**
1. Go to: https://github.com/greta-47/my-first-repo/actions/workflows/deploy.yml
2. Click "Run workflow"
3. Select branch: `main`
4. Click "Run workflow"

## Step 8: Monitor Deployment

### Via GitHub Actions

Watch the workflow run:
```bash
# List recent runs
gh run list --workflow=deploy.yml --limit 5

# Watch latest run
gh run watch
```

Or visit: https://github.com/greta-47/my-first-repo/actions

### Via doctl

```bash
APP_ID="your-app-id-here"

# Get deployment status
doctl apps get $APP_ID

# View deployment logs
doctl apps logs $APP_ID --type deploy --follow

# View runtime logs
doctl apps logs $APP_ID --type run --follow
```

### Via DigitalOcean Console

1. Go to: https://cloud.digitalocean.com/apps
2. Click on your app
3. View "Runtime Logs" or "Deploy Logs"

## Step 9: Configure Custom Domain

Your domain `recoveryos.org` is already in the app spec. Complete DNS setup:

### Get App Platform URL

```bash
APP_ID="your-app-id-here"
doctl apps get $APP_ID --format DefaultIngress --no-header
```

### Update DNS Records

1. Go to: https://cloud.digitalocean.com/networking/domains/recoveryos.org
2. Add A record:
   - **Hostname:** `@` (root domain)
   - **Will Direct To:** Select your app from dropdown
   - **TTL:** 3600

3. Or add CNAME (for subdomain):
   - **Hostname:** `api`
   - **Is An Alias Of:** `recoveryos-api-xxxxx.ondigitalocean.app`
   - **TTL:** 3600

### SSL Certificate

App Platform automatically provisions Let's Encrypt SSL certificates:
- Takes 5-10 minutes after DNS propagation
- Auto-renews before expiration
- No manual configuration needed

## Step 10: Verify Deployment

```bash
# Wait for DNS propagation (may take a few minutes)
dig recoveryos.org

# Test health endpoint
curl https://recoveryos.org/healthz
# Expected: {"status":"ok"}

# Test version endpoint
curl https://recoveryos.org/version
# Expected: {"version":"1.0.0","app_env":"production"}

# View API docs
open https://recoveryos.org/docs
```

## Troubleshooting

### Issue: "Image Pull Error"

**Symptoms:** Deployment fails with "failed to pull image"

**Cause:** App Platform can't access GHCR image

**Solution:**
1. Verify package is public: https://github.com/greta-47/my-first-repo/pkgs/container/my-first-repo
2. Check image exists: `docker pull ghcr.io/greta-47/my-first-repo:latest`
3. Verify registry settings in `.do/app.yaml`

### Issue: "Database Connection Failed"

**Symptoms:** App logs show "could not connect to database"

**Cause:** Database not ready or connection string incorrect

**Solution:**
```bash
# Check database status
doctl apps get $APP_ID

# Verify DATABASE_URL is set
doctl apps list-components $APP_ID

# Check database logs
doctl databases list
doctl databases logs <database-id>
```

### Issue: "Migration Job Failed"

**Symptoms:** Pre-deploy migration job fails

**Cause:** Database not ready or Alembic error

**Solution:**
```bash
# View migration logs
doctl apps logs $APP_ID --type deploy

# Test migrations locally
export DATABASE_URL="postgresql://..."
./scripts/migrate.sh

# Check Alembic status
alembic current
alembic history
```

### Issue: "503 Service Unavailable"

**Symptoms:** App URL returns 503 error

**Cause:** App still deploying or health check failing

**Solution:**
```bash
# Check deployment status
doctl apps get $APP_ID

# View runtime logs
doctl apps logs $APP_ID --type run --follow

# Test health endpoint directly
curl -v https://your-app.ondigitalocean.app/healthz
```

### Issue: "GitHub Actions Workflow Fails"

**Symptoms:** Deploy workflow fails with "DIGITALOCEAN_APP_ID not set"

**Cause:** GitHub secrets not configured

**Solution:**
```bash
# Verify secrets are set
gh secret list --repo greta-47/my-first-repo

# Re-set secrets if needed
gh secret set DIGITALOCEAN_ACCESS_TOKEN --repo greta-47/my-first-repo
gh secret set DIGITALOCEAN_APP_ID --repo greta-47/my-first-repo
```

## Scaling

### Vertical Scaling (More Resources)

Edit `.do/app.yaml`:
```yaml
services:
  - name: api
    instance_size_slug: basic-xs  # Upgrade from basic-xxs
```

Available sizes:
- `basic-xxs`: $5/mo (512MB RAM, 0.5 vCPU)
- `basic-xs`: $12/mo (1GB RAM, 1 vCPU)
- `basic-s`: $24/mo (2GB RAM, 1 vCPU)
- `basic-m`: $48/mo (4GB RAM, 2 vCPU)

Apply changes:
```bash
doctl apps update $APP_ID --spec .do/app.yaml
```

### Horizontal Scaling (More Instances)

Edit `.do/app.yaml`:
```yaml
services:
  - name: api
    instance_count: 3  # Scale to 3 instances
```

Apply changes:
```bash
doctl apps update $APP_ID --spec .do/app.yaml
```

### Database Scaling

```bash
# List available sizes
doctl databases options sizes

# Resize database
doctl databases resize <database-id> --size db-s-2vcpu-4gb --num-nodes 1
```

## Cost Breakdown

### Development/Staging
- **App (basic-xxs):** $5/month
- **Database (db-s-1vcpu-1gb):** $15/month
- **Bandwidth:** Included (1TB)
- **Total:** ~$20/month

### Production
- **App (basic-xs, 2 instances):** $24/month
- **Database (db-s-2vcpu-4gb):** $60/month
- **Bandwidth:** Included (1TB)
- **Total:** ~$84/month

## Rollback

If deployment fails or causes issues:

```bash
# List recent deployments
doctl apps list-deployments $APP_ID

# Get specific deployment ID
DEPLOYMENT_ID="deployment-id-here"

# Rollback by deploying previous image
# Update .do/app.yaml with previous SHA
sed -i 's/tag: latest/tag: previous-sha/' .do/app.yaml
doctl apps update $APP_ID --spec .do/app.yaml
```

## Environment Variables

### View Current Variables

```bash
doctl apps list-components $APP_ID
```

### Add/Update Variables

```bash
# Via doctl
doctl apps update $APP_ID --env "NEW_VAR=value"

# Or edit .do/app.yaml and update
doctl apps update $APP_ID --spec .do/app.yaml
```

### Sensitive Variables

For secrets (API keys, tokens):
```yaml
envs:
  - key: SENTRY_DSN
    scope: RUN_TIME
    type: SECRET  # Encrypted at rest
```

## Monitoring & Alerts

### Set Up Alerts

1. Go to: https://cloud.digitalocean.com/apps/your-app-id/settings
2. Navigate to "Alerts"
3. Configure:
   - CPU usage > 80%
   - Memory usage > 80%
   - Failed deployments
   - Health check failures

### View Metrics

```bash
# App metrics
doctl monitoring metrics get-bandwidth --resource-id $APP_ID

# Database metrics
doctl databases get <database-id>
```

### Logs

```bash
# Real-time logs
doctl apps logs $APP_ID --type run --follow

# Deployment logs
doctl apps logs $APP_ID --type deploy

# Export logs
doctl apps logs $APP_ID --type run > app-logs.txt
```

## Security Checklist

- [ ] GHCR package access configured (public or token)
- [ ] DigitalOcean token has minimal permissions
- [ ] GitHub secrets configured correctly
- [ ] Database uses SSL (automatic)
- [ ] HTTPS enforced (automatic)
- [ ] Health checks passing
- [ ] Rate limiting enabled in app
- [ ] Environment variables don't leak in logs
- [ ] Backup strategy in place

## Backup & Recovery

### Database Backups

App Platform provides automatic daily backups:
```bash
# List backups
doctl databases backups list <database-id>

# Restore from backup
doctl databases restore <database-id> <backup-id>
```

### Manual Backup

```bash
# Get database connection details
doctl databases connection <database-id>

# Create backup
pg_dump $DATABASE_URL > backup-$(date +%Y%m%d).sql

# Restore backup
psql $DATABASE_URL < backup-20251030.sql
```

## Additional Resources

- [App Platform Docs](https://docs.digitalocean.com/products/app-platform/)
- [doctl Reference](https://docs.digitalocean.com/reference/doctl/)
- [Pricing Calculator](https://www.digitalocean.com/pricing/app-platform)
- [Status Page](https://status.digitalocean.com/)

## Support

- **DigitalOcean Support:** https://cloud.digitalocean.com/support
- **Community:** https://www.digitalocean.com/community
- **GitHub Issues:** https://github.com/greta-47/my-first-repo/issues
