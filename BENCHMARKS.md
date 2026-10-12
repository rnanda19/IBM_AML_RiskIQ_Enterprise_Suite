# BENCHMARKS -- IBM AML RiskIQ Enterprise Suite

Consolidated real baseline-vs-model comparisons across every BP that has completed real validation --
all 6 of them (BP1-BP6). Every figure below is copied verbatim from that BP's own `reports/<bp>/MODEL_CARD.md`,
`RULE_CARD.md`, or (for BP6) `PLATFORM_CARD.md` (grep-verified against the source file; BP1-BP4 verified
2026-10-02, BP5/BP6 verified 2026-10-03 against the real on-disk validation reports after a staleness check
against `docs/evidence_ledger/EVIDENCE_LEDGER.md` found this document had not been updated since BP5/BP6
completed) -- nothing here is estimated or recomputed independently of that BP's own real Notebook 3/4 run. Primary reported variant for
every BP is LI-Medium (the platform's locked mandatory realism-validation tier, Section 2.1 of the master
plan); HI-Small is reported alongside where available, for continuity, never blended into one figure.

Hard rule carried from Section 7A of the master plan: false-positive-reduction $ savings and true-positive/
typology-confirmation uplift are always two separate lines, never summed into one blended dollar figure.

## BP1 -- Transaction Monitoring & Suspicious Activity Detection
Champion: XGBoost | Random seed 42 | Feature count: 19 | Status: RECOMMENDED FOR PRODUCTION (both gates PASS, HI-Small + LI-Medium)

| Variant | Test PR-AUC | Precision | Recall | F2 | Threshold | Verdict |
|---|---|---|---|---|---|---|
| HI-Small | 0.4214 | 0.3509 | 0.4776 | 0.4454 | -- | PASS |
| LI-Medium | 0.1242 | 0.1418 | 0.1793 | 0.1703 | 0.979838 | PASS |

- False-positive-reduction savings (ASSUMPTION, LI-Medium): $4,792,239 ($4.79M) -- 73,727 investigator hours, 294,907 fewer false-positive alerts (vs. a fixed-dollar-threshold naive baseline on the full 31,251,483-row population).
- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION, LI-Medium): $15,950,000 ($15.95M) -- +319 additional real cases caught vs. the naive baseline.
- Dominant real SHAP driver (LI-Medium): Payment Format.

## BP2 -- Typology & Red-Flag Pattern Detection
Champion: RandomForest | Random seed 42 | Feature count: 13 | Metric: macro-F1 (multi-class argmax) | Status: RECOMMENDED FOR PRODUCTION (both gates PASS, LI-Medium)

| Variant | Test Macro-F1 | Before Macro-F1 | Overall Accuracy | Verdict |
|---|---|---|---|---|
| LI-Medium | 0.4440 | 0.0812 | 0.4646 | PASS |

5 of 8 platform typologies had real matched ground truth this run (CYCLE, FAN-IN, FAN-OUT, GATHER-SCATTER, RANDOM) --
the other 3 are genuinely absent from this run's population, never fabricated.

| Typology | Before Recall | After Recall | Delta | Test n |
|---|---|---|---|---|
| CYCLE | 0.0000 | 0.3380 | +0.3380 | 71 |
| FAN-IN | 0.0000 | 0.5610 | +0.5610 | 82 |
| FAN-OUT | 1.0000 | 0.6967 | -0.3033 | 122 |
| GATHER-SCATTER | 0.0000 | 0.2667 | +0.2667 | 135 |
| RANDOM | 0.0000 | 0.4571 | +0.4571 | 70 |

- Auto-typing efficiency savings (ASSUMPTION): $1,313 -- 20.2 investigator hours, +101 more of 480 held-out cases correctly auto-typed.
- Illustrative typology-confirmation value (ASSUMPTION): $1,104,000 ($1.10M) -- 138 real cases the old single-guess rule structurally could not identify.
- Dominant real SHAP driver: receiver_distinct_counterparties_to_date.

## BP3 -- Transaction Network & Graph Intelligence (RULE, not a trained model)
Champion structural signal: "2-hop proximity to a TRAIN-flagged account" (`near_train_flagged`, set-membership test, not a threshold) | Random seed 42 | Status: RECOMMENDED FOR PRODUCTION (both gates PASS, LI-Medium)

| Variant | Real Lift Ratio | CI95 Low | CI95 High | Verdict |
|---|---|---|---|---|
| LI-Medium | 3.19x | 3.16x | 3.22x | PASS |

- Base rate: 1.1570%. Bootstrap: 2,000 resamples (closed-form multinomial, Lesson #18/#26), 0 invalid.
- Graph scale: 2,032,095 real distinct (Bank, Account) nodes, 4,363,197 real distinct directed edges (LI-Medium).
- No dollar figure -- no sourced per-account investigation-cost basis exists for this BP; none invented (locked Notebook 1 Section 6 policy).
- HI-Small Stage A screening champion ("In-degree, top decile") DIFFERS from the LI-Medium mandatory-tier champion above -- the LI-Medium result is authoritative per platform policy, the divergence is disclosed, not hidden.
- Explainability: N/A -- no trained model exists, not merely omitted.

## BP4 -- Structuring & Smurfing Detection (31 U.S.C. Section 5324)
Champion: XGBoost | Random seed 42 | Feature count: 24 (BP1's 19 + 5 new structuring features) | Status: RECOMMENDED FOR PRODUCTION (both gates PASS, HI-Small + LI-Medium)

| Variant | Test PR-AUC | Precision | Recall | F2 | Threshold | Verdict |
|---|---|---|---|---|---|---|
| HI-Small | 0.4387 | 0.3254 | 0.5054 | 0.4551 | -- | PASS |
| LI-Medium | 0.1253 | 0.0864 | 0.3055 | 0.2027 | 0.979263 | PASS |

- False-positive-reduction savings (ASSUMPTION, LI-Medium): $4,232,784 ($4.23M) -- 65,120 investigator hours, 260,479 fewer false-positive alerts.
- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION, LI-Medium): $65,000,000 ($65.00M) -- +1,300 additional real cases caught.
- Dominant real SHAP driver among the 5 new structuring features: amount_to_rolling_window_mean_ratio -- real, independent lift over BP1's own 19-column set.

## BP5 -- Correspondent Banking & Cross-Border Wire Risk
Champion: XGBoost | Random seed 42 | Feature count: 27 (BP1's 19 + 8 new cross-border features) | Status: RECOMMENDED FOR PRODUCTION (both gates PASS, HI-Small + LI-Medium)

| Variant | Test PR-AUC | Precision | Recall | F2 | Threshold | Verdict |
|---|---|---|---|---|---|---|
| HI-Small | 0.4306 | 0.3935 | 0.4869 | 0.4648 | -- | PASS |
| LI-Medium | 0.1399 | 0.1763 | 0.1830 | 0.1816 | 0.981432 | PASS |

- False-positive-reduction savings (ASSUMPTION, LI-Medium): $4,852,169 ($4.85M) -- 74,649 investigator hours, 298,595 fewer false-positive alerts -- the platform's single largest false-positive-reduction figure.
- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION, LI-Medium): $17,000,000 ($17.00M) -- +340 additional real cross-border cases caught.
- Dominant real SHAP driver (overall model, LI-Medium): Payment Format; among BP5's own 8 cross-border-specific features, sender_country_empirical_risk ranks top.
- OFAC sanctions-list screening and ECOA/FCRA-style fairness testing are both Not Possible -- Data Limitation on this synthetic dataset (no real sanctions-list/entity-name field, no demographic fields) -- disclosed explicitly, never silently skipped.

## BP6 -- Enterprise AML Compliance Monitoring & Regulatory Reporting (pure rollup, no model of its own)
Status: RECOMMENDED FOR PRODUCTION -- PLATFORM-WIDE. Pure read-only pass-through of BP1-BP5's own already-computed real figures -- nothing is re-validated or recomputed at the rollup level; the only new computation is this BP's own structural/reconciliation gate.

Three-category financial rollup (never blended into one grand total, per Section 7A/Section 8 policy):

| Category | Contributing BPs | Total | Real volume |
|---|---|---|---|
| 1 -- FP-reduction savings (ASSUMPTION) | BP1 + BP4 + BP5 | $13,877,192 ($13.88M) | 213,496 investigator hours, 853,981 fewer FP alerts |
| 2 -- TP-uplift illustrative value (ASSUMPTION) | BP1 + BP4 + BP5 | $97,950,000 ($97.95M) | +1,959 additional real cases caught |
| 3 -- BP2 typology lines (separate unit basis) | BP2 only | $1,313 + $1,104,000 ($1.10M) | 101 more cases auto-typed; 138 cases confirmed the old rule missed |

- BP4 contributes the platform's single largest Category 2 figure ($65,000,000 / $65.00M); BP5 contributes the platform's single largest Category 1 figure ($4,852,169 / $4.85M).
- XGBoost recurs as the real champion on 3 of 5 model-bearing BPs (BP1, BP4, BP5).
- BP3's real network coverage (2,032,095 nodes, 4,363,197 edges) is reported as a portfolio-scale volume line only -- never dollarized, never summed with the three categories above.
- No real sourced platform-wide build/operating-cost figure exists -- Cost Context intentionally carries no dollar figure rather than an invented placeholder.
- Full per-BP business narratives and all 11 SMART recommendations: `reports/bp6_enterprise_compliance_monitoring/PLATFORM_CARD.md`.

## Cross-BP read (real, observed -- not a claim about which BP is "better", different BPs answer different questions)
- BP4's structuring-specific features add real, independent signal on top of BP1's set (dominant SHAP driver is a BP4-only feature), while LI-Medium PR-AUC is close between BP1 (0.1242) and BP4 (0.1253) -- consistent with BP4's own stated framing: it tests whether structuring-shaped features carry additional lift for the SAME `Is Laundering` label BP1 already models, not a replacement for BP1.
- BP3's rule-based signal and BP1/BP4's trained models are not directly comparable on one scale (lift ratio vs. PR-AUC) -- each is reported in its own native metric, per this platform's locked no-blended-metric policy.
- All 5 model-bearing BPs (BP1-BP5) pass both the structural and statistical-robustness gates on their mandatory LI-Medium tier -- no BP has been shipped on a partial or failed validation; BP6's own structural/reconciliation gate also passes as a pure pass-through of those five verdicts.

## Validation methodology and known risks (added 2026-10-12)

Every number above comes from a **random, class-stratified `train_test_split`** of that BP's modeling
population (BP1/BP2/BP4/BP5), or a random split of accounts (BP3) -- not a chronological split, and (for
BP1/BP2/BP4/BP5) not an entity-separated one. `docs/data/LEAKAGE_AUDIT.md` documents this as Findings L-1
(random, not chronological) and L-2 (no entity-level separation) -- **documented methodological risks,
not proof that any number above is wrong.** Read this section alongside that document, not instead of it.

What has changed since the original 2026-10-02/2026-10-03 figures above were generated:
- `docs/data/LEAKAGE_AUDIT.md` now also documents (2026-10-12): no target leakage found in any BP's
  feature set (Finding L-4); a real, read-only duplicate-record check (Finding L-5; HI-Small's rate is
  negligible, <0.0005%; LI-Medium not yet checked on this project's current hardware); and confirmation
  that no scaler/imputer/resampler/feature-selector exists anywhere in this platform's pipeline for any
  BP, so the one real train-only-imputation case (BP2/BP4's RandomForest median-impute) is correctly
  fit on training data only, not the full dataset (Finding L-3).
- A new, unit-tested, reusable module -- `src/aml_riskiq/validation/temporal_entity_validation.py` --
  now exists and is wired into each BP's own `03_statistical_validation_deployment_SINGLE_CELL.py`
  (Finding L-6). On the user's next real run of each notebook, it will additionally produce, saved
  alongside each BP's existing `MODEL_CARD.md`/validation report:
  - **BP1/BP4/BP5**: `reports/<bp>/bp{1,4,5}_notebook3_temporal_entity_validation_<variant>.{json,md}`
    -- the SAME champion architecture re-fit (not re-tuned) on a chronological split and an
    entity-aware split of that run's real rows, with PR-AUC, ROC-AUC, a full confusion matrix at the
    production threshold (precision/recall/F1/FPR/alert volume), calibration (Brier score +
    reliability-curve bins), a threshold trade-off table, majority-class and logistic-regression
    baselines, entity-overlap and duplicate-overlap checks, a dataset content-hash fingerprint, and the
    full run environment (Python/numpy/pandas/scikit-learn versions, git commit).
  - **BP2**: `reports/bp2_typology_redflag_detection/bp2_notebook3_temporal_entity_validation_<variant>.{json,md}`
    -- baseline-only (majority-class + logistic regression, both multiclass-safe) under the same two
    alternative splits, plus entity-overlap; champion re-fit was deliberately scoped out for BP2 (see
    Finding L-6 for why).
  - **BP3**: `reports/bp3_network_graph_intelligence/bp3_notebook3_temporal_validation_<variant>.json` --
    the real 2-hop network-proximity lift-ratio signal re-computed on a chronological-by-first-seen split
    of accounts (BP3's own split already separates by entity, so no separate entity-aware split applies
    -- see Finding L-4).

**None of those four report pairs exist in this repository yet.** Per this project's standing execution
boundary, this update wrote and unit-tested the code (41 passing tests against synthetic fixtures,
`tests/unit/test_temporal_entity_validation.py`); it did not run any BP's real notebook against the real
dataset. **This document's benchmark tables above are not changed by this section** -- they remain
exactly what each BP's own real Notebook 3/4 run produced under the original random split, and will stay
the authoritative figures for that split until the user re-runs a notebook and this document is updated
again with whatever the re-run's own real `MODEL_CARD.md`/validation report says.

Every figure in this entire document, both above and any future chronological/entity-aware figures,
is computed against **IBM's published SYNTHETIC AML transaction dataset** (Kaggle:
`ealtman2019/ibm-transactions-for-anti-money-laundering-aml`; no real account, transaction, or financial
institution is represented) -- evidence about this platform's modeling methodology, never a claim about
real-world AML detection performance, regulatory effectiveness, or production readiness. "RECOMMENDED FOR
PRODUCTION" above describes this platform's own internal two-gate structural/statistical-robustness
check passing on synthetic data, not a certification, regulatory approval, or real-bank effectiveness
claim.

_Generated 2026-10-02; BP5/BP6 sections updated 2026-10-03 after a staleness check against the real
Evidence Ledger found they had been built and validated but never reflected here; "Validation methodology
and known risks" section added 2026-10-12. Every figure in the tables above traces to a real, dated
`MODEL_CARD.md`/`RULE_CARD.md`/`PLATFORM_CARD.md` generated by that BP's own real Notebook 3/4 run -- see
each file for full detail, explainability values, and the complete SMART recommendation set._
