# github_repo/ - staged GitHub packaging copy

This folder mirrors what actually gets pushed to the public GitHub repository. It is intentionally separate
from the working folders one level up (notebooks/, src/, tests/, etc.) for one specific, real reason:

STANDING LESSON (AMEX RiskIQ GitHub push): `git` cannot run inside a device-mounted folder - its object-store
bookkeeping needs a real `unlink`, which the mount blocks (`unable to unlink tmp_obj...`, `index.lock` errors).
This folder - and this whole Documents path - is a mounted folder, so `git init` / `git add` / `git commit`
must NEVER be run here.

## The actual push workflow (proven on AMEX and Home Credit RiskIQ)
1. Finished, real-run-confirmed BP content is copied/synced from the working folders into this `github_repo/`
   mirror (README, docs, notebooks, src, tests, reports, configs, .github/workflows - never data/raw,
   data/processed, or logs/, per .gitignore).
2. This folder's content is staged into the Claude session's cloud container (not this device), where `git init`
   and every commit actually happen - the cloud container's filesystem has no mount restriction.
3. The repository is created on GitHub, and the push itself is run from a normal (non-mounted) local path -
   never from inside this Documents mount - using a Personal Access Token verified to carry the `repo` scope
   (check the `x-oauth-scopes` response header first; a token with no scopes checked will authenticate but
   fail every push with a misleading 404).
4. Nothing above ever writes outside this Documents project folder on this device.

## Repo naming
Suggested repo name: `IBM-AML-RiskIQ-Enterprise-Suite` (GitHub convention - hyphens, no underscores).

## What is excluded from the push (mirrors the root .gitignore)
Raw AML transaction data (data/raw, data/external), trained model binaries (.joblib/.pkl/.onnx), logs/,
__pycache__/, notebook checkpoints, and anything under configs/ that ever holds a credential or API key.
