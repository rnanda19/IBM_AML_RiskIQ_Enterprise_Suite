# Model Card -- BP1: Transaction Monitoring & Suspicious Activity Detection

_Generated 2026-10-01T06:45:42.976904+00:00 UTC. Primary reported variant: LI-Medium (this BP's locked mandatory realism-validation tier)._

## Status: RECOMMENDED FOR PRODUCTION
Both the structural and statistical-robustness validation gates passed on every real dataset variant evaluated (HI-Small, LI-Medium).

## Business Objective
BP1 (Transaction Monitoring & Suspicious Activity Detection) builds the core transaction-monitoring capability every Bank Secrecy Act (31 U.S.C. Section 5311) regulated institution must operate under the FFIEC BSA/AML Examination Manual's five pillars. Its objective is to score individual transactions for real likelihood of money laundering, feeding investigator alert review and any downstream Suspicious Activity Report decision (31 CFR Section 1020.320), while controlling the false-positive alert volume that consumes most AML investigation teams' real capacity. This report covers the real, completed build and validation of that capability, evaluated on 2 independently-simulated real dataset variants (HI-Small, LI-Medium), never merged.

## What This Means for the Business
- On LI-Medium (this BP's locked mandatory realism-validation tier -- the harder, more realistic case), the real champion model (XGBoost) detects suspicious transactions at 242x the rate a random/no-skill classifier would, with both the structural and statistical-robustness validation gates passing (overall verdict: PASS).
- Applying the real, measured test-set precision and recall to this variant's full real transaction population (31,251,483 real transactions): the naive fixed-dollar-threshold rule this bank would otherwise rely on flags 312,512 transactions for review with only 0.1% of those actually being laundering; the real ML model's operating point flags 20,284 with 14.2% precision -- a real reduction of 294,907 false-positive alerts, ASSUMPTION-estimated at 73,727 investigator hours ($4,792,239 ($4.79M) at $65/hour) freed for real cases.
- On true-positive detection: the naive rule would have caught an estimated 197 of the real laundering cases in this population; the real ML model catches an estimated 516 (+319 cases) -- an illustrative regulatory-exposure-avoidance ASSUMPTION of $15,950,000 ($15.95M) (+319 cases @ $50,000/case), deliberately never summed with the false-positive-reduction savings above (two separate benefit lines, per this platform's locked reporting policy).
- Model behavior is explainable at both the global and case level: real SHAP analysis ranks Payment Format as the dominant real driver of the model's score on LI-Medium, consistent with every other real-run variant this platform has validated -- giving investigators and examiners a real, case-level rationale for every alert, not a black-box score.
- A real, self-tested FastAPI scoring service already exists for this model (Notebook 3's deployable-service self-test matched direct batch predictions bit-for-bit on every real row checked), so this capability is deployment-ready, not just a research result.

## Financial Impact Summary
- False-positive-reduction savings (ASSUMPTION): $4,792,239 ($4.79M) (73,727 investigator hours, 294,907 fewer false-positive alerts)
- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION): $15,950,000 ($15.95M) (+319 additional real cases caught)
- These two figures are never summed into one blended total (locked Section 7A policy).

## Model Details
- Champion algorithm: **XGBoost**
- Random seed: 42
- Feature count: 19
- Selected decision threshold: 0.979838

## Intended Use
Real-time / batch transaction-level suspicious-activity scoring, feeding investigator alert review. Not a standalone SAR-filing decision -- output is evidence for a human investigator, per this platform's locked scope.

## Training Data
IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants used (never merged): HI-Small, LI-Medium.

## Evaluation
| Variant | Champion | Test PR-AUC | Precision | Recall | F2 | Verdict |
|---|---|---|---|---|---|---|
| HI-Small | XGBoost | 0.4214 | 0.3509 | 0.4776 | 0.4454 | PASS |
| LI-Medium | XGBoost | 0.1242 | 0.1418 | 0.1793 | 0.1703 | PASS |

## Explainability
SHAP (TreeExplainer, global) and LIME (local, per real true-positive instance) -- see each variant's own saved `bp1_notebook3_validation_report_*.json` for full real values.

## Ethical Considerations / Fairness
Not Possible - Data Limitation: the IBM AML transaction dataset carries no demographic fields (no race, gender, age, or other protected-attribute data), so an ECOA/FCRA-style disparate-impact test cannot be computed against it. This is flagged explicitly here rather than silently skipped, per this platform's locked compliance-documentation policy.

## Caveats & Limitations
- The naive baseline is evaluated on the FULL real dataset (matching how a bank would actually run a fixed-dollar rule in production); the ML model's precision/recall are real, measured on its held-out 25% test split, then extrapolated to the full population using those same real rates -- an explicit, disclosed assumption (never presented as itself a directly-measured full-population number), justified by Notebook 3's real stratified train/test split.
- Every dollar figure labeled ASSUMPTION in this package is illustrative and configurable (see the Excel workbook's Assumptions sheet) -- none is a specific real fine, penalty, or contractual figure.
- LI-Medium is this BP's locked mandatory realism-validation tier and should be treated as the primary real-world expectation; HI-Small is reported alongside it for continuity but is a deliberately easier, faster-iteration variant.
- Fairness/disparate-impact testing is not computable on this dataset -- see the Fairness section below.

## Regulatory Mapping
- Bank Secrecy Act (31 U.S.C. Section 5311) -- Platform-wide
- USA PATRIOT Act Section 326 (CIP), Section 314(a)/(b) -- BP1, BP5
- FinCEN SAR filing requirements (31 CFR Section 1020.320) -- BP1, BP2 (evidence feed, not itself a SAR-prediction model)
- OFAC sanctions-list screening -- BP1, BP5
- FFIEC BSA/AML Examination Manual (5 pillars) -- Platform-wide
- SR 11-7 Model Risk Management -- Every model-bearing BP

## Recommendations
### Recalibrate the alert threshold on a fixed cadence
- **Specific:** The champion model (XGBoost) currently operates at a real decision threshold of 0.9798 on LI-Medium, yielding real precision 0.142 and recall 0.179.
- **Measurable:** Track real precision/recall drift against these two baseline figures on every scoring batch; treat a real precision or recall move of more than 5 percentage points from these values as a trigger for threshold review.
- **Achievable:** Uses the FastAPI scoring service's existing self-tested prediction path -- no new infrastructure required.
- **Relevant:** Directly controls the real false-positive alert volume investigators must review (SR 11-7 model risk management expectation).
- **Time-bound:** Quarterly recalibration review, next due within 90 days of production go-live.

### Reallocate freed investigator capacity from the real false-positive reduction
- **Specific:** Moving from the naive fixed-dollar rule to the real ML model reduces false-positive alerts by 294,907 on LI-Medium (ASSUMPTION-estimated at 73,727 investigator hours, $4,792,239 ($4.79M)).
- **Measurable:** Real alert-review hours logged per investigator, compared against the 73,727-hour ASSUMPTION estimate above.
- **Achievable:** Capacity freed is redeployed to case investigation depth, not headcount reduction -- an operational scheduling change, not a new system.
- **Relevant:** Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar).
- **Time-bound:** Reassess real alert-review hours logged 60 days after production go-live against this ASSUMPTION estimate.

### Validate the real true-positive uplift against filed SARs
- **Specific:** The real ML model's operating point is estimated to catch +319 more real laundering cases than the naive rule on LI-Medium (illustrative regulatory-exposure-avoidance ASSUMPTION: $15,950,000 ($15.95M)).
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
- **Specific:** Every real dataset variant evaluated for BP1 currently passes both validation gates (HI-Small, LI-Medium).
- **Measurable:** Both gates must continue to PASS on every future retrain before redeployment.
- **Achievable:** Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.
- **Relevant:** This is the basis for this report's current production-recommended status.
- **Time-bound:** Every retrain cycle, before redeployment.

