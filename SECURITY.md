# Security

## Static analysis
`bandit` runs in CI on every push across `src/` (`.github/workflows/ci.yml`). Current real result: **0
blocking findings** -- 7 Low-severity/High-confidence informational findings remain (the `pickle.load`
calls each BP's scoring service uses to load its own trusted, self-produced model artifact; each is
`# nosec B301`-annotated inline with the trust-boundary justification, never a blanket suppression).

## API authentication
All 5 scoring services (BP1/BP2/BP3-rule/BP4/BP5) share one auth module (`src/aml_riskiq/serving/_security.py`).
Set the `AML_RISKIQ_API_KEYS` environment variable (comma-separated keys) to require a matching
`X-API-Key` header on every `/score` request; keys are compared with `secrets.compare_digest`
(constant-time) and never logged in raw form (only an 8-character SHA-256 fingerprint is). Left unset, the
service runs in a documented "open mode" with a loud startup warning -- this is what keeps local
development and this project's own CI/pytest suite green without injecting a credential into every test.
`/health` is deliberately never auth-gated (liveness/readiness probes need to reach it without a key, and
it leaks nothing beyond what a model-registry fingerprint already discloses -- see `MODEL_REGISTRY.md`).

**Fail-closed production gate:** open mode is a deliberate default for local dev / CI, not a safe default
for a real deployment. Set `AML_RISKIQ_REQUIRE_AUTH=true` to make that explicit: if it is true and
`AML_RISKIQ_API_KEYS` is unset or empty, the service refuses to start (raises at startup) instead of
quietly serving unauthenticated traffic. Leaving `AML_RISKIQ_REQUIRE_AUTH` unset preserves today's
open-mode-by-default behavior exactly -- this is an opt-in deployment control, not a change to the
default. Recommended: set both `AML_RISKIQ_API_KEYS` and `AML_RISKIQ_REQUIRE_AUTH=true` in every
non-local deployment.

## Role-aware API keys (primitive, not yet applied to any route)
`AML_RISKIQ_API_KEYS` entries may optionally carry a role prefix: `role:key` (e.g.
`investigator:abc123,admin:def456`). A bare key with no prefix keeps working exactly as before, with the
default role `service`. `require_role(role)` (in `_security.py`) is a dependency factory that additionally
checks the matched key's role (an `admin`-role key satisfies any role check), returning 403 for a valid
key with the wrong role vs. 401 for no/invalid key. Honest scope: none of the 5 scoring services' routes
use it yet -- today each service has only `/health` (unauthenticated) and `/score` (any valid key, any
role), so there is not yet a second route for a role distinction to protect. This exists so `/score` or a
future route can adopt it without another change to the shared auth module.

## Metrics
`GET /metrics` (via `wire_metrics_endpoint()` in `_security.py`) exposes real, in-process request counts
and summed latency per service/method/path/status, in Prometheus text-exposition format -- derived from
the same per-request data the audit-log middleware already records, not a new data source. Deliberately
unauthenticated, same reasoning as `/health`. Honest scope: in-process counters only (reset on restart,
not shared across multiple worker processes) -- adequate for this platform's one-process-per-container
shape, not a drop-in for a multi-worker deployment without an external aggregator.

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
