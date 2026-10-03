# CHANGELOG -- BP1: Transaction Monitoring & Suspicious Activity Detection

## 2026-09-30T12:35:29.152540+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1242, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp1_transaction_monitoring_detection\executive_package.

## 2026-09-30T12:47:32.326594+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1242, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp1_transaction_monitoring_detection\executive_package.

## 2026-09-30T13:11:55.072795+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1242, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp1_transaction_monitoring_detection\executive_package.

## 2026-09-30T13:20:22.897371+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1242, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp1_transaction_monitoring_detection\executive_package.

## 2026-10-01T06:45:42.976904+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1242, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp1_transaction_monitoring_detection\executive_package.

## 2026-10-02T00:00:00+00:00 (hardening pass, "Global Standard" / that prior platform Phase-2-hardening pattern)
Production-hardening review of this BP's existing deployable service and Docker packaging (src/services/bp1_scoring_service.py was already present and correct -- reviewed, not rebuilt). Real bug found and fixed PLATFORM-WIDE (affects all 4 BPs' docker-compose.yml identically, same copy-paste origin): each docker-compose.yml's `build.context` was `../../../..` (4 levels up from src/docker/<bp>/), one level too high -- confirmed via `realpath --relative-to` that the correct repo-root-relative path from that directory is `../../..` (3 levels). Left uncorrected, `docker-compose build` would have resolved its context to the parent of the project folder, where none of the COPY paths (requirements.txt, src/, models/...) exist -- a real, silent future failure, never hit yet only because no docker-compose build had been run. Fixed in all 4 BPs' docker-compose.yml. Added 5 new structural/wiring pytest tests (tests/bp1_transaction_monitoring_detection/test_bp1_scoring_service.py) covering real-saved-report loading, the /health and /score endpoints, and Pydantic validation rejection -- all against a synthetic stub classifier (never this BP's real trained model or real AML data, per the standing execution-boundary rule), executed for real on-device: 5/5 PASSED. Added root-level governance scaffolding this session (BENCHMARKS.md, pyproject.toml, Makefile, .pre-commit-config.yaml, code-quality.yml CI job, .github/ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md) -- shared across all BPs, see repo root CHANGELOG context in LESSONS_LEARNED_APPLIED.md Lesson #38.
