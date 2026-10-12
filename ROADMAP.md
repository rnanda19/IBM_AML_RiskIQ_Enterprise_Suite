# Roadmap

## Done
- BP1-BP6 workstreams and their current evaluation/reporting artifacts are documented. This does **not** mean
  all six are *live-CI-confirmed* deployment-verified: BP2's and BP3's real artifacts were regenerated
  2026-10-12 (see "Resolved 2026-10-12" below) and `docker-verify.yml` builds/starts/polls `/health` for all
  5 scoring services plus a separate BP6 batch check, but the assistant has not directly observed a passing
  GitHub Actions run (no Docker daemon in its sandboxes) -- confirm on the repository's Actions tab. See the
  defect register and evidence ledger for exact artifacts and limitations.
- Full hardening pass: dependency lockfile (`requirements.in`/`requirements.txt`), mypy wired into CI/
  pre-commit (0 errors across 15 files), API-key auth + rate limiting + audit logging on all 5 scoring
  services, a real model-registry fingerprint exposed via `/health`, a real Docker COPY-path verifier that
  caught and fixed a genuine missing-file bug in all 5 service Dockerfiles. Full detail in
  `LESSONS_LEARNED_APPLIED.md` (Lessons #49-#51).
- GitHub repository published at `github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite`, structured to match
  this project's own `PROJECT_STRUCTURE_LOCKED.md` plus the governance doc set used on this portfolio's
  other platforms (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `DATA_PRIVACY.md`, `MODEL_REGISTRY.md`,
  `SECURITY.md`, `SECRETS_MANAGEMENT.md`, `CHANGELOG.md`, this file), plus a `.github/` CI suite (CI,
  Code Quality, CodeQL, Docker Build & Run Verification) -- all 4 workflows passing on `main`.
- `docker-verify.yml` builds, starts, and polls `/health` for all 5 scoring services (BP1-BP5) plus the
  new Case Management Service -- `bp2`/`bp3` jobs were re-added 2026-10-12 once their real artifacts
  existed (see "Resolved 2026-10-12" below), and a `case-management` job was added the same day. Every
  job first proves the fail-closed-by-default auth works (container refuses to start with no API key)
  before running with a disposable CI test key; the `case-management` job additionally confirms a live
  running container actually rejects an unauthenticated write with 401. A separate `bp6-batch` job runs
  the real rollup and checks its report outputs are non-empty (BP6 has no port, so it is never polled for
  `/health`). The assistant has not directly observed a passing GitHub Actions run of this workflow --
  confirm current status on the repository's Actions tab.
- **RBAC is now real on one surface.** `require_any_role()` genuinely protects all 12 non-public routes
  of the new Case Management Service with 4 roles (`analyst`/`investigator`/`compliance_officer`/`admin`)
  -- see `docs/security/RBAC.md` and the 43-test suite in
  `tests/integration/case_management/test_case_management_service.py`. This closes
  `docs/audit/DEFECT_REGISTER.md`'s DEF-003 for the case-management surface specifically; BP1-BP5's
  `/score` routes remain single-tier (see "In progress / pending" below).

## In progress / pending
- Nothing currently blocked on a missing real artifact for BP1-BP5. See "Resolved 2026-10-12" below for
  the two items that were here.
- **DEF-003, remaining part**: BP1-BP5's `/score` routes still accept any valid key regardless of role --
  there is still no second route on any of them for a role distinction to protect. Would only become
  relevant if a second, more sensitive route (e.g. model reload/config change) is ever added to one of
  them; the `require_any_role()` mechanism proven on the Case Management Service would protect it the
  same way.
- The `integrated-workflow` CI job (see "Added 2026-10-12 -- End-to-End AML Workflow Integration" below)
  has been written and locally YAML-validated but not yet observed passing in GitHub Actions -- Docker is
  unavailable in this development environment, so its first real execution is the next push's CI run.
  Confirm on the repository's Actions tab before treating the real-container integration path as verified.

## Resolved 2026-10-12
- **BP2's Docker image wouldn't start** (found 2026-10-03) -- fixed by a real re-run of BP2 Notebook 3
  (LI-Medium) on the user's own machine, resuming Stage A/B fits from the existing checkpoint. The
  regenerated report carries `champion_needs_rf_impute`/`rf_impute_value`, real LIME explanations, and a
  real FastAPI self-test (480 rows, 0 mismatches). `bp2` re-added to `docker-verify.yml`.
- **BP3's near-train-flagged lookup Parquet was missing** -- fixed by a real, full-cost re-run of BP3
  Notebook 3 (LI-Medium) (no checkpoint exists for this notebook). The lookup Parquet
  (24,532,481 bytes, sha256 recorded in `MODEL_REGISTRY.md`) was also blocked from ever being committed by
  a `.gitignore` gap -- every other BP's champion artifact had a `!` exception carved out of the blanket
  `*.pkl`/`*.parquet` rules, but BP3's never did; that exception is now added. `bp3` re-added to
  `docker-verify.yml`.

## Added this session (2026-10-10), not requiring real pipeline execution
- Fail-closed auth gate, role-aware API keys (primitive), `/metrics` endpoint on all 5 services.
- Fixed the real BP2/BP4 port-8001 collision (noted-but-deferred since Lesson #40) -- BP4 now on 8004.
- Non-root user + HEALTHCHECK on all 5 service Dockerfiles (not yet build-verified locally -- pending
  next `docker-verify.yml` CI run).
- `docs/audit/`, `docs/governance/`, `docs/business_value/`, `docs/data/LEAKAGE_AUDIT.md`,
  `docs/security/THREAT_MODEL.md`, `docs/deployment/DEPLOYMENT_GUIDE.md`.

## Added 2026-10-12 -- End-to-End AML Workflow Integration
- **Closes the automatic-pipeline gap tracked above.** Each of BP1-BP5's `/score` routes now decides,
  using its own real scoring result, whether the outcome is alert-worthy, and if so dispatches a real
  alert to the Case Management Service with full provenance (business problem, entity/transaction ref,
  risk score, threshold, model name/sha256, timestamp) -- see
  `docs/architecture/SCORING_ALERT_INTEGRATION.md` for the full design.
- `casework/scoring_event.py` (new): a validated `ScoringEvent` contract (rejects missing identifiers,
  NaN/infinite scores, unsupported schema versions), risk-based severity routing
  (`is_alert_worthy()`/`classify_severity()`), and a deterministic SHA-256 idempotency key over each
  event's stable identity fields.
- `serving/_alert_dispatch.py` (new): the shared delivery client all 5 scoring services import --
  bounded inline retries with backoff, a durable JSON-Lines outbox for sustained Case Management Service
  outages (`data/alert_outbox/`), and non-retryable handling for 400/401/403/404/422 rejections.
- `POST /alerts/ingest` (new route on the Case Management Service): idempotent ingestion
  (`store.create_alert_idempotent()`, backed by a real SQLite partial `UNIQUE` index), the same
  `analyst`/`investigator`/`compliance_officer` RBAC `POST /alerts` already enforces -- deliberately never
  a bespoke "service" role -- plus `alert_ingest_created_total`/`alert_ingest_duplicate_total` counters
  and an `unresolved_alerts_total` gauge on the existing `/metrics` endpoint.
- BP2 (a 5-class typology classifier with no saved decision threshold) uses the mathematically-derived
  chance baseline `1/len(CLASS_NAMES)` as its alert-worthiness line, rather than a hand-tuned value; BP3
  (a rule, not a model) normalizes to a fixed `1.0`/`1.0` signal and never treats an out-of-graph account
  as alert-worthy by omission. Neither introduces a new ML model.
- Root-level `docker-compose.yml` (closes the item tracked above): wires all 5 scoring services + the
  Case Management Service together via Compose's own service-name DNS, each BP depending on
  case-management's Docker-native health check before starting. `scripts/replay_alert_outbox.py` (new):
  the CLI wrapper for `replay_outbox()` the dispatch module's own docstring already promised.
  `.github/workflows/docker-verify.yml` gained an `integrated-workflow` job that builds and brings up
  `case-management` + `bp3-network-graph-intelligence` for real and proves a genuine scoring-to-alert
  round trip (including idempotent resubmission and a correctly-silent non-flagged account) over the
  real network between the two live containers.
- **296 tests passing** (up from 189 at the start of this phase): 20 new unit tests for the scoring-event
  contract, 20 for the dispatch client, 11 for the replay CLI, plus wiring tests on each BP's own
  integration suite, 12+ new Case Management Service tests for `/alerts/ingest`, and a new
  `tests/integration/end_to_end/` suite (8 scenarios) exercising the real FastAPI apps over a real `httpx`
  transport -- normal scoring, threshold-triggered alerts, duplicate suppression, simulated outage +
  retry + outbox, and an authorization-failure scenario.
- Docs: new `docs/architecture/SCORING_ALERT_INTEGRATION.md`; updated `README.md`, `CHANGELOG.md`,
  `docs/security/THREAT_MODEL.md`, `docs/deployment/DEPLOYMENT_GUIDE.md`.
- **Explicitly not claimed**: a new or retrained ML model, any change to the Case Management Service's
  own lifecycle/RBAC/audit trail (reused unchanged), that a generated alert is proof of laundering (it is
  an investigation starting point, not a verdict), or that the `integrated-workflow` CI job has been
  observed passing (see "In progress / pending" above).

## Added 2026-10-12 -- RBAC, Case Management & Audit Trails (not requiring real pipeline execution)
- `require_any_role()`/`resolve_caller_role()` in `_security.py` -- the role-aware API keys and
  `require_role()` primitive from 2026-10-10 now genuinely protect a real route surface for the first
  time (DEF-003, resolved for this surface).
- A new, real, standalone FastAPI service, `case_management_service.py` (port 8005), built on the
  pre-existing `casework` package: alert creation, assignment, investigation notes, evidence references,
  status transitions (with a compliance-officer-only escalation/closure rule), evidence export, integrity
  verification, and a reconciliation report -- 12 routes, every non-public one RBAC-protected.
- A real SQLite-backed `AlertStore` (`casework/store.py`) -- the `casework` package's first persistent
  store, append-only by construction, with a SHA-256 hash chain over case history for tamper-evidence.
- Automated security tests integrated into CI: 17 new unit tests for the RBAC primitives, 12 new unit
  tests for the hash chain/lifecycle additions, 20 new unit tests for the store, and 43 new integration
  tests for the service (positive/negative auth, role enforcement, input validation, audit logging,
  negative authorization) -- 189/189 total, auto-discovered by `ci.yml`'s existing `pytest tests/` call.
  `docker-verify.yml` gained a `case-management` job with a live 401 check.
- Docs: new `docs/security/RBAC.md`; updated `docs/security/THREAT_MODEL.md`, `SECURITY.md`,
  `docs/audit/DEFECT_REGISTER.md`, `docs/architecture/INVESTIGATOR_WORKFLOW.md`, `README.md`,
  `docs/deployment/DEPLOYMENT_GUIDE.md`.
- **Explicitly not claimed**: regulatory compliance, production readiness, RBAC on BP1-BP5's `/score`
  routes, an automatic scoring-to-case pipeline, or tamper-*proofing* (only tamper-*evidence*) on the
  audit trail.

## Not planned
- The 4 business problems dropped from the original 8-BP draft (Account/Entity AML Risk Scoring, Alert
  Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision
  Engine) -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section for why each was dropped.
