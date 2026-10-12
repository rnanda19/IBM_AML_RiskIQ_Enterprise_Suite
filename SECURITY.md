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

## Role-aware API keys (now applied: Case Management Service)
`AML_RISKIQ_API_KEYS` entries may optionally carry a role prefix: `role:key` (e.g.
`investigator:abc123,admin:def456`). A bare key with no prefix keeps working exactly as before, with the
default role `service`. `require_role(role)` / `require_any_role(*roles)` (in `_security.py`) are
dependency factories that additionally check the matched key's role (an `admin`-role key satisfies any
role check), returning 403 for a valid key with the wrong role vs. 401 for no/invalid key.

**Updated 2026-10-12.** The 5 scoring services still do not use this -- each has only `/health`
(unauthenticated) and `/score` (any valid key, any role), so there is still no second route on any of them
for a role distinction to protect; that part of `docs/audit/DEFECT_REGISTER.md`'s DEF-003 remains open by
design (see that entry for the exact remaining scope). What changed: the new **Case Management Service**
(`src/aml_riskiq/serving/case_management_service.py`) is a real, live FastAPI service whose 12 routes
genuinely enforce 4 distinct roles -- `analyst`, `investigator`, `compliance_officer`, and `admin` (the
"administrator" business role, via the pre-existing admin bypass) -- through `require_any_role()`.
`docs/security/RBAC.md` is the authoritative permission matrix (including the one route,
`/alerts/{id}/transition`, whose required role depends on the request body rather than the route alone),
and `tests/integration/case_management/test_case_management_service.py` is the 43-test automated suite
(positive and negative per role per route) that verifies it.

## Metrics
`GET /metrics` (via `wire_metrics_endpoint()` in `_security.py`) exposes real, in-process request counts
and summed latency per service/method/path/status, in Prometheus text-exposition format -- derived from
the same per-request data the audit-log middleware already records, not a new data source. Deliberately
unauthenticated, same reasoning as `/health`. Honest scope: in-process counters only (reset on restart,
not shared across multiple worker processes) -- adequate for this platform's one-process-per-container
shape, not a drop-in for a multi-worker deployment without an external aggregator.

## Rate limiting
Real token-bucket rate limiting via `slowapi`, default 60 requests/minute per caller on `/score`,
overridable via `AML_RISKIQ_SCORE_RATE_LIMIT`. The Case Management Service has its own independent budget
(default 120 requests/minute, overridable via `AML_RISKIQ_CASE_RATE_LIMIT`) -- a separate env var and a
separate limiter instance, so tuning one never silently changes the other. Exceeding either returns a real
`429`, not a soft warning.

## Input validation
Every request body, path parameter, and query parameter on every service (including the Case Management
Service) is a Pydantic v2 model or a typed FastAPI parameter -- malformed input (wrong type, missing
required field, an enum value outside `CaseStatus`) is rejected with a real `422` before any handler code
runs, never hand-rolled validation. No SQL is ever built from an untrusted value: the Case Management
Service's SQLite layer (`src/aml_riskiq/casework/store.py`) exclusively binds real values through
parameterized `?` placeholders; the one place a string is f-string-assembled is a fixed literal `WHERE`
clause fragment (never a value), annotated `# nosec B608` with that justification and confirmed by a clean
`bandit` run.

## Audit logging
Every request to every route on every service emits one structured JSON line (timestamp, service, method,
path, status code, latency, caller IP, caller fingerprint) to stdout -- see `SECRETS_MANAGEMENT.md` for
what is and isn't in that line.

## Case management audit trail
Beyond the per-request log above, the Case Management Service records a structured, per-case audit trail
(`CaseEvent` history, plus notes and evidence) for every status transition, assignment, note, and evidence
addition -- authenticated caller fingerprint, action, timestamp, and (for transitions) the status moved
from/to. Protected against *undetected* modification, not against modification itself: every event is
linked into a SHA-256 hash chain (`prev_event_hash` / `event_hash`), and the underlying SQLite store
(`src/aml_riskiq/casework/store.py`) never issues an `UPDATE` or `DELETE` against the `case_events`,
`case_notes`, or `case_evidence` tables anywhere in its own source (verified by a dedicated regex-based
structural test, not just by convention), nor does the REST API expose any route that could. An
out-of-band edit -- raw SQL against the `.db` file, bypassing this module entirely -- is still physically
possible and is exactly what `verify_integrity()` / `GET /alerts/{id}/integrity` (compliance-officer-only)
is for: this is tamper-**evidence**, not tamper-**proofing**. It proves internal self-consistency of the
chain and will detect any event edited after the fact, but it cannot prove the very first event in a
chain was the true original. See `docs/security/RBAC.md` and `docs/security/THREAT_MODEL.md` for the full
honest scope, including the hash chain's limitation and SQLite's single-process (non-cluster-aware)
limitation.

## Reporting a vulnerability
Open a GitHub issue, or contact the maintainer directly via the email on the GitHub profile for anything
sensitive enough not to post publicly.
