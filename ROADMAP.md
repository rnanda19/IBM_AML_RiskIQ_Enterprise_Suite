# Roadmap

## Done
- BP1-BP6 workstreams and their current evaluation/reporting artifacts are documented. BP2's and BP3's real
  artifacts were regenerated 2026-10-12 (see "Resolved 2026-10-12" below) and `docker-verify.yml`
  builds/starts/polls `/health` for all 5 scoring services plus a separate BP6 batch check -- this is now
  **confirmed live-CI-passing**: commit `eb00ac9` has all 15 required checks green together (`ci.yml` on
  Python 3.10 and 3.11, `docker-verify.yml` incl. `integrated-workflow`, `codeql.yml`, `code-quality.yml`),
  verified via GitHub's check-runs REST API (see "Resolved 2026-10-12 -- CI fixes after first real push"
  below for how the two real failures on the first push were found and fixed). The latest commit on `main`,
  `4c134f1` (adds the chronological/entity-aware validation module; no app or Docker code changed), was
  independently reverified green the same way -- see "Resolved 2026-10-12 -- CI re-verified on commit
  `4c134f1`" below. See the defect register and evidence ledger for exact artifacts and limitations.
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
  `/health`). This has been confirmed passing: commit `eb00ac9` has every `docker-verify.yml` job green,
  including the `integrated-workflow` job described below; `4c134f1` (current `main` tip) re-confirmed the
  same 4 `docker-verify.yml` jobs green on 2026-10-12.
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
- **Strengthening AML model-validation evidence** (started 2026-10-12, code complete 2026-10-12):
  `docs/data/LEAKAGE_AUDIT.md` documents six findings now (L-1 through L-6) -- random (non-chronological)
  splitting and no explicit entity-level separation across BP1/BP2/BP4/BP5 (L-1/L-2, methodological risks,
  not proof the published metrics are wrong), confirmation that no scaler/imputer/resampler/selector
  exists anywhere in the pipeline and the one real train-only-imputation case is fit correctly (L-3), no
  target leakage found in any `FEATURE_COLS` (L-4), a real read-only duplicate-record check (L-5;
  HI-Small negligible, LI-Medium blocked by this project's current device RAM), and the new reusable
  `src/aml_riskiq/validation/temporal_entity_validation.py` module (L-6) -- chronological/entity-aware
  splits, PR-AUC/ROC-AUC/confusion-matrix/FPR/alert-volume/calibration/threshold trade-offs, transparent
  baselines, dataset fingerprinting and environment capture, covered by 41 passing synthetic-fixture unit
  tests and the full flake8/black/isort/mypy/bandit gate. Wired into every BP's own
  `03_statistical_validation_deployment_SINGLE_CELL.py` (BP1/BP4/BP5: real champion re-fit per split;
  BP2: baseline-only, multiclass-safe; BP3: chronological-by-first-seen-account re-validation of its real
  lift-ratio signal, entity-separation confirmed already satisfied by BP3's own node-level split). Per
  this project's standing execution boundary, this is all written and unit-tested code -- the real
  chronological/entity-aware numbers for BP1-BP5 against the actual dataset appear only once you run the
  updated notebooks on your own machine; see each BP's `reports/<bp>/*_temporal_entity_validation_*` (or,
  for BP3, `*_temporal_validation_*`) output path, and `BENCHMARKS.md`'s "Validation methodology and
  known risks" section.

## Resolved 2026-10-12
- **BP2's Docker image wouldn't start** (found 2026-10-03) -- fixed by a real re-run of BP2 Notebook 3
  (LI-Medium) on the maintainer's own machine, resuming Stage A/B fits from the existing checkpoint. The
  regenerated report carries `champion_needs_rf_impute`/`rf_impute_value`, real LIME explanations, and a
  real FastAPI self-test (480 rows, 0 mismatches). `bp2` re-added to `docker-verify.yml`.
- **BP3's near-train-flagged lookup Parquet was missing** -- fixed by a real, full-cost re-run of BP3
  Notebook 3 (LI-Medium) (no checkpoint exists for this notebook). The lookup Parquet
  (24,532,481 bytes, sha256 recorded in `MODEL_REGISTRY.md`) was also blocked from ever being committed by
  a `.gitignore` gap -- every other BP's champion artifact had a `!` exception carved out of the blanket
  `*.pkl`/`*.parquet` rules, but BP3's never did; that exception is now added. `bp3` re-added to
  `docker-verify.yml`.

## Resolved 2026-10-12 -- CI fixes after the first real push of the integration phase
The "Added 2026-10-12 -- End-to-End AML Workflow Integration" work below was pushed, and its first real
GitHub Actions run (commit `c5e4da74`) genuinely failed two jobs -- found via GitHub's unauthenticated
check-runs/annotations/jobs REST API (job-log downloads require authenticated scope even on a public repo,
so step-by-step job status was the available signal; nothing here was guessed).
- **`Lint & Type Check` failed at its `flake8` step** (black/isort/mypy never ran that time, since the job
  stops on first failure): real `E501` line-length violations in `casework/store.py`, `serving/_security.py`,
  and 3 test files, plus genuinely-unused imports (`ScoringEvent` in `serving/_alert_dispatch.py`,
  `dispatch_alert` in `test_scoring_alert_e2e.py`). Fixed by rewrapping the offending lines and removing
  the dead imports. Running black/isort/mypy for real afterward (not just guessing they'd pass) also found
  and fixed: 2 more pre-existing drifted files under `black`, and a real `mypy` bug in BP1/2/4/5 --
  `_FIELD_TYPES`'s dict comprehension inferred a narrower tuple type than the new
  `entity_ref`/`transaction_ref`/`event_timestamp` fields' `(Optional[float], None)` shape, fixed with an
  explicit `dict[str, tuple[Any, Any]]` annotation.
- **`integrated-workflow` failed at `docker compose up` itself**, before its own health-wait step ever ran:
  `./data/case_management` doesn't exist on a fresh checkout, so Docker auto-created the bind-mount source
  as root, mode `0755` -- unwritable by the non-root `app` user every image in this stack runs as.
  case-management's SQLite `AlertStore` opens eagerly at import time, so the resulting `PermissionError`
  crashed the container before it could serve `/health`; its `HEALTHCHECK` never went healthy, and bp3's
  `depends_on: condition: service_healthy` made `docker compose up` fail outright. Fixed with a new
  "Prepare writable bind-mount data directories" CI step (`mkdir -p` + `chmod -R 777 data`), and the same
  note added to `docs/deployment/DEPLOYMENT_GUIDE.md` since it is a real local-deployment gotcha too.
- Both fixes committed as `eb00ac9` and pushed. **Confirmed green on the real re-run**: all 15 check runs
  on `eb00ac9` -- `Lint & Type Check`, `Pytest (Py 3.10)`, `Pytest (Py 3.11)`, `integrated-workflow`, `bp1`
  through `bp5`, `bp6-batch`, `case-management`, `bandit-security-scan`, `format-check`,
  `Analyze (python) (python)` (CodeQL), and `Dependabot` -- succeeded, with every step of
  `integrated-workflow` (including the real alert-creation, duplicate-suppression, and non-flagged-account
  checks) actually running rather than being skipped. This is the first commit in this project with every
  required check observed green together.

## Resolved 2026-10-12 -- CI re-verified on commit `4c134f1`
The validation-framework work above (`temporal_entity_validation.py` + its 41 unit tests + the BP1-BP5
notebook wiring + `LEAKAGE_AUDIT.md`/`BENCHMARKS.md` updates) was committed as
`4c134f16a3ba59aa99c9abd9032072f1942c7c9f` and pushed to `main` on top of `eb00ac9`. Its real GitHub
Actions results were fetched directly from GitHub's check-runs REST API (unauthenticated, from the maintainer's
own machine -- no authenticated GitHub API access was used), not assumed from the prior commit's green run:
- 4 workflow runs, all `conclusion: success`: `CI` (run 38259440422), `Code Quality` (38259440671),
  `CodeQL Security Scan` (38259440844), `Docker Build & Run Verification` (38259440418).
- 14 check runs, all `conclusion: success`: `Pytest (Py 3.10)`, `Pytest (Py 3.11)`, `Lint & Type Check`,
  `format-check`, `bandit-security-scan`, `Analyze (python) (python)` (CodeQL), `bp1`-`bp5`, `bp6-batch`,
  `case-management`, `integrated-workflow`. (One fewer than `eb00ac9`'s 15 -- `Dependabot` simply did not
  run on this push, since no dependency file changed; every other required job ran for real.)
- Confirmed by reading `.github/workflows/docker-verify.yml`'s source directly (not just the green badge)
  that `integrated-workflow`'s steps assert exactly the four behaviours this platform's integration
  guarantees require: a known-flagged account's real `/score` call creates a case-management alert with
  scoring provenance intact ("Verify a real alert was created in case-management, with provenance intact"),
  an identical resubmission does not create a duplicate ("Verify re-submitting the identical account does
  not create a duplicate alert"), a non-flagged account produces no alert ("Verify an unflagged account
  produces no alert"), and `case-management`'s own steps assert the RBAC/auth behaviour ("Verify missing
  API key fails closed", "Exercise the real RBAC matrix against the running container" -- an unauthenticated
  write is rejected with a real `401`). All of these run as real HTTP calls against live
  `docker compose up` containers, not mocked.
- Confirmed all 6 Docker images (`src/docker/*/Dockerfile`) run as a non-root `USER app`.
- Not independently verifiable this pass: raw per-step job logs
  (`.../actions/jobs/{id}/logs` returns `403 Must have admin rights to Repository` even on this public
  repo) and the CodeQL code-scanning alerts list (`.../code-scanning/alerts` returns `401`) -- both need
  the repository owner's own authenticated session, not just public read access. This does not weaken the
  pass/fail evidence above: GitHub marks a check run `failure` if any step inside it -- including every
  assertion step quoted above -- exits non-zero, so a `success` conclusion is real evidence those
  assertions executed and passed, not merely that the job was attempted.
- No code change was required this pass -- every required check was already green on the pushed commit.

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
  own lifecycle/RBAC/audit trail (reused unchanged), or that a generated alert is proof of laundering (it
  is an investigation starting point, not a verdict). The `integrated-workflow` CI job's first real run did
  fail (a real bind-mount permission bug, not a flaky test) -- see "Resolved 2026-10-12 -- CI fixes after
  the first real push" below for the fix and the confirmed-green re-run.

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

## Added 2026-10-12 -- Production-Readiness & Operational Resilience (Improvement 3)
- **Fixed a real security/robustness gap**: BP1/BP2/BP4/BP5's `/score` schemas silently accepted
  `NaN`/`Infinity` feature values (producing a fabricated-looking score) and, once rejected, the
  resulting FastAPI validation-error response itself crashed with a 500 (`ValueError: Out of range
  float values are not JSON compliant`, then `TypeError: Object of type ValueError is not JSON
  serializable`) rather than returning a clean error. Fixed once, shared everywhere: a new
  `FiniteFloatFieldsModel` (`serving/_request_validation.py`) wired as every affected BP's
  `create_model(__base__=...)`, plus a new `_json_safe()` + `_validation_error_handler()` pair in
  `_security.py` wired into `harden_app()`. The same gap existed in the Case Management Service's
  public `Alert`/`AlertCreateRequest` models (its internal `ScoringEvent` already guarded against it)
  -- fixed with the same `field_validator` pattern already used there.
- **Request correlation IDs**: every one of the 6 HTTP services now reads/generates an `X-Request-ID`
  (`serving/_security.py`'s `AuditLogMiddleware`), echoes it on the response, and records it in the
  structured audit-log line.
- **Real `/ready` endpoints**: all 6 services now expose `GET /ready` (via a new
  `wire_readiness_endpoint()` helper), distinct from the existing `/health` -- each with a real,
  service-appropriate check (model-loaded for BP1/2/4/5, lookup-table-loaded for BP3, DB-reachable for
  case management), returning 503 with the specific failing check(s) rather than a blanket 200.
- **Secrets-hygiene audit** (`SECRETS_MANAGEMENT.md`): a grep-based scan across every git-tracked file
  for hardcoded keys/tokens/passwords came back clean. **Known gap, not yet delivered**: no dedicated
  automated secret-scanning CI hook (e.g. `gitleaks` or `detect-secrets`) exists yet -- the audit so far
  is a manual, point-in-time pass, not a continuously-enforced control. Adding that hook is open work.
- **Resilience test plan** (`docs/operations/RESILIENCE_TEST_PLAN.md`): honestly separates what is
  automated/verified today (duplicate-event handling, dependency-failure recovery via the existing
  outbox pattern, interrupted-write atomicity via fault injection on `AlertStore._append_event_row`,
  service-restart recovery via a fresh `AlertStore` instance against the same SQLite file -- the latter
  two added this pass) from what would need live Docker infrastructure the local review environment does not have.
- **Reproducibility evidence** (`docs/operations/REPRODUCIBILITY.md`): confirmed `requirements.txt` is
  fully version-pinned, confirmed the documented install+test commands match `ci.yml`'s own clean-runner
  sequence exactly, confirmed no unseeded randomness exists anywhere in `tests/`, and found + fixed a
  real `.env.example` gap -- 9 of 13 real `AML_RISKIQ_*` environment variables (the Case Management
  Service's DB path and all of the scoring-to-alert dispatch settings, plus the project-root override)
  were read by the code but undocumented in the example file. Now all 13 are documented, and
  `tests/unit/test_env_example_completeness.py` makes this a permanent regression guard. A literal
  from-scratch `git clone` + from-scratch `pip install` reproduction was attempted in this review
  session but abandoned as unreliable on the mounted-folder filesystem used for local work (disclosed in that doc
  rather than reported as passing); CI's own continuous clean-runner execution stands in its place.
- **New input/data-quality monitoring module** (`src/aml_riskiq/monitoring/data_quality.py`, see
  `MONITORING.md`): schema validation, missing-value reporting, baseline-quantile-derived out-of-range
  detection, per-feature PSI drift (reusing `drift_monitor.py`'s existing PSI function), alert-volume
  anomaly detection, and a `recommend_retraining_review()` verdict that never recommends automatic
  retraining -- only that a human review the model. `baseline_is_synthetic` is a required (no-default)
  parameter so a report can never silently imply live production monitoring it isn't doing. Wired into
  BP1's Notebook 3 only so far (same "first real consumer" precedent `drift_monitor.py` itself set);
  extending this to BP2-BP5's own Notebook 3 scripts is open work.
- **New/extended automated tests**: `tests/unit/test_request_validation.py` (10), a from-scratch
  `tests/unit/test_drift_monitor.py` (13, filling a pre-existing gap -- that module had no test file at
  all before this pass despite its own docstring claiming test coverage), `tests/unit/test_data_quality.py`
  (29), `tests/unit/test_env_example_completeness.py` (3), ~25 new security tests in
  `tests/unit/test_security.py` (JSON-safety/validation-handler, correlation IDs, readiness), 2 new
  resilience tests in `tests/unit/test_casework_store.py`, and new negative-path/readiness integration
  tests across every BP's scoring-service test file and the case-management test file -- all
  auto-discovered by `ci.yml`'s existing `pytest tests/` call. Local suite: 425/425 passing as of this
  pass (not yet re-confirmed against a fresh CI run -- see `README.md`'s "Status" section).
- Docs: `MONITORING.md`, `SECRETS_MANAGEMENT.md`, `docs/deployment/DEPLOYMENT_GUIDE.md` (also fixed a
  stale paragraph that predated this project's own later, real confirmation that the
  `integrated-workflow` CI job had passed), `README.md`, this file.
- **Explicitly not claimed**: production readiness from any of the above; a live, continuously-running
  monitoring or secret-scanning process; a real Docker-daemon-backed resilience test (service restart,
  dependency outage) in the local review environment -- those remain CI-only or manual-run evidence, not something this
  review session executed itself.

## Not planned
- The 4 business problems dropped from the original 8-BP draft (Account/Entity AML Risk Scoring, Alert
  Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision
  Engine) -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section for why each was dropped.
