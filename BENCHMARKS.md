# BENCHMARKS -- IBM AML RiskIQ Enterprise Suite

Consolidated real baseline-vs-model comparisons across every BP that has completed real validation.
Every figure below is copied verbatim from that BP's own `reports/<bp>/MODEL_CARD.md` or `RULE_CARD.md`
(grep-verified against the source file at the time this document was written, 2026-10-02) -- nothing here
is estimated or recomputed independently of that BP's own real Notebook 3 run. Primary reported variant for
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
Notebooks 1-3 built and delivered (2026-10-02); not yet run by the user. NOT YET COMPUTED -- requires a real run on real data before any number can appear here (locked Section 7B policy: no synthetic placeholder output, ever).

## BP6 -- Enterprise AML Compliance Monitoring & Regulatory Reporting
Pure rollup of BP1-BP5's own already-computed summary JSON -- not yet built (waits on real BP5 results per the platform's own build-order rule, Section 3 Phase 4).

## Cross-BP read (real, observed -- not a claim about which BP is "better", different BPs answer different questions)
- BP4's structuring-specific features add real, independent signal on top of BP1's set (dominant SHAP driver is a BP4-only feature), while LI-Medium PR-AUC is close between BP1 (0.1242) and BP4 (0.1253) -- consistent with BP4's own stated framing: it tests whether structuring-shaped features carry additional lift for the SAME `Is Laundering` label BP1 already models, not a replacement for BP1.
- BP3's rule-based signal and BP1/BP4's trained models are not directly comparable on one scale (lift ratio vs. PR-AUC) -- each is reported in its own native metric, per this platform's locked no-blended-metric policy.
- All 4 completed BPs pass both the structural and statistical-robustness gates on their mandatory LI-Medium tier -- no BP has been shipped on a partial or failed validation.

_Generated 2026-10-02. Every figure above traces to a real, dated `MODEL_CARD.md`/`RULE_CARD.md` generated by that BP's own real Notebook 4 run -- see each file for full detail, explainability values, and the complete SMART recommendation set._
