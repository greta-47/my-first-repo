# My First Repo

A simple FastAPI application for RecoveryOS.

<!-- Test change to trigger auto-add workflow -->

## Run locally

```bash
python -m uvicorn app.main:app --reload
curl -fsS http://127.0.0.1:8000/healthz
```

## Tests

```bash
python -m pytest -q
```

## API Documentation

- **Interactive API docs**: Visit `http://127.0.0.1:8000/docs` when running locally
- **Help endpoint**: `GET /help` for API information and troubleshooting
- **Troubleshooting guide**: See [docs/troubleshooting.md](docs/troubleshooting.md)

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
