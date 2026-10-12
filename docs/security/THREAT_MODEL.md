# Security Threat Model

Scope: the 5 FastAPI scoring services (BP1/BP2/BP3-rule/BP4/BP5), the Case Management Service
(`src/aml_riskiq/serving/case_management_service.py`, added 2026-10-12), and their shared hardening
module (`src/aml_riskiq/serving/_security.py`). Out of scope: the notebooks/pipeline (not a running
service), GitHub Pages static report site (no application logic, see `pages.yml`), and anything below
the application layer (TLS termination, network segmentation, host OS hardening) -- those are a real
deployer's gateway/infra responsibility, not this codebase's, per `SECURITY.md`'s own scope note. Also in scope since
2026-10-12 (End-to-End AML Workflow Integration): `src/aml_riskiq/serving/_alert_dispatch.py` (the
scoring-to-alert delivery client) and the new `POST /alerts/ingest` route on the Case Management
Service -- see `docs/architecture/SCORING_ALERT_INTEGRATION.md` for the design these threats reference.

## Assets
- The trained model artifacts themselves (`.pkl`/rule `.json`) -- not secret, but integrity-sensitive
  (a swapped artifact would silently change every score).
- `/score` responses (a risk score + explanation for a submitted synthetic transaction) -- not real
  customer data in this project's own tests, but the application should behave as if it were.
- API keys (`AML_RISKIQ_API_KEYS`) -- credential material.
- Audit log stream (who called what, when, from where).
- **Case records** (`data/case_management/casework.db`, added 2026-10-12): alert content, case status
  history, investigator notes, evidence references -- the asset DEF-003's RBAC work and this entry both
  protect.
- **The case-service API key each scoring service holds** (`AML_RISKIQ_CASE_SERVICE_API_KEY`, added
  2026-10-12): credential material distinct from a scoring service's own `AML_RISKIQ_API_KEYS` -- it is
  what BP1-BP5 present to the Case Management Service when dispatching an alert.
- **The local alert outbox files** (`data/alert_outbox/<service>.outbox.jsonl`, added 2026-10-12): a
  queued, undelivered alert's full content at rest on the scoring service's own filesystem until
  replayed.

## Threats considered, and this platform's real current posture

| Threat | Mitigation in place | Real gap |
|---|---|---|
| Unauthenticated access to `/score` | `require_api_key` dependency, constant-time compare | Open mode is the *default* (documented) -- `AML_RISKIQ_REQUIRE_AUTH` makes this fail-closed, but only if a deployer sets it |
| Credential stuffing / brute-force on `/score` | Rate limiting (`slowapi`, 60/min default) + 401 on bad key | No account lockout, no IP-reputation check -- rate limiting alone is the only brake |
| Timing side-channel on key comparison | `secrets.compare_digest` | None known |
| API key leaked via logs | Only an 8-char SHA-256 fingerprint is ever logged, never the raw key | None known |
| A caller with a valid key doing something only a different role should do | On the Case Management Service (added 2026-10-12): every mutating route enforces `require_any_role()`/a dynamic per-target-status check -- see `docs/security/RBAC.md`'s full matrix, tested by 43 cases in `tests/integration/case_management/test_case_management_service.py` including explicit negative-authorization assertions | **Still true for BP1-BP5's `/score` routes** -- each has only `/health` (unauthenticated) and `/score` (any valid key, any role); there is still not a second route on any of them for a role distinction to protect. DEF-003 is resolved for the surface it had (case management, its own recommended fix), not retroactively applied to the 5 scoring services |
| Malformed / oversized request body crashing the service | Pydantic request-model validation (FastAPI default) | No explicit request-size limit configured at the application layer -- relies on a reverse proxy/gateway in front, per this module's own scope note |
| A compromised/rogue model artifact silently swapped in | `/health` exposes a live-recomputed SHA-256 + mtime of the loaded artifact (`MODEL_REGISTRY.md`) so a caller/monitor CAN detect drift from the registry's recorded hash | Nothing *automatically* alerts on a mismatch today -- detection requires a caller or monitor to actually compare against `MODEL_REGISTRY.md` |
| Denial of service via request flood | Rate limiting bounds a single caller's rate | No protection against a distributed flood across many IPs -- that is explicitly a gateway/CDN concern, not this module's |
| Dependency supply-chain vulnerability | CodeQL + Dependabot wired into CI (`.github/workflows/codeql.yml`, `.github/dependabot.yml`) | None known beyond standard CI-cadence lag |
| Container escape / privilege escalation inside a compromised container | **Fixed this session**: all 5 service Dockerfiles now run as a non-root `app` user | Base image (`python:3.11-slim`) vulnerabilities still depend on Dependabot's base-image update cadence |
| `/health` or `/metrics` leaking sensitive data to an unauthenticated caller | Both are deliberately unauthenticated by design (liveness-probe/scrape-target requirement) but checked to expose only model-registry metadata and request counts, never transaction content | None known -- re-verify this invariant on any future addition to either route |
| A scoring service's case-service API key is leaked or guessed | Same `secrets.compare_digest` constant-time check and SHA-256-fingerprint-only logging as every other API key in this platform; a 401/403 from `/alerts/ingest` is treated as a definitive rejection, not retried, and is logged/outboxed for operator visibility (added 2026-10-12) | The key is configured as a plain environment variable (`AML_RISKIQ_CASE_SERVICE_API_KEY`) on each scoring container -- rotating it requires redeploying every scoring service that holds it, there is no automated rotation mechanism |
| A malicious or buggy caller submits a scoring event with a forged `entity_ref`/`model_name` to inflate case-management records | `ScoringEvent` validates shape (non-empty identifiers, finite scores, supported schema version) but not the *truth* of any field's content -- `/score`'s own caller, not `/alerts/ingest`, is this platform's actual trust boundary for that data (added 2026-10-12) | No cross-check between a dispatched alert's claimed `model_name`/`model_sha256` and the Case Management Service's own independent knowledge of what model actually produced it -- case-management trusts the scoring service's own report of its provenance |
| A queued alert sitting in the local outbox file is read or tampered with before replay | File lives under the scoring service's own filesystem, same trust boundary as its model artifacts and config (added 2026-10-12) | The outbox file is plain, unencrypted JSON Lines at rest -- no additional access control beyond the container's own filesystem permissions |
| Retrying or replaying a scoring event creates a duplicate alert | A real SQLite partial `UNIQUE` index on `idempotency_key` (`casework/store.py`'s `create_alert_idempotent()`), not an application-level check-then-insert that would have a race window (added 2026-10-12) | None known -- this is treated as resolved, not a residual gap, because the guarantee is database-enforced |

## Residual risks (explicitly not mitigated by this codebase)

- **TLS termination, network segmentation, host hardening**: the deployer's gateway/reverse-proxy
  responsibility, not reimplemented here (see `_security.py`'s own "HONEST SCOPE NOTE").
- **Open mode as the default**: a deployer who does not explicitly set `AML_RISKIQ_API_KEYS` and
  `AML_RISKIQ_REQUIRE_AUTH=true` gets an unauthenticated service with only a startup warning, by design
  (keeps local dev/CI friction-free) -- this is a real, deliberate trade-off, not an oversight, but it
  means secure-by-default is opt-in, not automatic.
- **Role differentiation on BP1-BP5's `/score` routes**: still unprotected (each has only one
  protectable route today) -- the Case Management Service closes this for case-management actions, not
  for `/score` itself.
- **Case audit-trail tamper-evidence, not tamper-proofing** (new 2026-10-12): the hash chain over
  `case_events` (`case_lifecycle.verify_history_integrity()`) proves the chain is internally
  self-consistent, catching a row edited outside the application's own append-only code path -- it
  cannot prove the very first event in a chain is the true original event, only that every event after
  it is consistent with it. Not a cryptographic non-repudiation signature scheme.
- **SQLite is single-process-per-container, not cluster-aware**: the case-management store (new
  2026-10-12) is correct for this platform's one-process-per-container deployment shape but would need
  a real client-server database for a multi-replica deployment -- disclosed in `store.py`'s own module
  docstring, not built here.
- **Live artifact-integrity alerting**: `/health`'s fingerprint makes tampering *detectable*, not
  *automatically alerted on*.
- **Scoring-to-alert data trust (new 2026-10-12)**: `/alerts/ingest` validates that a scoring event is
  well-formed, not that its content is true -- a compromised or buggy scoring service could submit a
  structurally valid but substantively false event (wrong entity, inflated score). This is the same
  trust relationship the platform already has with any caller of `/score`; it is not a new privilege
  boundary, but it is now reachable automatically rather than only through a manual `POST /alerts` call.
- **Case-service API-key rotation (new 2026-10-12)**: no automated rotation for
  `AML_RISKIQ_CASE_SERVICE_API_KEY` across the 5 scoring services that hold it -- a real deployer's
  secrets-manager responsibility, not built here (same disclosed trade-off as every other API key in
  this platform).

## Review cadence
Re-review this document whenever a new route is added to any service, when `_security.py` changes, or
at minimum alongside any `SECURITY.md` update.
