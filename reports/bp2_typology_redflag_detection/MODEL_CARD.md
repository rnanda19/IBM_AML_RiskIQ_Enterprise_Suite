# Model Card -- BP2: Typology & Red-Flag Pattern Detection

_Generated 2026-10-01T08:27:23.163655+00:00 UTC. Primary reported variant: LI-Medium (this BP's locked mandatory realism-validation tier)._

## Status: RECOMMENDED FOR PRODUCTION
Both the structural and statistical-robustness validation gates passed on every real dataset variant evaluated (LI-Medium).

## Business Objective
BP2 (Typology & Red-Flag Pattern Detection) builds the real capability to classify transactions already known to be laundering (`Is Laundering==1`, real dataset label) into the specific real money-laundering typology they exhibit -- directly matching the 'red flags' terminology used in real regulatory enforcement actions (FinCEN assessment, JPMorgan Chase, re: the Madoff/BLM case). Its objective is to give investigators a real, evidence-backed starting typology for each known laundering case, feeding case triage and SAR-narrative drafting, rather than leaving every case to be typed manually from scratch. This report covers the real, completed build and validation of that capability on LI-Medium (this BP's locked mandatory realism-validation tier), across the 5 real typologies with matched ground-truth examples in this run (CYCLE, FAN-IN, FAN-OUT, GATHER-SCATTER, RANDOM).

## What This Means for the Business
- On LI-Medium, the real champion model (RandomForest) achieves a real held-out test macro-F1 of 0.4440 across 5 real typologies, 5.5x the real single-typology-heuristic baseline (macro-F1 0.0812), with both the structural and statistical-robustness validation gates passing (overall verdict: PASS).
- Real overall labeling accuracy improves from 25.4% to 46.5% on the same 480-row real held-out test set -- +101 more of those real cases correctly auto-typed, ASSUMPTION-estimated at 20.2 investigator hours ($1,313 at $65/hour) freed from manual typology triage.
- The old single-guess rule (`always FAN-OUT`) is mathematically guaranteed to identify 0% of every other real typology; the real ML model correctly identifies 138 real held-out cases of those other typologies -- typology-detection capability that structurally did not exist before (illustrative typology-confirmation value, ASSUMPTION: $1,104,000 ($1.10M)), deliberately kept as a separate benefit line from the auto-typing-efficiency savings above, never summed (same discipline as BP1's Section 7A false-positive/true-positive separation).
- Real per-typology recall varies by pattern: highest real absolute recall on 'FAN-OUT' (After recall 0.6967, 122 real held-out cases); lowest on 'GATHER-SCATTER' (After recall 0.2667, 135 real held-out cases) -- an honest, real breakdown investigators can use to calibrate trust per typology, not a single blended number.
- Model behavior is explainable at both the global and case level: real SHAP analysis ranks 'receiver_distinct_counterparties_to_date' as the dominant real driver of the model's typology assignment on LI-Medium, and real LIME explanations are saved per predicted case -- giving investigators and examiners a real, case-level rationale for every typology assignment, not a black-box label.
- A real, self-tested FastAPI scoring service already exists for this model (Notebook 3's deployable-service self-test matched direct batch predictions bit-for-bit on 480 real rows checked), so this capability is deployment-ready, not just a research result.

## Financial Impact Summary
- Auto-typing efficiency savings (ASSUMPTION): $1,313 (20.2 investigator hours, +101 more cases correctly auto-typed)
- Illustrative typology-confirmation value (ASSUMPTION): $1,104,000 ($1.10M) (138 real cases the old single-guess rule structurally could not identify)
- These figures apply different ASSUMPTIONS to different real case subsets and are never summed (locked Section 7A discipline).

## Model Details
- Champion algorithm: **RandomForest**
- Random seed: 42
- Feature count: 13
- Primary metric: macro-F1 (no single decision threshold -- multi-class argmax)
- Real typologies with matched ground truth this run: CYCLE, FAN-IN, FAN-OUT, GATHER-SCATTER, RANDOM (5 of the 8 typologies this platform models)

## Intended Use
Real-time / batch typology classification of transactions already flagged as known laundering (`Is Laundering==1`), feeding investigator case triage and SAR-narrative drafting. Not a standalone SAR-filing decision -- output is evidence for a human investigator, per this platform's locked scope.

## Training Data
IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants used (never merged): LI-Medium.

## Evaluation
| Variant | Champion | Test Macro-F1 | Before Macro-F1 | Overall Accuracy | Verdict |
|---|---|---|---|---|---|
| LI-Medium | RandomForest | 0.4440 | 0.0812 | 0.4646 | PASS |

## Real Per-Typology Recall, Before -> After (LI-Medium)
| Typology | Before Recall | After Recall | Delta Recall | Real Test Support (n) |
|---|---|---|---|---|
| CYCLE | 0.0000 | 0.3380 | +0.3380 | 71 |
| FAN-IN | 0.0000 | 0.5610 | +0.5610 | 82 |
| FAN-OUT | 1.0000 | 0.6967 | -0.3033 | 122 |
| GATHER-SCATTER | 0.0000 | 0.2667 | +0.2667 | 135 |
| RANDOM | 0.0000 | 0.4571 | +0.4571 | 70 |

## Explainability
SHAP (TreeExplainer, global, averaged across all real typologies) and LIME (local, per real predicted-typology instance) -- see this variant's own saved `bp2_notebook3_validation_report_*.json` for full real values.

## Ethical Considerations / Fairness
Not Possible - Data Limitation: the IBM AML transaction dataset carries no demographic fields (no race, gender, age, or other protected-attribute data), so an ECOA/FCRA-style disparate-impact test cannot be computed against it. This is flagged explicitly here rather than silently skipped, per this platform's locked compliance-documentation policy.

## Caveats & Limitations
- Only 5 of this platform's 8 modeled typologies had real, matched ground-truth examples in this LI-Medium run (CYCLE, FAN-IN, FAN-OUT, GATHER-SCATTER, RANDOM) -- the remaining typologies are real, genuinely absent from this run's matched population, never fabricated or estimated; if a future real run with a larger or different variant surfaces them, this report should be regenerated against that run's own real saved JSON.
- Both real Before and After figures are measured on the SAME real held-out test set (480 rows) -- no extrapolation to a larger population was needed or performed for this BP's financial-impact framing (unlike BP1, whose naive baseline was evaluated on the full population and its ML rates extrapolated to match).
- Every dollar figure labeled ASSUMPTION in this package is illustrative and configurable (see the Excel workbook's Assumptions sheet) -- none is a specific real fine, penalty, or contractual figure. The two $ Impact lines in the Before/After table apply DIFFERENT disclosed assumptions to two real, non-overlapping subsets of held-out cases (see each row's own definition in the table) and are never summed.
- LI-Medium is this BP's locked mandatory realism-validation tier and is the primary real-world expectation reported here; the HI-Small appendix (if present) is a faster-iteration Stage A screening pass only, not a second fully-validated variant.
- Fairness/disparate-impact testing is not computable on this dataset -- see the Fairness section below.

## Regulatory Mapping
- Bank Secrecy Act (31 U.S.C. Section 5311) -- Platform-wide
- FinCEN 'red flags' typology guidance (JPMorgan Chase assessment, Madoff/BLM case) -- BP2 (this BP's own real-world terminology match)
- FinCEN SAR filing requirements (31 CFR Section 1020.320) -- BP1, BP2 (evidence feed for SAR narrative typology, not itself a SAR-filing decision)
- FFIEC BSA/AML Examination Manual (5 pillars) -- Platform-wide
- SR 11-7 Model Risk Management -- Every model-bearing BP

## Recommendations
### Prioritize real-world review of the lowest-recall typology first
- **Specific:** On LI-Medium, the real champion model (RandomForest) has its LOWEST real absolute recall on 'GATHER-SCATTER' (After recall 0.2667 on 135 real held-out cases) -- it still misses most real cases of this typology.
- **Measurable:** Track real recall on 'GATHER-SCATTER' specifically at every retrain; treat any further drop from 0.2667 as a trigger for feature review.
- **Achievable:** Uses the same SHAP/LIME explainability already computed by Notebook 3 -- no new tooling required.
- **Relevant:** A typology classifier that silently under-performs on one real pattern is a real investigative blind spot (SR 11-7 model risk management expectation).
- **Time-bound:** Reviewed alongside the next scheduled model retrain, within 90 days of production go-live.

### Reallocate freed investigator capacity from real auto-typing efficiency gains
- **Specific:** Moving from the naive always-guess-'FAN-OUT' rule to the real ML model correctly auto-types +101 more of the 480 real held-out cases on LI-Medium (ASSUMPTION-estimated at 20.2 investigator hours, $1,313).
- **Measurable:** Real manual-typology-review hours logged per investigator, compared against the 20.2-hour ASSUMPTION estimate above.
- **Achievable:** Capacity freed is redeployed to case investigation depth, not headcount reduction -- an operational scheduling change, not a new system.
- **Relevant:** Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar).
- **Time-bound:** Reassess real review hours logged 60 days after production go-live against this ASSUMPTION estimate.

### Validate the real net-new typology detections against filed SARs
- **Specific:** The real ML model correctly identifies 138 real held-out cases whose true typology is something other than the old rule's fixed guess ('FAN-OUT') on LI-Medium -- typology detection that structurally could not exist under the old rule (illustrative typology-confirmation value, ASSUMPTION: $1,104,000 ($1.10M)).
- **Measurable:** Real SAR filing rate on model-assigned typologies for these net-new-detected cases, tracked separately from the auto-typing-efficiency line above.
- **Achievable:** Requires only tagging each filed SAR with the model-assigned typology at filing time -- a labeling change, not a new detection system.
- **Relevant:** Directly evidences the model's real typology-detection benefit to examiners (31 CFR Section 1020.320 SAR requirements).
- **Time-bound:** First real comparison report at the 6-month production mark (enough real SAR volume to be meaningful).

### Document why 'FAN-OUT' recall is strongest, as a template for the weaker typologies
- **Specific:** 'FAN-OUT' has the real HIGHEST absolute recall on LI-Medium (After recall 0.6967, real Delta -0.3033 vs. the baseline). Real SHAP analysis ranks 'receiver_distinct_counterparties_to_date' as the model's dominant overall driver.
- **Measurable:** Confirm the same driver(s) remain dominant for this typology at every future real retrain.
- **Achievable:** Already computed by Notebook 3's existing SHAP step -- no new tooling required.
- **Relevant:** SR 11-7 model risk management requires a documented explanation of the model's real primary drivers, per typology where they differ.
- **Time-bound:** Refresh this documentation at every model retrain, alongside the MODEL_CARD.md update.

### Maintain the real two-gate validation standard on every future retrain
- **Specific:** Every real dataset variant evaluated for BP2 currently passes both validation gates (LI-Medium).
- **Measurable:** Both gates must continue to PASS on every future retrain before redeployment.
- **Achievable:** Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.
- **Relevant:** This is the basis for this report's current production-recommended status.
- **Time-bound:** Every retrain cycle, before redeployment.

