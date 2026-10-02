# Evidence Ledger - IBM AML RiskIQ

Single source of truth for BP completion status. No BP is marked complete anywhere else -
README, LinkedIn post, or conversation - without a row here showing a real Evidence Ledger
entry. Locked 6-BP scope (BP1-BP6) per claude/master-execution-plan.md v2.0 (2026-09-29) --
the v1.0 draft's BP7/BP8 rows below are retired, not pending.

Every cell below was re-read directly from the real, on-disk validation-report JSON cited in
its "Artifact ref" column on 2026-10-02 (not carried forward from memory/claim) -- this table
itself is regenerable at any time by re-reading those same files.

| BP | Gate reached | Real-run confirmed? | Key real metric (mandatory LI-Medium tier) | Artifact / commit ref |
|----|--------------|----------------------|------------------|------------------------|
| BP1 | Gate1+Gate2 | PASS (HI-Small + LI-Medium) | Champion XGBoost, test PR-AUC 0.1242 | `reports/bp1_transaction_monitoring_detection/bp1_notebook3_validation_report_li_medium.json` |
| BP2 | Gate1+Gate2 | PASS (LI-Medium) | Champion RandomForest, test macro-F1 0.4440 | `reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json` |
| BP3 | Gate1+Gate2 | PASS (LI-Medium) | Champion signal '2-hop proximity to a TRAIN-flagged account', network-lift ratio 3.19x | `reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_li_medium.json` |
| BP4 | Gate1+Gate2 | PASS (HI-Small + LI-Medium) | Champion XGBoost, test PR-AUC 0.1253 | `reports/bp4_structuring_smurfing_detection/bp4_notebook3_validation_report_li_medium.json` |
| BP5 | Gate1+Gate2 | PASS (HI-Small + LI-Medium) | Champion XGBoost, test PR-AUC 0.1399 | `reports/bp5_correspondent_banking_crossborder_risk/bp5_notebook3_validation_report_li_medium.json` |
| BP6 | Structural/reconciliation gate | PASS (pure rollup of BP1-BP5's own figures; no model of its own) | overall_verdict PASS, rolled up from the 5 rows above | `reports/bp6_enterprise_compliance_monitoring/bp6_notebook3_platform_validation_report.json` |

Retired (v1.0 8-BP draft, superseded 2026-09-29 -- not part of the locked scope, listed here
only so this history is not silently lost):
- Account/Entity AML Risk Scoring -- dropped, no independent ground truth in this dataset.
- Alert Escalation/SAR-Filing Prediction -- dropped, same reason.
- GenAI SAR Narrative Assistant (originally "BP6" in the v1.0 draft) -- dropped; the locked
  BP6 is an unrelated pure rollup, not this.
- Alert Prioritization & Case Decision Engine -- dropped, same reason.

Local git: HEAD at commit 8055a9d as of this ledger update (2026-10-02) -- no GitHub remote
pushed yet, see LESSONS_LEARNED_APPLIED.md Lesson #49.
