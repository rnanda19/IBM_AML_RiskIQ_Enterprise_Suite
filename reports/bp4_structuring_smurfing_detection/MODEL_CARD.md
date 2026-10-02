# Model Card -- BP4: Structuring & Smurfing Detection

_Generated 2026-10-01T18:07:52.798787+00:00 UTC. Primary reported variant: LI-Medium (this BP's locked mandatory realism-validation tier)._

## Status: RECOMMENDED FOR PRODUCTION
Both the structural and statistical-robustness validation gates passed on every real dataset variant evaluated (HI-Small, LI-Medium).

## Business Objective
BP4 (Structuring & Smurfing Detection) targets a federal crime with its own named statute: 31 U.S.C. Section 5324 makes it illegal to break transactions into smaller pieces specifically to evade the Bank Secrecy Act's reporting requirements, and detecting this pattern is a mandatory examination area at every BSA-regulated institution (FFIEC BSA/AML Examination Manual). This BP engineers 5 real, rule-derived features that capture sub-threshold amount clustering, time-clustering, and fan-out splitting behavior -- structuring_window_txn_count, structuring_window_amount_sum, daily_fanout_count, amount_to_rolling_window_mean_ratio, near_threshold_flag -- and combines them with BP1's existing 19-feature transaction-monitoring set to test whether structuring/smurfing-specific behavior carries real, additional predictive lift for the same `Is Laundering` ground-truth label BP1 uses. This report covers the real, completed build and validation of that capability, evaluated on 2 independently-simulated real dataset variants (HI-Small, LI-Medium), never merged.

## What This Means for the Business
- On LI-Medium (this BP's locked mandatory realism-validation tier), the real champion model (XGBoost) detects suspicious transactions at 244.1x the rate a random/no-skill classifier would, with both the structural and statistical-robustness validation gates passing (overall verdict: PASS).
- Applying the real, measured test-set precision and recall to this variant's full real transaction population (31,251,483 real transactions): the naive fixed-dollar-threshold rule this bank would otherwise rely on flags 312,512 transactions for review with only 0.1% of those actually being laundering; the real ML model's operating point flags 56,736 with 8.6% precision -- a real reduction of 260,479 false-positive alerts, ASSUMPTION-estimated at 65,120 investigator hours ($4,232,784 ($4.23M) at $65/hour) freed for real cases.
- On true-positive detection: the naive rule would have caught an estimated 197 of the real laundering cases in this population; the real ML model catches an estimated 1,497 (+1,300 cases) -- an illustrative regulatory-exposure-avoidance ASSUMPTION of $65,000,000 ($65.00M) (+1,300 cases @ $50,000/case), deliberately never summed with the false-positive-reduction savings above (two separate benefit lines, per this platform's locked reporting policy).
- The structuring/smurfing-specific features this BP adds carry real, independent signal: real SHAP analysis ranks amount_to_rolling_window_mean_ratio as the top structuring feature's global importance on LI-Medium -- this is a feature BP1's own 19-column set does not have, giving this capability detection power BP1 alone does not carry.
- A real, self-tested FastAPI scoring service already exists for this model (Notebook 3's deployable-service self-test matched direct batch predictions bit-for-bit on every real row checked, including the disclosed null/NaN-handling path for this BP's one feature with real, expected missing values), so this capability is deployment-ready, not just a research result.

## Financial Impact Summary
- False-positive-reduction savings (ASSUMPTION): $4,232,784 ($4.23M) (65,120 investigator hours, 260,479 fewer false-positive alerts)
- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION): $65,000,000 ($65.00M) (+1,300 additional real cases caught)
- These two figures are never summed into one blended total (locked Section 7A policy).

## Model Details
- Champion algorithm: **XGBoost**
- Random seed: 42
- Feature count: 24
- Selected decision threshold: 0.979263

## Intended Use
Real-time / batch transaction-level suspicious-activity scoring, feeding investigator alert review. Not a standalone SAR-filing decision -- output is evidence for a human investigator, per this platform's locked scope.

## Training Data
IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants used (never merged): HI-Small, LI-Medium.

## Evaluation
| Variant | Champion | Test PR-AUC | Precision | Recall | F2 | Verdict |
|---|---|---|---|---|---|---|
| HI-Small | XGBoost | 0.4387 | 0.3254 | 0.5054 | 0.4551 | PASS |
| LI-Medium | XGBoost | 0.1253 | 0.0864 | 0.3055 | 0.2027 | PASS |

## Explainability
SHAP (TreeExplainer, global) and LIME (local, per real true-positive instance) -- see each variant's own saved `bp4_notebook3_validation_report_*.json` for full real values.

## Ethical Considerations / Fairness
Not Possible - Data Limitation: the IBM AML transaction dataset carries no demographic fields (no race, gender, age, or other protected-attribute data), so an ECOA/FCRA-style disparate-impact test cannot be computed against it. This is flagged explicitly here rather than silently skipped, per this platform's locked compliance-documentation policy.

## Caveats & Limitations
- The naive baseline is evaluated on the FULL real dataset (matching how a bank would actually run a fixed-dollar rule in production); the ML model's precision/recall are real, measured on its held-out 25% test split, then extrapolated to the full population using those same real rates -- an explicit, disclosed assumption, justified by Notebook 3's real stratified train/test split.
- Every dollar figure labeled ASSUMPTION in this package is illustrative and configurable (see the Excel workbook's Assumptions sheet) -- none is a specific real fine, penalty, or contractual figure.
- LI-Medium is this BP's locked mandatory realism-validation tier and should be treated as the primary real-world expectation; HI-Small is reported alongside it for continuity but is a deliberately easier, faster-iteration variant.
- This BP's target is the same `Is Laundering` label BP1 uses, not a dataset label named literally 'structuring' (this dataset's typology list has no such label) -- the real question this BP answers is whether structuring-shaped FEATURES carry real additional predictive lift for that shared label, not whether it re-derives BP2's own typology classification.
- Fairness/disparate-impact testing is not computable on this dataset -- see the Fairness section below.

## Regulatory Mapping
- Bank Secrecy Act (31 U.S.C. Section 5311) -- Platform-wide
- BSA structuring statute (31 U.S.C. Section 5324) -- BP4 -- this BP's own named statute
- FinCEN SAR filing requirements (31 CFR Section 1020.320) -- BP1, BP2, BP4 (evidence feed, not itself a SAR-prediction model)
- FFIEC BSA/AML Examination Manual (5 pillars) -- Platform-wide
- SR 11-7 Model Risk Management -- Every model-bearing BP

## Recommendations
### Recalibrate the alert threshold on a fixed cadence
- **Specific:** The champion model (XGBoost) currently operates at a real decision threshold of 0.9793 on LI-Medium, yielding real precision 0.086 and recall 0.305.
- **Measurable:** Track real precision/recall drift against these two baseline figures on every scoring batch; treat a real precision or recall move of more than 5 percentage points from these values as a trigger for threshold review.
- **Achievable:** Uses the FastAPI scoring service's existing self-tested prediction path -- no new infrastructure required.
- **Relevant:** Directly controls the real false-positive alert volume investigators must review (SR 11-7 model risk management expectation).
- **Time-bound:** Quarterly recalibration review, next due within 90 days of production go-live.

### Reallocate freed investigator capacity from the real false-positive reduction
- **Specific:** Moving from the naive fixed-dollar rule to the real ML model reduces false-positive alerts by 260,479 on LI-Medium (ASSUMPTION-estimated at 65,120 investigator hours, $4,232,784 ($4.23M)).
- **Measurable:** Real alert-review hours logged per investigator, compared against the 65,120-hour ASSUMPTION estimate above.
- **Achievable:** Capacity freed is redeployed to case investigation depth, not headcount reduction -- an operational scheduling change, not a new system.
- **Relevant:** Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar).
- **Time-bound:** Reassess real alert-review hours logged 60 days after production go-live against this ASSUMPTION estimate.

### Validate the real true-positive uplift against filed SARs
- **Specific:** The real ML model's operating point is estimated to catch +1,300 more real laundering cases than the naive rule on LI-Medium (illustrative regulatory-exposure-avoidance ASSUMPTION: $65,000,000 ($65.00M)).
- **Measurable:** Real SAR filing rate on model-flagged alerts vs. naive-rule-flagged alerts, tracked separately, never blended with the false-positive savings above.
- **Achievable:** Requires only tagging each filed SAR with which rule (naive vs. ML) originally surfaced the alert -- a labeling change, not a new detection system.
- **Relevant:** Directly evidences the model's real detection benefit to examiners (31 CFR Section 1020.320 SAR requirements).
- **Time-bound:** First real comparison report at the 6-month production mark (enough real SAR volume to be meaningful).

### Document the dominant real model driver for examiner review
- **Specific:** Real SHAP analysis ranks 'Payment Format' as the model's dominant real driver on LI-Medium.
- **Measurable:** Confirm this ranking is stable across each future real retrain (top-1 feature unchanged, or the change is explicitly documented).
- **Achievable:** Already computed by Notebook 3's existing SHAP step -- no new tooling required.
- **Relevant:** SR 11-7 model risk management requires a documented explanation of the model's real primary drivers.
- **Time-bound:** Refresh this documentation at every model retrain, alongside the MODEL_CARD.md update.

### Maintain the real two-gate validation standard on every future retrain
- **Specific:** Every real dataset variant evaluated for BP4 currently passes both validation gates (HI-Small, LI-Medium).
- **Measurable:** Both gates must continue to PASS on every future retrain before redeployment.
- **Achievable:** Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.
- **Relevant:** This is the basis for this report's current production-recommended status.
- **Time-bound:** Every retrain cycle, before redeployment.

