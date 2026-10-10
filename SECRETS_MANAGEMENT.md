# Secrets Management -- Platform-Wide

Real, current state (2026-10-03).

## What exists today
All 5 scoring services (`src/aml_riskiq/serving/*.py`) read their shared secret (`AML_RISKIQ_API_KEYS`, used by the
`X-API-Key` auth described in `SECURITY.md`) from a plain process environment variable, documented in
`.env.example`, which ships a clearly-fake placeholder value, never a real secret. There is no central
secrets store, no rotation, and no audit trail of who or what read a given secret beyond the per-request
audit log line (which records a key's SHA-256 fingerprint, never the raw key -- see `src/aml_riskiq/serving/
_security.py`'s `_key_fingerprint`).

## What is NOT a secret in this project
This platform's underlying dataset (IBM's synthetic AML transaction data -- see `DATA_PRIVACY.md`) contains
no real credentials, government IDs, or payment-card numbers to protect in the first place. The secrets
surface here is narrow: one shared API key pattern, nothing else.

## Required authentication for scoring containers
Scoring-service Docker images set `AML_RISKIQ_REQUIRE_AUTH=true` by default. A container refuses to start if `AML_RISKIQ_API_KEYS` is unset or empty. Supply a real secret through the deployment environment or a secrets manager; do not use the CI test key or the example placeholder in any real deployment. Local source execution can retain the documented open-mode behavior only when the operator explicitly leaves the require-auth gate disabled. The health endpoint remains unauthenticated for liveness checks and must not expose transaction-level data.

## Rotating a key
Set `AML_RISKIQ_API_KEYS` to the new comma-separated list and restart the service -- there is no
in-process rotation or dual-key grace period implemented. For a Docker deployment, this means updating the
container's environment and recreating it (see each `src/docker/*/docker-compose.yml`).

## If a key leaks
Remove it from `AML_RISKIQ_API_KEYS` and restart every service that shared it. Because the audit log only
ever stores a fingerprint, there's no raw value to scrub from existing logs.
