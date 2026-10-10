# Defect Register

Real defects found by direct inspection/execution during Phase 1 audit (2026-10-10). Each entry has a
file path, evidence, severity, business impact, and recommended fix. Severity: Critical (blocks a core
claim or service), High (real functional gap), Medium (real but contained), Low (hygiene).

## DEF-001 -- BP2 scoring service crashes on startup (Critical)
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
  `INITIAL_REPOSITORY_AUDIT.md`'s "Standing constraint" section) unless the user authorizes this specific
  execution.
- **Verification method**: `docker-verify.yml`'s `bp2` job (would need to be re-added) builds, starts,
  and polls `/health`.

## DEF-002 -- BP3 missing near-train-flagged lookup artifact (Critical)
- **File**: `models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet` (absent)
- **Evidence**: directory listing confirms only `.gitkeep`, `README.md`, and the rule JSON exist in
  `models/bp3_network_graph_intelligence/` -- the lookup Parquet is not present.
- **Business impact**: BP3's scoring service cannot start without this artifact; excluded from
  `docker-verify.yml`.
- **Recommended fix**: same class as DEF-001 -- produced only by a real BP3 Notebook 3 (LI-Medium)
  re-run. Blocked on the same standing rule.
- **Verification method**: artifact exists on disk with a real file size + hash recorded in
  `MODEL_REGISTRY.md`; `docker-verify.yml`'s `bp3` job builds, starts, polls `/health`.

## DEF-003 -- No RBAC at the API layer (High)
- **File**: `src/aml_riskiq/serving/_security.py`
- **Evidence**: direct read of the module -- auth is single-tier (valid key or not); no role claim,
  no role-based route restriction anywhere in `src/`.
- **Business impact**: cannot support differentiated investigator/analyst/model-administrator/auditor
  workflows as the blueprint's Prompt 6 requests; every valid API key currently has identical access to
  every protected route.
- **Recommended fix**: extend `_security.py`'s key model from a flat set to key-\>role mapping (e.g.
  `AML_RISKIQ_API_KEYS` entries become `role:key` pairs), add a `require_role(role)` dependency, apply
  per-route. This is pure code -- no pipeline execution needed. Feasible without lifting the standing rule.

## DEF-004 -- No live monitoring, `/metrics`, or scheduled alerting (High)
- **File**: n/a (absence confirmed by grep across `src/`)
- **Evidence**: `MONITORING.md` already discloses this; grep confirms no `prometheus`, `/metrics` route,
  `apscheduler`, or `celery` anywhere in `src/`.
- **Business impact**: `drift_monitor.py`'s real PSI implementation is a library function only -- nothing
  calls it on a schedule, nothing exposes its output as a scrapeable metric, nothing alerts on it.
- **Recommended fix**: add a `/metrics` route per service (even a minimal one exposing request counts,
  latency, and the model-registry fingerprint already computed for `/health`) and a documented way to run
  `drift_monitor.py` on a schedule (a cron entry calling a small script, not a new service framework).
  Pure code/infra-config -- no pipeline execution needed.

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
