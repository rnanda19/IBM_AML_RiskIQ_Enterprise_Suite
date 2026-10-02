# CHANGELOG -- BP5: Correspondent Banking & Cross-Border Wire Risk

## 2026-10-02T11:30:17.712275+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion XGBoost, test PR-AUC 0.1399, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp5_correspondent_banking_crossborder_risk\executive_package.

## 2026-10-02T14:53:15.394010+00:00 (hardening pass, "Global Standard" / AMEX Phase-2-hardening pattern)
Production-hardening pass on BP5's deployable scoring service and Docker packaging, closing the
gap Notebook 4 itself flagged ("No hardening pass has touched BP5 yet"). Extracted
`src/services/bp5_scoring_service.py` from Notebook 3's own in-kernel FastAPI self-test
(`score_transaction` copied verbatim -- both variants' real self-test already proved it
bit-identical to direct batch `predict_proba`, 5,000 real rows checked, 0 mismatches,
max_abs_diff=0.0, both HI-Small and LI-Medium). Unlike BP4, BP5 has no disclosed-NaN feature
column, so the service's request schema and scoring path are simpler -- no Optional/impute
branch needed. Added 5 new structural/wiring pytest tests
(`tests/bp5_correspondent_banking_crossborder_risk/test_bp5_scoring_service.py`) covering
real-saved-report loading, the `/health` and `/score` endpoints, and Pydantic validation
rejection -- all against a synthetic stub classifier (never this BP's real trained XGBoost
model or real AML data, per the standing execution-boundary rule), executed for real
on-device: 5/5 PASSED. Real bug found and fixed: `src/docker/bp5_correspondent_banking_crossborder_risk/docker-compose.yml`'s
`build.context` was `../../../..` (4 levels up from that directory) -- the same build-context
bug already fixed platform-wide for BP1-BP4 (see BP1's own CHANGELOG entry), but missed for
BP5 since it had not been hardened yet. Confirmed via `realpath --relative-to` that the
correct repo-root-relative path is `../../..` (3 levels); fixed. Dockerfile's own
"DISCLOSED GAP" comment updated to a dated "RESOLVED" note, same pattern BP3 used.
`docker-compose.yml`'s port (8002) re-checked against this platform's own port map (BP1=8000,
BP2=8001, BP3=8003, BP4=8001 -- BP4's existing collision with BP2, not touched here, out of
this pass's scope) -- confirmed no new collision.
