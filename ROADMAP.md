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
- GitHub repository structure assembled, matching this project's own `PROJECT_STRUCTURE_LOCKED.md` plus the
  governance doc set used on this portfolio's other platforms (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`,
  `DATA_PRIVACY.md`, `MODEL_REGISTRY.md`, `SECURITY.md`, `SECRETS_MANAGEMENT.md`, this file).

## In progress / pending
- **GitHub push itself** -- the local repo is fully committed and ready; it has not yet been pushed to a
  remote. Needs either a Personal Access Token (classic, `repo` scope) to push from this environment, or
  the owner pushing from their own authenticated machine.
- **`docker build` verification** -- no Docker daemon is available in the environment these notebooks and
  services were built in; every Dockerfile's `COPY` paths are statically verified
  (`scripts/check_docker_copy_paths.py`), but a real `docker build`/`docker-compose up` has never been run
  for any of the 6 images. Flagged honestly, not worked around.
- **BP3's near-train-flagged lookup Parquet** -- `models/bp3_network_graph_intelligence/
  bp3_notebook3_near_train_flagged_lookup_li_medium.parquet` does not exist on this machine yet; it is
  produced only by a real re-run of BP3 Notebook 3 (LI-Medium), per that notebook's own standing
  zero-pipeline-execution rule (Claude writes and verifies code, never executes the real notebook itself).

## Not planned
- The 4 business problems dropped from the original 8-BP draft (Account/Entity AML Risk Scoring, Alert
  Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision
  Engine) -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section for why each was dropped.
