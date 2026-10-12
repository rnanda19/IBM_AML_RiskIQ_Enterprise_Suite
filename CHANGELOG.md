# Changelog -- IBM AML RiskIQ Enterprise Suite

Platform-level index over the full git history of this repository. Per-BP changelogs for the real
notebook/model work on each business problem live in `reports/<bp>/CHANGELOG.md` -- this file tracks the
repository's own structure, hardening, and governance history, in the same plain-date style used on the
a prior customer-intelligence-focused enterprise platform in this same methodology lineage.

## 2026-10-12 (End-to-End AML Workflow Integration)
- **Scoring services now automatically generate alerts.** Each of BP1-BP5's `/score` routes calls
  `maybe_generate_and_dispatch_alert()` (new, `src/aml_riskiq/serving/_alert_dispatch.py`) after scoring,
  which decides alert-worthiness from the service's own real result and, if warranted, dispatches a real
  alert to the Case Management Service's new `POST /alerts/ingest` route -- full design in the new
  `docs/architecture/SCORING_ALERT_INTEGRATION.md`.
- `src/aml_riskiq/casework/scoring_event.py` (new): `ScoringEvent` (validated: rejects missing
  identifiers, NaN/infinite risk scores, unsupported schema versions), `is_alert_worthy()`/
  `classify_severity()` for risk-based routing, `compute_idempotency_key()` (deterministic SHA-256 over
  each event's stable identity fields), `build_alert_from_scoring_event()`. 20 new tests
  (`tests/unit/test_scoring_event.py`).
- `src/aml_riskiq/serving/_alert_dispatch.py` (new): `dispatch_alert()` -- bounded fast inline retries,
  then a durable JSON-Lines outbox (`data/alert_outbox/<service>.outbox.jsonl`) on sustained failure;
  `_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}` (401/403 added deliberately: a misconfigured
  case-service API key will never self-correct on retry); `replay_outbox()` for draining a queued
  outbox, safe to run repeatedly thanks to idempotency. `maybe_generate_and_dispatch_alert()` never
  raises -- a case-management outage can never fail a `/score` response. 20 new tests
  (`tests/unit/test_alert_dispatch.py`).
- `src/aml_riskiq/serving/case_management_service.py`: new `POST /alerts/ingest` route -- idempotent
  (`store.create_alert_idempotent()`, backed by a real SQLite partial `UNIQUE` index on
  `idempotency_key`), same RBAC as `POST /alerts` (`analyst`/`investigator`/`compliance_officer`, never
  a bespoke "service" role), plus `alert_ingest_created_total`/`alert_ingest_duplicate_total` counters
  and an `unresolved_alerts_total` gauge (`_refresh_unresolved_gauge()`, called from alert creation,
  ingest, and status transition). 12+ new tests in
  `tests/integration/case_management/test_case_management_service.py`, including a structured audit-log
  assertion and a full ingest-to-closure lifecycle test.
- `src/aml_riskiq/serving/bp{1,2,3,4,5}_*.py`: each `/score` endpoint now accepts optional
  `entity_ref`/`transaction_ref`/`event_timestamp` fields and wires in alert dispatch. BP2 (multiclass,
  no saved `selected_threshold`) uses the chance-baseline `1/len(CLASS_NAMES)` rather than a hand-tuned
  cutoff; BP3 (a rule, not a model) normalizes to a fixed `1.0`/`1.0` risk score/threshold pair and never
  alerts on an out-of-graph (`near_train_flagged is None`) account. 2-4 new wiring tests per BP's own
  integration test file.
- `tests/integration/end_to_end/test_scoring_alert_e2e.py` (new): 8 scenarios against the real in-process
  FastAPI apps over a real `httpx` transport (Starlette's own sync `TestClient` transport, not
  `ASGITransport`, which is async-only and cannot back a sync `httpx.Client`) -- normal scoring,
  threshold-triggered alerts, duplicate suppression via idempotency, a simulated Case Management Service
  outage with retry-then-outbox, and an authorization-failure (401/403 non-retry) scenario.
- `docker-compose.yml` (new, repository root): wires all 5 scoring services + Case Management together
  via Compose's own service-name DNS, `depends_on: condition: service_healthy` gating BP startup on
  case-management's existing Docker-native `HEALTHCHECK`. `scripts/replay_alert_outbox.py` (new): the
  CLI wrapper for `replay_outbox()` promised by `_alert_dispatch.py`'s own module docstring -- 11 new
  tests (`tests/unit/test_replay_alert_outbox.py`). `.github/workflows/docker-verify.yml` gained an
  `integrated-workflow` job: builds and brings up `case-management` + `bp3-network-graph-intelligence`
  for real, POSTs a real, committed node_key from BP3's own `near_train_flagged` lookup table to BP3's
  live `/score`, and verifies against the live case-management container that a real alert was created
  with BP3's provenance intact, that an identical resubmission does not duplicate it, and that a real
  non-flagged account produces no alert.
- **296/296 total project tests passing** (up from 189) -- 0 regressions at every checkpoint.
- Docs: new `docs/architecture/SCORING_ALERT_INTEGRATION.md`; updated `ROADMAP.md`,
  `docs/security/THREAT_MODEL.md`, `docs/deployment/DEPLOYMENT_GUIDE.md`, `README.md`.
- **CI fixes from the first real push's run** (found via the Actions tab, both real failures -- no
  fabricated repro):
  - `Lint & Type Check` failed on `flake8` (E501 line-length in `casework/store.py`,
    `serving/_security.py`, and 3 test files; F401 unused imports in `serving/_alert_dispatch.py` and
    `tests/integration/end_to_end/test_scoring_alert_e2e.py`) -- all fixed by rewrapping the offending
    lines/removing the dead imports, re-verified clean against `black`/`isort`/`flake8` together. The
    same run would next have failed `mypy` (not reached the first time, since `flake8` already stopped
    the job): BP1/2/4/5's `_FIELD_TYPES` dict, built via a comprehension inferring
    `dict[str, tuple[type[float], EllipsisType]]`, was then mutated with a differently-shaped
    `(Optional[float], None)` entry for the new `entity_ref`/`transaction_ref`/`event_timestamp` fields --
    fixed with an explicit `dict[str, tuple[Any, Any]]` annotation on each.
  - `integrated-workflow` failed at `docker compose up` itself (before its own health-wait step ever
    ran): `./data/case_management`'s bind-mount source didn't exist yet on the fresh checkout, so Docker
    auto-created it as root, mode `0755` -- unwritable by the non-root `app` user every image in this
    stack runs as. Case-management's SQLite `AlertStore` opens eagerly at import time
    (`casework/store.py`), so the resulting `PermissionError` crashed the process before it could ever
    serve `/health`, its `HEALTHCHECK` never went healthy, and bp3's
    `depends_on: condition: service_healthy` made `docker compose up` fail outright. Fixed with a new
    "Prepare writable bind-mount data directories" CI step (`mkdir -p` + `chmod -R 777 data` before
    `docker compose up`) and the same note added to `docs/deployment/DEPLOYMENT_GUIDE.md` for anyone
    running the stack locally for the first time.
- **Explicitly not claimed**: a new or retrained ML model; any change to case-management's own
  lifecycle/RBAC/audit trail (reused unchanged, verified unchanged by a dedicated test); that a
  generated alert is proof of laundering (it is an automated starting point for a human investigation,
  not a verdict); or that the `integrated-workflow` job (or `Lint & Type Check`) has been observed
  passing in GitHub Actions since the fixes above -- confirm on the repository's Actions tab after the
  next push.

## 2026-10-12 (RBAC, Case Management & Audit Trails)
- **RBAC applied to a real route surface for the first time.** Added `require_any_role()` and
  `resolve_caller_role()` to `src/aml_riskiq/serving/_security.py` (the pre-existing `require_role()` and
  role-aware API keys were a primitive until now, per DEF-003 in `docs/audit/DEFECT_REGISTER.md`), plus 4
  platform role constants (`analyst`, `investigator`, `compliance_officer`, `admin`). 17 new tests in
  `tests/unit/test_security.py` (51/51 total in that file).
- **New AML case-management workflow**, built on the existing `casework` package
  (`docs/architecture/INVESTIGATOR_WORKFLOW.md`):
  - `casework/alert_schema.py` / `case_lifecycle.py`: added `CaseNote`, `EvidenceReference`, a SHA-256
    hash chain over `CaseEvent.history` (`prev_event_hash`/`event_hash`) with `verify_history_integrity()`,
    and `assign()`/`add_note()`/`add_evidence()` lifecycle functions. 12 new tests in
    `tests/unit/test_casework.py` (29/29 total).
  - `casework/store.py` (new): a real SQLite-backed `AlertStore` -- CRUD, filtered listing, transition
    persistence, assignment, notes, evidence, a reconciliation report, and `verify_integrity()`. The
    `case_events`/`case_notes`/`case_evidence` tables are append-only by construction (no `UPDATE`/`DELETE`
    anywhere in the module's own source, verified by a structural regex test). 20 new tests
    (`tests/unit/test_casework_store.py`), including a raw-SQL tampering test that confirms the hash
    chain catches an out-of-band edit on reload.
  - `src/aml_riskiq/serving/case_management_service.py` (new): a real, standalone FastAPI service --
    12 routes (create/list/get/assign alerts, notes, evidence, evidence export, status transition,
    integrity check, reconciliation, plus `/health`/`/metrics`) -- enforcing the 4 roles above via
    `require_any_role()`, with a body-dependent check on `/alerts/{id}/transition` (escalation/closure
    needs `compliance_officer`) via `resolve_caller_role()`. Its own rate-limit budget
    (`AML_RISKIQ_CASE_RATE_LIMIT`, default 120/minute) is independent of `/score`'s. 43 new integration
    tests (`tests/integration/case_management/test_case_management_service.py`): positive/negative access
    per role per route, input-validation 422s, structured audit-log verification via `caplog`, and the
    raw-DB tamper-detection test surfaced through the live `/alerts/{id}/integrity` route.
  - `src/docker/case_management/` (new Dockerfile/.dockerignore/docker-compose.yml, port 8005, same
    hardening pattern as BP1-BP5); `.github/workflows/docker-verify.yml` gained a `case-management` job
    (build, fail-closed-auth check, then a live create-alert-then-reject-unauthenticated-write 401 check
    against the running container); `.gitignore` gained `data/case_management/*.db`.
  - **189/189 total project tests passing** (up from 95); black/isort/flake8/mypy/bandit all clean on the
    new and changed code (fixed 2 flake8 line-length issues and 1 new bandit Medium false-positive in
    `store.py`'s `list_alerts`, annotated `# nosec B608` with an inline justification, same convention as
    the existing `# nosec B301` pickle.load findings).
  - **Docs**: new `docs/security/RBAC.md` (the authoritative permission matrix); updates to
    `docs/security/THREAT_MODEL.md`, `SECURITY.md`, `docs/audit/DEFECT_REGISTER.md` (DEF-003 resolved for
    this surface), `docs/architecture/INVESTIGATOR_WORKFLOW.md`, `README.md`, and
    `docs/deployment/DEPLOYMENT_GUIDE.md`.
  - **What this does not claim**: BP1-BP5's `/score` routes still have no role differentiation (no
    second route on any of them to protect, unchanged from before this phase); the hash chain is
    tamper-evidence, not tamper-proofing; SQLite is not cluster-aware; no regulatory-compliance or
    production-readiness claim is made.

## 2026-10-12
- Real re-runs of BP2 and BP3 Notebook 3 (LI-Medium) on the user's own machine, closing DEF-001 and
  DEF-002 from `docs/audit/DEFECT_REGISTER.md` (both Critical):
  - BP2: regenerated `reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json`
    (resumed Stage A/B fits from the existing checkpoint). Now carries `champion_needs_rf_impute`/
    `rf_impute_value`, 3 real LIME instance explanations, and a real FastAPI self-test (480 rows,
    0 mismatches, bit-identical). Gate 1 PASS, Gate 2 PASS, overall PASS.
  - BP3: a real, full-cost re-run (no checkpoint exists for this notebook) produced the previously-missing
    `models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet`
    (24,532,481 bytes). Fixed a `.gitignore` gap that would have silently blocked this artifact from ever
    being committed -- every other BP's champion artifact had a `!` exception carved out of the blanket
    `*.pkl`/`*.parquet` rules; BP3's never did. Gate 1 PASS, Gate 2 PASS, overall PASS, real FastAPI
    self-test (2,000 rows, 0 mismatches).
  - Corrected a stale byte count in `MODEL_REGISTRY.md` (BP3 rule JSON recorded as 2,957 bytes; the real
    on-disk file is 421 bytes -- the SHA-256 itself was already correct).
  - Re-added the `bp2` and `bp3` jobs to `.github/workflows/docker-verify.yml` (removed 2026-10-03 pending
    exactly these two fixes) and emptied `scripts/check_docker_copy_paths.py`'s now-stale
    `KNOWN_PENDING_ARTIFACTS` allowlist.

## 2026-10-10
- External benchmark-upgrade review (ChatGPT-produced blueprint) worked through in two scoped batches,
  limited to what does not require executing the real notebook/data pipeline:
  - `src/aml_riskiq/serving/_security.py`: added an opt-in fail-closed production gate
    (`AML_RISKIQ_REQUIRE_AUTH`), role-aware API keys + `require_role()` (primitive, not yet applied to
    any route), and a real `GET /metrics` endpoint (Prometheus text format, in-process counters fed by
    the existing audit middleware). 25 new tests across both additions (77/77 total passing).
  - Fixed a real, previously-disclosed-but-unfixed defect: BP2 and BP4 both EXPOSEd/mapped port 8001 --
    BP4 moved to 8004 across its Dockerfile, `docker-compose.yml`, `docker-verify.yml`, and the README
    architecture diagram.
  - Hardened all 5 scoring-service Dockerfiles: non-root `app` user, a `HEALTHCHECK` hitting the real
    `/health` endpoint. Not build-tested locally (no Docker daemon in this session) -- verification is
    `docker-verify.yml`'s next CI run.
  - New docs: `docs/audit/` (repository audit, requirement traceability matrix, defect register,
    baseline test report), `docs/governance/MODEL_RISK_GOVERNANCE.md`, `docs/business_value/
    BUSINESS_VALUE_METHODOLOGY.md` (reproduces the published $13.88M/$97.95M figures exactly from their
    real disclosed constants, plus a sensitivity table), `docs/data/LEAKAGE_AUDIT.md` (static code-reading
    audit -- found all 5 BPs use a random, non-chronological, non-entity-aware train/test split),
    `docs/security/THREAT_MODEL.md`, `docs/deployment/DEPLOYMENT_GUIDE.md`.
  - Fixed the CI badge showing red/failing: a separate Oct-3 tool/session had added `|| true` to every
    lint/type/security/test step in `ci.yml` and embedded a second, fabrication-laden Pages-deploy job
    that was hard-failing every push. Reverted to a clean, genuinely-enforcing two-job workflow.
  - Restored `README.md`, which the same Oct-3 rewrite had silently truncated to 55 lines (unclosed
    Mermaid fence) with fabricated capability claims ("Automated FinCEN SAR Drafting Platform", ISO 20022
    ingestion, wrong Apache-2.0 license badge).
  - Enabled GitHub Pages (Settings -> Pages -> Source -> GitHub Actions, a one-time manual step) --
    the per-BP live dashboard links in the README now resolve instead of 404ing.
  - Remaining work this review identified that requires real pipeline execution against real data
    (BP2/BP3 artifact regeneration, chronological re-split validation, model comparison/recalibration) is
    explicitly deferred pending direct user authorization, per this project's standing no-pipeline-
    execution rule.
  - `src/aml_riskiq/casework/`: investigator case-management foundation -- a versioned `Alert` schema built
    from each service's real `/score` response shape, a conservative case-lifecycle state machine, cross-BP
    entity clustering vs. true exact-duplicate detection, a self-checking reconciliation report, and a JSON
    evidence-export bundle. 18 new tests (95/95 total at the time), scoped honestly as not yet wired into
    any live route; surfaced a real architecture gap in the process (no transaction/account identifier in
    any `/score` request or response). `docs/architecture/INVESTIGATOR_WORKFLOW.md` records the rationale.
  - Second external review pass (8.4/10, referencing commit `913f00b`) worked through:
    - `wire_metrics_endpoint(app)` is now actually called in all 5 scoring services (`bp1`..`bp5`), not just
      defined in `_security.py` -- `GET /metrics` is live on every running service, verified with a real
      `TestClient` smoke test (not just a unit test of the helper function in isolation). 5 new integration
      tests assert this per service (100/100 total passing).
    - `docs/audit/DEFECT_REGISTER.md`: DEF-003 (RBAC) marked partially addressed -- `require_role()` exists
      and is tested but still has no second protected route to apply to; DEF-004 (`/metrics`/monitoring)
      marked partially addressed -- the endpoint is now live, but counters are in-process/per-worker only,
      there is no committed Prometheus scrape config, and `drift_monitor.py` is still not scheduled or
      exposed as a metric.
    - `docs/audit/REQUIREMENT_TRACEABILITY_MATRIX.csv`: 7 Investigator Workflow rows added, including two
      explicit `MISSING` rows for the case-management-not-wired-into-a-live-API and no-transaction-ID gaps.
    - `README.md`: security/testing/status sections reconciled against actual current code (auth-gate env
      var, role-aware keys, live `/metrics`, casework package, 100/100 tests, explicit BP2/BP3 Docker
      disclosure with a `DEFECT_REGISTER.md` cross-reference); System Architecture diagram restyled to a
      light-grey canvas (`#e5e7eb`) with darker, thicker flow lines (`#0f172a`, 3px) for contrast, and its
      stale "52 tests" CI node label corrected.
    - `docs/architecture/CASEWORK_WORKED_EXAMPLE.md` + `docs/architecture/examples/
      casework_worked_example.py`: this review's P2 item ("demonstrate one alert from scoring through
      investigation, disposition and audit reconstruction") -- a real, captured transcript of the
      `casework` package's own functions run end to end on one clearly-labeled synthetic alert, not a
      live service demo.
    - This review's P1 items that require real notebook execution against the real dataset (BP2/BP3
      artifact fix, detection-effectiveness/model-retraining) remain deferred pending explicit user
      authorization, same as the first review's equivalent items.

## 2026-10-03
- Corrected dataset-source attribution: the IBM Transactions for Anti-Money Laundering (AML) dataset is
  published by IBM at `github.com/IBM/AML-Data` (index/documentation page), with the real data files
  hosted on IBM's own Box storage (`ibm.box.com/v/AML-Anti-Money-Laundering-Data`) -- removed the
  third-party-mirror framing from `README.md` and `DATA_PRIVACY.md`.
- Added a `Dataset` section to `README.md`'s front page describing the real, verified source.
- Created the public GitHub repository (`github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite`) and pushed
  the full real commit history.
- Closed a real staleness gap in `BENCHMARKS.md`: BP5 and BP6 had completed real validation
  (see `docs/evidence_ledger/EVIDENCE_LEDGER.md`) but `BENCHMARKS.md` still read "not yet computed" --
  updated with the real figures from each BP's own `MODEL_CARD.md`/`PLATFORM_CARD.md`.
- Added this `CHANGELOG.md`, replaced `LICENSE` (MIT -> All Rights Reserved portfolio license) and
  `CODE_OF_CONDUCT.md` (custom short form -> full Contributor Covenant v2.1), and added
  `.github/CODEOWNERS`, `.github/dependabot.yml`, `.github/workflows/codeql.yml`, and
  `.github/workflows/docker-verify.yml` -- bringing this repository's governance scaffolding in line with
  the the prior credit-risk platform / the prior lending-risk platform / the prior customer-intelligence platform portfolio repos.
- Added a System Architecture diagram to the front of `README.md`.

## 2026-10-02
- Enterprise-hardening pass: added API-key authentication, rate limiting, and structured audit logging
  to all 5 FastAPI scoring services (BP1, BP2, BP3, BP4, BP5); added a model registry
  (`src/services/_model_registry.py`) exposing live SHA-256 + mtime verification under each service's
  `/health` endpoint.
- Found and fixed a real bug: 5 of 5 scoring-service Dockerfiles never copied the saved validation-report
  JSON into the image, which would have crashed every container on startup; added
  `scripts/check_docker_copy_paths.py` as a permanent regression guard, wired into CI.
- Wired `mypy` (with the pydantic plugin) and the Docker COPY-path check into CI, pre-commit, and the
  Makefile; fixed every resulting type error (0 remaining across 15 source files).
- Hardened BP6's own test coverage to close the last platform-wide gap.
- Removed `github_repo/` (a staging-mirror workaround for a git-in-mounted-folder restriction confirmed
  not to apply in this environment) and added a governance/documentation set
  (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `DATA_PRIVACY.md`, `MODEL_REGISTRY.md`, `SECURITY.md`,
  `SECRETS_MANAGEMENT.md`, `.env.example`, `ROADMAP.md`, `MONITORING.md`) matching the the prior customer-intelligence platform
  Navigator Enterprise Suite's real, verified structure.
- Initial commit: the full BP1-BP6 platform (notebooks, `src/` services, tests, Docker packaging,
  reports, configs).
