# Changelog -- IBM AML RiskIQ Enterprise Suite

Platform-level index over the full git history of this repository. Per-BP changelogs for the real
notebook/model work on each business problem live in `reports/<bp>/CHANGELOG.md` -- this file tracks the
repository's own structure, hardening, and governance history, in the same plain-date style used on the
Customer360 Navigator Enterprise Suite.

## 2026-10-03
- Corrected dataset-source attribution: the IBM Transactions for Anti-Money Laundering (AML) dataset is
  sourced directly from IBM's own GitHub repository (`github.com/IBM/AML-Data`), not a Kaggle mirror --
  removed all Kaggle references from `README.md` and `DATA_PRIVACY.md`.
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
  the AMEX RiskIQ / Home Credit RiskIQ / Customer360 Navigator portfolio repos.
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
  `SECRETS_MANAGEMENT.md`, `.env.example`, `ROADMAP.md`, `MONITORING.md`) matching the Customer360
  Navigator Enterprise Suite's real, verified structure.
- Initial commit: the full BP1-BP6 platform (notebooks, `src/` services, tests, Docker packaging,
  reports, configs).
