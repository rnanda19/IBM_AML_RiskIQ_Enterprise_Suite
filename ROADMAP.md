# Roadmap

## Done
- All 6 business problems (BP1-BP6): every gate real-run confirmed end to end, both mandatory (LI-Medium)
  and stretch (HI-Small, where applicable) tiers. See `docs/evidence_ledger/EVIDENCE_LEDGER.md` for the
  real metric + exact artifact path behind every PASS verdict.
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
- Real `docker build` + `docker run` + `/health` verification now runs in CI for BP1, BP4, and BP5
  (`.github/workflows/docker-verify.yml`) -- confirms more than static COPY-path checking: the containers
  actually build, start, and serve a real request.

## In progress / pending
- **BP2's Docker image won't start** (found 2026-10-03, first real CI run of `docker-verify.yml`) --
  `reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json` was generated
  2026-10-01, before a 2026-10-02 hardening edit added two required keys (`champion_needs_rf_impute`,
  `rf_impute_value`) that `src/services/bp2_scoring_service.py` now reads at import time. The container
  builds and starts, but the uvicorn worker crashes immediately with a real `KeyError`. Fix: re-run BP2
  Notebook 3 for LI-Medium -- `rf_impute_value` is a real train-median that must come from an actual run on
  real data, never invented here. BP2 is excluded from `docker-verify.yml` until that re-run happens.
- **BP3's near-train-flagged lookup Parquet** -- `models/bp3_network_graph_intelligence/
  bp3_notebook3_near_train_flagged_lookup_li_medium.parquet` does not exist on this machine yet; it is
  produced only by a real re-run of BP3 Notebook 3 (LI-Medium), per that notebook's own standing
  zero-pipeline-execution rule (Claude writes and verifies code, never executes the real notebook itself).
  BP3 is excluded from `docker-verify.yml` for the same reason.

## Not planned
- The 4 business problems dropped from the original 8-BP draft (Account/Entity AML Risk Scoring, Alert
  Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision
  Engine) -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section for why each was dropped.
