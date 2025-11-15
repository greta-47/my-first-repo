# My First Repo

A simple FastAPI application for RecoveryOS.

<!-- Test change to trigger auto-add workflow -->

## Run locally

```bash
# run
python -m uvicorn app.main:app --reload
# or: python3 -m uvicorn app.main:app --reload
```

## Tests

```bash
# test (after installing locks)
python -m pytest -q
# or: python3 -m pytest -q
```

### Install (new contributors)

```bash
python -m pip install -U pip==24.2 pip-tools==7.4.1
pip install -r requirements.lock.txt
pip install -r requirements-dev.lock.txt
```

Note: The repository pins pyenv to Python 3.12.5 for consistency across dev and CI. Ensure you have a compatible python3 available locally.

## API Documentation

- **Interactive API docs**: Visit `http://127.0.0.1:8000/docs` when running locally
- **Help endpoint**: `GET /help` for API information and troubleshooting
- **Troubleshooting guide**: See [docs/troubleshooting.md](docs/troubleshooting.md)

## Deployment

The app is configured for deployment to **DigitalOcean App Platform** with automatic CI/CD.

### Quick Deploy

```bash
# 1. Install doctl CLI
brew install doctl  # macOS

# 2. Authenticate with DigitalOcean
doctl auth init

# 3. Create app
doctl apps create --spec .do/app.yaml

# 4. Set GitHub secrets
gh secret set DIGITALOCEAN_ACCESS_TOKEN --repo greta-47/my-first-repo
gh secret set DIGITALOCEAN_APP_ID --repo greta-47/my-first-repo

# 5. Deploy
git push origin main
```

### What Gets Deployed

- **Docker Image**: Built from `Dockerfile` and pushed to GitHub Container Registry
- **Database**: Managed PostgreSQL (automatically provisioned)
- **Domain**: `recoveryos.org` (configured in app spec)
- **SSL**: Automatic Let's Encrypt certificates
- **Migrations**: Run automatically before each deployment

### Required Secrets

Configure these in GitHub repository secrets:

- `DIGITALOCEAN_ACCESS_TOKEN`: Your DigitalOcean Personal Access Token
- `DIGITALOCEAN_APP_ID`: App ID from `doctl apps create` command

### Deployment Pipeline

1. **Build**: Docker image built and pushed to GHCR
2. **Deploy**: DigitalOcean App Platform pulls image and deploys
3. **Migrate**: Database migrations run automatically
4. **Health Check**: App Platform verifies `/healthz` endpoint
5. **DNS**: Traffic routed to new deployment

### Monitoring

- **Logs**: `doctl apps logs $APP_ID --type run --follow`
- **Status**: `doctl apps get $APP_ID`
- **Metrics**: Available in DigitalOcean console

### Complete Guide

See [docs/DIGITALOCEAN-DEPLOYMENT.md](docs/DIGITALOCEAN-DEPLOYMENT.md) for detailed deployment instructions, troubleshooting, and scaling information.

## CI

- Python 3.12 only. Ruff, mypy, pytest, and pip-audit (non-blocking in PR CI) run in `.github/workflows/ci.yml`.
- A nightly dependency audit blocks on High/Critical vulnerabilities (see `.github/workflows/nightly-audit.yml`).

## Projects V2 Sync

This repository automatically syncs issues and pull requests to the GitHub Project V2 board "RecoveryOS · Now / Next / Later" (user project for greta-47).

### How It Works

When an issue or PR is opened, edited, labeled, or unlabeled, the `.github/workflows/projects-sync.yml` workflow:

1. Adds the item to the project (if not already present)
2. Sets default field values if unset:
   - **Priority**: P2 (Normal)
   - **Stage**: Later

The sync is idempotent - it won't overwrite existing field values, only set defaults for empty fields.

### Manual Trigger

To manually sync an item, use workflow_dispatch:

```bash
gh workflow run projects-sync.yml
```

Or trigger via the GitHub Actions UI: Actions → "Sync Issues/PRs to Project V2" → Run workflow

### Rotating PROJECTS_TOKEN

The workflow uses the `PROJECTS_TOKEN` secret (GitHub PAT Classic with `project` scope) to access the user-level Project V2 board.

To rotate the token:

1. Generate a new Personal Access Token (Classic) at https://github.com/settings/tokens
2. Select scope: `project` (read and write access to user projects)
3. Update the repository secret:
   ```bash
   gh secret set PROJECTS_TOKEN --repo greta-47/my-first-repo
   ```
   Or via GitHub UI: Settings → Secrets and variables → Actions → Update `PROJECTS_TOKEN`

**Note**: This targets a **user-level** Project V2 (not an organization project). The token must belong to a user with write access to the project.
