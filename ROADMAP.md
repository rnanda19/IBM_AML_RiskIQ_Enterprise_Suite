# Roadmap

## Done
- BP1-BP6 workstreams and their current evaluation/reporting artifacts are documented. This does **not** mean all six are deployment-verified: BP2's validation report needs a real refresh, BP3's lookup Parquet is pending, and BP6 is a batch job. See the defect register and evidence ledger for exact artifacts and limitations.
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
- Real `docker build` + `docker run` + `/health` verification runs in CI for BP1, BP4, and BP5 only. The workflow supplies a disposable CI API key because scoring containers now fail closed by default. A separate BP6 batch-job smoke test has now been added to `docker-verify.yml`; its result is pending. BP2/BP3 remain blocked on genuine data-dependent artifacts.

## In progress / pending
- Nothing currently blocked on a missing real artifact for BP1-BP5. See "Resolved 2026-10-12" below for
  the two items that were here.

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

## Not planned
- The 4 business problems dropped from the original 8-BP draft (Account/Entity AML Risk Scoring, Alert
  Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision
  Engine) -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section for why each was dropped.
