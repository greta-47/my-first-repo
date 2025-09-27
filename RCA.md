Symptom
- PR #82 had 2 failing jobs:
  - CI (py312) › lint-test
  - PR CI › Lint (ruff) + format check

Key error indicators (from CI):
- ruff job installed latest ruff (unpinned), causing formatter/lint drift versus previous runs.
- ci.yml attempted to install requirements-dev.txt, which does not exist in the repo, causing failure before tools ran.

Root cause
- CI toolchain drift and workflow misconfiguration:
  - Unpinned ruff in PR workflow led to breaking changes from latest releases.
  - ci.yml referenced a non-existent requirements-dev.txt, breaking the job.

Fix implemented
- Pin toolchain in workflows and remove bad reference:
  - pr.yml ruff job now pins:
    - pip==24.2
    - ruff==0.13.2
  - ci.yml lint-test now:
    - Pins pip==24.2
    - Installs runtime deps from requirements.txt
    - Installs tools with fixed versions: ruff==0.13.2, mypy==1.11.2, pip-audit==2.7.3, pytest==8.3.2
    - Removes requirements-dev.txt reference.

Why this works
- Deterministic tool versions eliminate drift across runs and environments.
- Removing the non-existent dev requirements file restores a valid install step.
- Lockfile preflight already pins pip==24.2 and pip-tools==7.4.1 and passed; no lockfile changes were necessary.

Links
- Before (failing): see PR #82 checks for “lint-test” and “Lint (ruff) + format check”.
- After (passing): see PR #82 checks after these commits.

Follow-ups (optional)
- None required. Trivy remains non-blocking with fork-safe SARIF upload guards. Python version remains 3.12 across CI.

Tooling policy adherence
- Python: 3.12 only.
- Deterministic lockfiles: unchanged; preflight uses pip==24.2 and pip-tools==7.4.1.
- Minimal diff: workflow-only changes; no app code modifications; security posture unchanged.
