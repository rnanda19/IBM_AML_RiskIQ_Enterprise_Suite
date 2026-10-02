# Rule Card -- BP3: Transaction Network & Graph Intelligence

_Generated 2026-10-01T09:19:30.566344+00:00 UTC. Primary reported variant: LI-Medium (this BP's locked mandatory realism-validation tier)._

**This is a RULE CARD, not a model card.** BP3 has no trained ML model -- the real deployable artifact is a directly-interpretable structural RULE (a threshold or a set-membership test over a real graph-structural signal), never a pickled classifier. SHAP/LIME explainability sections that appear in this platform's other BPs' model cards are genuinely not applicable here, not merely omitted.

## Status: RECOMMENDED FOR PRODUCTION
Both the structural and statistical-robustness validation gates passed on every real dataset variant evaluated (LI-Medium).

## Business Objective
BP3 (Transaction Network & Graph Intelligence) builds the real capability to flag accounts using directly-interpretable graph-structural signals -- real degree, real PageRank, and real network proximity to already-flagged accounts -- computed from the real account-to-account transaction structure, no ground-truth label required to construct them. Its objective is to give investigators a real, evidence-backed structural starting point for which accounts' surrounding networks deserve review next, and to surface a real bounded 2-hop ego-network around each flagged account rather than leaving every case to single-account review. This report covers the real, completed build and validation of that capability on LI-Medium (this BP's locked mandatory realism-validation tier) -- 2,032,095 real distinct (Bank, Account) nodes, 4,363,197 real distinct directed edges.

## What This Means for the Business
- On LI-Medium, the real champion structural signal ('2-hop proximity to a TRAIN-flagged account') achieves a real held-out test network-lift ratio of 3.19x over the real base rate of 1.1570% (real bootstrap 95% CI [3.16x, 3.22x], 2,000 resamples, 0 invalid), with both the structural and statistical-robustness validation gates passing (overall verdict: PASS).
- Real bounded 2-hop ego-network review surfaces materially more real account context per flagged case than single-account review: NB3's 3 real illustrative examples show real network sizes of 181,831, 15,360, 15,174 accounts before the locked 2,000-node cap is applied -- a real volume-scale KPI, never dollarized (no sourced per-account investigation-cost basis exists for this BP, and none is invented).
- BP3 has no trained ML model -- every candidate (real degree, real PageRank, real network proximity) is a directly-interpretable structural signal, ranked purely by real network-lift ratio on a real held-out test set of accounts, never a black-box score.
- The real champion signal differs between real dataset scales (HI-Small Stage A screening selected 'In-degree (top decile)', LI-Medium mandatory validation selects '2-hop proximity to a TRAIN-flagged account') -- per this platform's locked policy, the real LI-Medium result is authoritative and is never silently overridden by the smaller-scale prior.
- A real, self-tested FastAPI scoring service already exists for this champion RULE (Notebook 3's deployable-service self-test matched direct batch computation bit-for-bit on 2,000 real rows checked, 0 mismatches), so this capability is deployment-ready, not just a research result.

## Rule Details
- Champion structural signal: **2-hop proximity to a TRAIN-flagged account**
- Rule artifact column: `near_train_flagged`
- Is threshold signal: False
- Threshold: N/A (set-membership test)
- Random seed: 42
- Real network-lift ratio (point estimate): 3.1882x
- Real bootstrap 95% CI: [3.1567x, 3.2187x] (2,000 resamples, 0 invalid)

## Intended Use
Network-proximity / structural-prominence flagging to prioritize which already-flagged accounts' surrounding networks an investigator reviews next, and to surface a real bounded 2-hop ego-network for that review. Not a standalone SAR-filing decision, not a probability score -- output is a real structural flag feeding investigator triage, per this platform's locked scope.

## Training / Screening Data
IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants used (never merged): LI-Medium.

## Evaluation
| Variant | Champion Signal | Real Lift Ratio | CI95 Low | CI95 High | Gate 1 | Gate 2 | Overall Verdict |
|---|---|---|---|---|---|---|---|
| LI-Medium | 2-hop proximity to a TRAIN-flagged account | 3.19x | 3.16x | 3.22x | PASS | PASS | PASS |

## Explainability -- Not Applicable
BP3 has no trained ML model -- every candidate is a directly-interpretable structural signal; SHAP/LIME are N/A, not attempted.

## Scaling / Engineering Notes
networkx avoided for the full graph (Lesson #21/#26) -- hand-rolled vectorized sparse PageRank (self-tested above) and a memory-efficient frontier-expansion BFS used instead; networkx used only for the small capped illustrative ego-networks (Section 8).

## Deployable Scoring Service -- Real Self-Test
- Rows checked: 2,000
- Mismatches: 0

## Ethical Considerations / Fairness
Not Possible - Data Limitation: the IBM AML transaction dataset carries no demographic fields (no race, gender, age, or other protected-attribute data), so an ECOA/FCRA-style disparate-impact test cannot be computed against it. This is flagged explicitly here rather than silently skipped, per this platform's locked compliance-documentation policy.

## Caveats & Limitations
- BP3 has no trained ML model and no SHAP/LIME explainability section -- genuinely not applicable to a directly-interpretable structural rule, not merely omitted or unavailable (BP3 has no trained ML model -- every candidate is a directly-interpretable structural signal; SHAP/LIME are N/A, not attempted.)
- No dollar figure appears anywhere in this report. This platform's locked policy (Notebook 1 Section 6) requires a real, sourced per-account investigation-cost assumption before dollarizing the Before/After volume-scale KPI, and no such sourced figure exists for this BP -- none is invented here, unlike BP1/BP2's illustrative ASSUMPTION-labeled dollar figures.
- The real before/after ego-network comparison uses only the 3 real illustrative examples Notebook 3 computed full statistics for -- NOT a population-wide average across every real flagged account (that aggregate was not computed and is not estimated here).
- LI-Medium is this BP's locked mandatory realism-validation tier and is the primary real-world expectation reported here; the HI-Small appendix (if present) is a faster-iteration Stage A screening pass only, not a second fully-validated variant.
- Fairness/disparate-impact testing is not computable on this dataset -- see the Fairness section below.
- Full-graph community detection (Louvain) and betweenness centrality are explicitly excluded from this BP's methodology at full-graph scale -- a real pre-build diagnostic (Lesson #21) confirmed Louvain did not finish in 120 real seconds even on HI-Small, the smallest variant. Both remain available only within the locked bounded 2-hop ego-network scope (2,000-node cap).

## Regulatory Mapping
- Bank Secrecy Act (31 U.S.C. Section 5311) -- Platform-wide
- FFIEC BSA/AML Examination Manual (5 pillars -- link analysis / relationship mapping is a recognized investigative technique) -- BP3 (real-world terminology match not independently confirmed against a primary enforcement document, disclosed honestly per Notebook 1 Section 3)
- FinCEN SAR filing requirements (31 CFR Section 1020.320) -- BP3 (evidence feed for SAR narrative network context, not itself a SAR-filing decision)
- SR 11-7 Model Risk Management -- Every model/rule-bearing BP -- applied here to a RULE artifact, not a trained model

## Recommendations
### Re-validate the champion structural signal on a fixed cadence
- **Specific:** The champion signal on LI-Medium (2-hop proximity to a TRAIN-flagged account) achieves a real network-lift ratio of 3.19x (real bootstrap 95% CI [3.16x, 3.22x], 2,000 resamples, 0 invalid).
- **Measurable:** Track the real lift ratio and its bootstrap CI on every future real re-run; treat a CI95 lower bound that drops to or below 1.0x (no real lift over the real base rate) as a trigger for re-screening the full candidate signal set.
- **Achievable:** Uses the existing, already-built Notebook 2 (Stage A screening) and Notebook 3 (validation + bootstrap) pipeline -- no new infrastructure required.
- **Relevant:** Directly controls whether the real network-proximity flagging rule remains evidence-based (Lesson #11 leakage discipline, enforced every run as its own structural gate).
- **Time-bound:** Quarterly re-validation review, next due within 90 days of production go-live.

### Scale investigator review capacity to the real bounded ego-network volume, not account count
- **Specific:** Before = single-account review (zero real network visibility). After = the real bounded 2-hop ego-network around the same flagged account -- NB3's 3 real illustrative examples show real network sizes 181,831, 15,360, 15,174 accounts before the locked 2,000-node cap is applied.
- **Measurable:** Real per-case investigator review time logged under the new bounded-ego-network workflow vs. the prior single-account workflow -- no ASSUMPTION dollar figure is used here, per this BP's locked no-invented-cost-basis policy.
- **Achievable:** Capacity planning is an operational scheduling change against the existing locked 2,000-node bounded scope -- no new detection system required.
- **Relevant:** Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar) -- network-scale review has a materially different real workload shape than single-account review.
- **Time-bound:** Reassess real review-time-per-case 60 days after production go-live.

### Investigate the real champion divergence between HI-Small and LI-Medium
- **Specific:** The real Stage A (HI-Small) screening champion ('In-degree (top decile)') and the real LI-Medium mandatory-validation-tier champion ('2-hop proximity to a TRAIN-flagged account') are DIFFERENT signals. Per this platform's locked rule, the real LI-Medium result is authoritative and is never silently overridden by the smaller-scale prior -- but the divergence itself is worth understanding.
- **Measurable:** Compare the real per-signal lift ratios at both scales (see the Signal Comparison table in this report) to characterize how each candidate's real lift changes with real graph scale.
- **Achievable:** Uses the already-saved Notebook 2 and Notebook 3 outputs -- a comparison, not a new computation.
- **Relevant:** Understanding why a structural signal's real relative strength changes with scale directly informs which signal to trust at full production (HI-Large/LI-Large) scale.
- **Time-bound:** Before this champion is cited as stable in any external or regulatory-facing report.

### Keep the 'no trained model' framing explicit in every downstream use of this rule
- **Specific:** BP3 has no trained ML model -- every candidate is a directly-interpretable structural signal; SHAP/LIME are N/A, not attempted. The real deployable artifact is a RULE (near_train_flagged (set-membership test)), never a pickled classifier -- confirmed by the real self-tested FastAPI service (2,000 real rows checked, 0 mismatches).
- **Measurable:** Any downstream system or document referencing this BP's output states 'structural rule' or 'network-lift signal', never 'model prediction' or 'model score'.
- **Achievable:** A documentation/labeling convention, not a code or infrastructure change.
- **Relevant:** SR 11-7 model risk management requires accurate characterization of what kind of artifact is actually in production -- a RULE carries different real validation and monitoring expectations than a trained classifier.
- **Time-bound:** Immediate -- applies to this report and every future one referencing this BP.

### Maintain the real two-gate validation standard on every future retrain
- **Specific:** Every real dataset variant evaluated for BP3 currently passes both validation gates (LI-Medium).
- **Measurable:** Both gates must continue to PASS on every future retrain before redeployment.
- **Achievable:** Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.
- **Relevant:** This is the basis for this report's current production-recommended status.
- **Time-bound:** Every retrain cycle, before redeployment.

