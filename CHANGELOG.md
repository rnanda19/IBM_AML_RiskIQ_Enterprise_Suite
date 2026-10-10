# Changelog -- IBM AML RiskIQ Enterprise Suite

Platform-level index over the full git history of this repository. Per-BP changelogs for the real
notebook/model work on each business problem live in `reports/<bp>/CHANGELOG.md` -- this file tracks the
repository's own structure, hardening, and governance history, in the same plain-date style used on the
a prior customer-intelligence-focused enterprise platform in this same methodology lineage.

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
