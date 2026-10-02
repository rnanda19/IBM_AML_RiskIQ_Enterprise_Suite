# Security

## Static analysis
`bandit` runs in CI on every push across `src/` (`.github/workflows/ci.yml`). Current real result: **0
blocking findings** -- 7 Low-severity/High-confidence informational findings remain (the `pickle.load`
calls each BP's scoring service uses to load its own trusted, self-produced model artifact; each is
`# nosec B301`-annotated inline with the trust-boundary justification, never a blanket suppression).

## API authentication
All 5 scoring services (BP1/BP2/BP3-rule/BP4/BP5) share one auth module (`src/services/_security.py`).
Set the `AML_RISKIQ_API_KEYS` environment variable (comma-separated keys) to require a matching
`X-API-Key` header on every `/score` request; keys are compared with `secrets.compare_digest`
(constant-time) and never logged in raw form (only an 8-character SHA-256 fingerprint is). Left unset, the
service runs in a documented "open mode" with a loud startup warning -- this is what keeps local
development and this project's own CI/pytest suite green without injecting a credential into every test.
`/health` is deliberately never auth-gated (liveness/readiness probes need to reach it without a key, and
it leaks nothing beyond what a model-registry fingerprint already discloses -- see `MODEL_REGISTRY.md`).

## Rate limiting
Real token-bucket rate limiting via `slowapi`, default 60 requests/minute per caller on `/score`,
overridable via `AML_RISKIQ_SCORE_RATE_LIMIT`. Exceeding it returns a real `429`, not a soft warning.

## Audit logging
Every request to every route on every service emits one structured JSON line (timestamp, service, method,
path, status code, latency, caller IP, caller fingerprint) to stdout -- see `SECRETS_MANAGEMENT.md` for
what is and isn't in that line.

## Reporting a vulnerability
Open a GitHub issue, or contact the maintainer directly via the email on the GitHub profile for anything
sensitive enough not to post publicly.
