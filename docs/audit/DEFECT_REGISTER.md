# Defect Register

Real defects found by direct inspection/execution during Phase 1 audit (2026-10-10). Each entry has a
file path, evidence, severity, business impact, and recommended fix. Severity: Critical (blocks a core
claim or service), High (real functional gap), Medium (real but contained), Low (hygiene).

## DEF-001 -- BP2 scoring service crashes on startup (Critical) -- RESOLVED 2026-10-12
- **File**: `src/aml_riskiq/serving/bp2_scoring_service.py`; `reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json`
- **Evidence**: `.github/workflows/docker-verify.yml`'s own header comment documents the real `KeyError`
  (confirmed, not re-derived fresh this pass): the committed validation report was generated 2026-10-01,
  before a 2026-10-02 code change added two keys (`champion_needs_rf_impute`, `rf_impute_value`) the
  service now reads unconditionally at import time.
- **Business impact**: BP2's Docker image cannot serve traffic at all. It is excluded from
  `docker-verify.yml` as a result -- one of the platform's 6 BPs is not independently deployment-verified.
- **Recommended fix**: re-run BP2 Notebook 3 (LI-Medium) to regenerate the validation report with the
  real train-median `rf_impute_value`. This value must come from an actual run on real data -- it cannot
  be invented or hand-written. **Blocked on the standing no-pipeline-execution rule** (see
  `INITIAL_REPOSITORY_AUDIT.md`'s "Standing constraint" section) unless the maintainer authorizes this specific
  execution.
- **Verification method**: `docker-verify.yml`'s `bp2` job (re-added 2026-10-12) builds, starts, and
  polls `/health`.
- **Resolution (2026-10-12)**: user re-ran BP2 Notebook 3 (LI-Medium) on their own machine (resumed
  Stage A/B fits from the existing checkpoint). Regenerated report now carries
  `champion_needs_rf_impute: true`, `rf_impute_value: 1.0`, plus real LIME explanations and a real
  FastAPI self-test (480 rows, 0 mismatches) -- `generated_at_utc: 2026-10-12T04:41:50Z`. Committed in
  `62c06fb`.

## DEF-002 -- BP3 missing near-train-flagged lookup artifact (Critical) -- RESOLVED 2026-10-12
- **File**: `models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet` (absent)
- **Evidence**: directory listing confirms only `.gitkeep`, `README.md`, and the rule JSON exist in
  `models/bp3_network_graph_intelligence/` -- the lookup Parquet is not present.
- **Business impact**: BP3's scoring service cannot start without this artifact; excluded from
  `docker-verify.yml`.
- **Recommended fix**: same class as DEF-001 -- produced only by a real BP3 Notebook 3 (LI-Medium)
  re-run. Blocked on the same standing rule.
- **Verification method**: artifact exists on disk with a real file size + hash recorded in
  `MODEL_REGISTRY.md`; `docker-verify.yml`'s `bp3` job (re-added 2026-10-12) builds, starts, polls
  `/health`.
- **Resolution (2026-10-12)**: user re-ran BP3 Notebook 3 (LI-Medium) on their own machine (no
  checkpoint exists for this notebook, so this was a full-cost re-run). The lookup Parquet now exists
  (24,532,481 bytes, sha256 `c21cbd395b04d025f2e3592b2ccb5abb7b2bb6d4a06565ce295e669f50222596`) and is
  tracked in git -- it was previously excluded by `.gitignore`'s blanket `*.parquet` rule with no `!`
  exception carved out for it, unlike every other BP's champion artifact; that exception is now added.
  Regenerated report: Gate 1 PASS, Gate 2 PASS, overall PASS, real FastAPI self-test (2,000 rows, 0
  mismatches) -- `generated_at_utc: 2026-10-12T04:49:33Z`.

## DEF-003 -- No RBAC at the API layer (High) -- RESOLVED 2026-10-12 (case-management surface)
- **File**: `src/aml_riskiq/serving/_security.py`
- **Evidence (original)**: direct read of the module -- auth was single-tier (valid key or not); no role
  claim, no role-based route restriction anywhere in `src/`.
- **Update (earlier this project)**: role-aware API keys and `require_role()` were added to `_security.py`
  in a later batch (tested, 8 new tests). **Still not applied to any route** -- each of the 5 scoring
  services had only `/health` (unauthenticated) and `/score` (any valid key, any role), so there was not
  yet a second route for a role distinction to protect. The `casework` package added afterward (see
  `docs/architecture/INVESTIGATOR_WORKFLOW.md`) was exactly the kind of second surface `require_role()`
  was built for, but it was not wired into any live route either.
- **Resolution (2026-10-12)**: a new, real, live FastAPI service -- the Case Management Service
  (`src/aml_riskiq/serving/case_management_service.py`) -- was built directly on the `casework` package
  and its routes genuinely enforce RBAC. 4 distinct roles (`analyst`, `investigator`,
  `compliance_officer`, `admin`) are enforced across 12 routes via a new `require_any_role()` primitive
  (plus a new `resolve_caller_role()` primitive for the one route, `/alerts/{id}/transition`, whose
  required role depends on the request body rather than the route alone). `docs/security/RBAC.md` is the
  authoritative permission matrix; `tests/integration/case_management/test_case_management_service.py`
  (43 tests, positive and negative, every ✅/❌ cell in that matrix covered) is the automated proof.
  Unauthorized access and privilege-escalation attempts are explicitly tested (wrong role on an allowed
  route → 403 naming the caller's actual role and the accepted set; missing/invalid key → 401; an
  `investigator` who clears the route-level gate on `/transition` but targets `escalated`/`closed` is
  still blocked at the body-level check).
- **What this resolves and what it does not**: this closes DEF-003 for the case-management surface this
  phase built. It does **not** retroactively add role differentiation to BP1-BP5's `/score` routes --
  those still have only `/health` and a single-tier `/score`, so there is still no second route on any of
  them for a role distinction to protect. That remainder is unchanged from the "Update" note above and is
  tracked below as still open.
- **Business impact**: resolved for case-management access control; unchanged for the 5 scoring services.
- **Recommended fix (remaining, scoring services only)**: if/when a second, more sensitive route is added
  to any of BP1-BP5 (e.g. a model-reload or config-change endpoint), protect it with the same
  `require_any_role()` primitive used here -- the mechanism is proven, only the scoring services' route
  surface is still too thin to need it.

## DEF-004 -- No live monitoring, `/metrics`, or scheduled alerting (High) -- PARTIALLY ADDRESSED
- **File (original)**: n/a (absence confirmed by grep across `src/`)
- **Evidence (original)**: `MONITORING.md` already disclosed this; grep confirmed no `prometheus`,
  `/metrics` route, `apscheduler`, or `celery` anywhere in `src/`.
- **Update**: `render_metrics()`/`wire_metrics_endpoint()` were added to `_security.py` (Prometheus text
  format, real in-process request-count + latency counters, unauthenticated by design) and -- unlike
  DEF-003's `require_role()` -- actually mounted: `wire_metrics_endpoint(app)` is now called in all 5
  scoring services (`bp1`..`bp5`) right after `harden_app(app, ...)`. Verified live, not just unit-tested:
  a `TestClient` smoke test against the real `bp1_scoring_service` module (synthetic stub model, same
  fixture pattern as `tests/integration/.../test_bp1_scoring_service.py`) confirmed `GET /metrics` returns
  200 with a real counter line reflecting the preceding `GET /health` call.
- **Still open**: counters are in-process and per-worker (not shared across `uvicorn --workers N` or across
  service restarts -- `MONITORING.md`'s multi-worker caveat applies), there is no scrape config
  (`prometheus.yml`) or dashboard committed, and `drift_monitor.py`'s PSI implementation is still a
  library function only -- nothing calls it on a schedule or exposes its output as a metric, and there is
  no alerting.
- **Business impact (remaining)**: request-level observability now exists per-worker; model-drift
  observability and any alerting still do not.
- **Recommended fix (remaining)**: add a committed `prometheus.yml` scrape target as deployment docs, and
  a documented way to run `drift_monitor.py` on a schedule (a cron entry calling a small script, not a new
  service framework) that exposes its PSI output as a metric. Pure code/infra-config -- no pipeline
  execution needed.

## DEF-005 -- BRD/FRD/RTM are unfilled stubs (Medium)
- **File**: `docs/BRD/README.md`, `docs/FRD/README.md`, `docs/RTM/README.md`
- **Evidence**: each file's entire content is a one-line placeholder.
- **Business impact**: no formal requirement-traceability artifact existed before this audit pass
  (`REQUIREMENT_TRACEABILITY_MATRIX.csv`, written this pass, is the first one).
- **Recommended fix**: either fill BRD/FRD from the already-real `README.md`/`BENCHMARKS.md` content, or
  retire the stubs and point to `docs/audit/REQUIREMENT_TRACEABILITY_MATRIX.csv` as the canonical
  traceability artifact going forward (recommend the latter -- avoids maintaining the same facts in two
  places).

## DEF-006 -- No model-risk governance document (Medium)
- **File**: n/a
- **Evidence**: intended use, prohibited uses, and change-approval process are not written down anywhere
  as a single document; pieces exist scattered (`MODEL_REGISTRY.md`'s versioning, README's synthetic-data
  caveats).
- **Business impact**: the blueprint's Prompt 6 model-lifecycle governance ask has no home.
- **Recommended fix**: new `docs/governance/MODEL_RISK_GOVERNANCE.md` consolidating intended use,
  prohibited uses, versioning/rollback procedure (referencing `MODEL_REGISTRY.md`'s real fingerprinting),
  and change-approval process. Pure documentation -- no pipeline execution needed.

## DEF-007 -- No business-value assumption / sensitivity-analysis doc (Low)
- **File**: `BENCHMARKS.md` (figures already labeled ASSUMPTION/illustrative)
- **Evidence**: direct read confirms every dollar figure already carries an explicit "(ASSUMPTION)" or
  "illustrative" label and a one-line basis (investigator-hours, case counts) -- this is better than the
  external review implied, but there is no standalone methodology doc showing the hourly-cost assumption,
  per-case-value assumption, or a sensitivity range across them.
- **Business impact**: low -- the core ask (don't present assumptions as measured results) is already
  met. The gap is depth/auditability of the assumption, not mislabeling.
- **Recommended fix**: new `docs/business_value/BUSINESS_VALUE_METHODOLOGY.md` showing the real constants
  the report_builder code uses for investigator-hour cost and per-case value, plus a sensitivity table
  (e.g. +/-25% on each input). Pure documentation/arithmetic over already-real inputs -- no pipeline
  execution needed, as long as it only presents existing code's real constants rather than inventing new
  ones.

## DEF-008 -- No leakage audit document (Medium, partially blocked)
- **File**: n/a
- **Evidence**: no `docs/data/LEAKAGE_AUDIT.md` or equivalent exists.
- **Business impact**: cannot currently state with documented evidence that there is no target/temporal/
  entity leakage across BP1-BP5's train/test splits.
- **Recommended fix**: two parts. (1) Static code audit of each BP's `02_feature_engineering_modeling`
  and `03_statistical_validation_deployment` scripts for leakage patterns (features derived from the
  label, test rows present during fit, non-chronological splits where chronology matters) -- this is
  pure code reading, feasible without lifting the standing rule. (2) Confirming the audit's findings
  empirically (re-running a split with a chronology check) requires real pipeline execution and is
  blocked on the same standing rule as DEF-001/DEF-002.
