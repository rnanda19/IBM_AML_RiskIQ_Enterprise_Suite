---
title: IBM AML RiskIQ Enterprise Suite - Master Execution Plan (v2.0)
---

# IBM AML RiskIQ Enterprise Suite — Master Execution Plan v2.0
AI-Driven Anti-Money Laundering & Financial Crime Intelligence Platform
6 Business Problems | 5 Build Phases | 24 BP notebooks + 5 phase rollups + 1 platform rollup = 30 total notebooks
Prepared for Nandagopal — 2026-09-29
Supersedes v1.0 (2026-09-23) on every conflicting point. v1.0's 8-BP scope is retired; see Section 3 for why.

Methodology mirrored from: a prior credit-risk-focused enterprise platform in this same methodology lineage, a prior lending-risk-focused enterprise platform in this same methodology lineage, the prior fraud-risk platform, a prior customer-intelligence-focused enterprise platform in this same methodology lineage — the same four platforms this project's folder scaffold was originally mirrored from.

## 1. Executive Summary

This plan locks in a 6-Business-Problem scope, replacing the original 8-BP draft after a real feasibility review against the actual dataset: each of the 6 BPs here has independent, real ground truth or a fully computable structural signal in the IBM AML dataset — no proxy labels, no unvalidated composites. Four BPs from the original draft were dropped on that review (Account/Entity AML Risk Scoring, Alert Escalation/SAR-Filing Prediction, GenAI SAR Narrative Assistant, Alert Prioritization & Case Decision Engine) because each either lacked an independent ground-truth label in this dataset or wasn't a trainable/validatable problem as scoped. Two BPs were added because the dataset directly supports them and they are real, high-priority named functions at top-tier banks (Structuring/Smurfing Detection, Correspondent Banking & Cross-Border Wire Risk).

Every standing rule from the four prior platforms carries forward unchanged: zero-fabrication, the Claude execution-boundary rule, WARP (runtime resource governance, extended here with thermal protection), HYPER (delivery acceleration), the 6-Gate SOP mapped to CRISP-DM, the two-gate verdict architecture, and the Evidence Ledger. Nineteen concrete, real-bug-derived lessons from the those two prior platforms builds are consolidated in `LESSONS_LEARNED_APPLIED.md` at the project root and referenced throughout this plan rather than repeated in full.

## 2. Confirmed Foundations

**Dataset:** "IBM Transactions for Anti Money Laundering (AML)" — published by IBM at github.com/IBM/AML-Data; the real data files are directly downloadable from Kaggle (kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml), the dataset's real, direct download location, with the same files also mirrored on IBM's own Box storage (ibm.box.com/v/AML-Anti-Money-Laundering-Data, CDLA-Sharing-1.0) — IBM Research / Altman et al., NeurIPS 2023 (arXiv:2306.16424), fully synthetic. 6 size variants: HI-Small/Medium/Large, LI-Small/Medium/Large. Confirmed present and genuine on the user's device at `C:\Users\rnand\Downloads\IBM AML RISKIQ DATASET\`: real headers verified for `*_Trans.csv` (`Timestamp, From Bank, Account, To Bank, Account, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering` — the duplicated "Account" header is real, pandas auto-renames the second to `Account.1`), `*_accounts.csv` (`Bank Name, Bank ID, Account Number, Entity ID, Entity Name`), and `*_Patterns.txt` (real block-structured typology ground truth, e.g. `BEGIN LAUNDERING ATTEMPT - FAN-OUT`). Row counts and illicit-transaction ratios for HI-Small, LI-Small, HI-Medium, and LI-Medium were independently cross-checked against the published paper's own Table 4 statistics — near-exact matches on all four. HI-Large (17,052,760,651 bytes) and LI-Large (16,742,513,790 bytes) were row-counted for real on 2026-09-29: HI-Large_Trans.csv = 179,702,230 lines (179,702,229 real transactions + 1 header); LI-Large_Trans.csv = 176,066,558 lines (176,066,557 real transactions + 1 header). Both are a near-exact match to the paper's expected ~180M/~176M-row scale — this was previously flagged as unconfirmed and is now independently closed out.

**Build target:** HI-Small for all primary development and validation (fast iteration, already the default in BP1's Notebook 1 draft). The pipeline is designed to re-point at HI-Medium/HI-Large by changing one config value (`DATASET_VARIANT` in each BP's `configs/bpN_*.yaml`) once proven correct on HI-Small — never built directly against the largest variant first, per the same staged-scale-up pattern used on those two prior platforms.

**Environment:** `C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\` (Windows, "Documents" connected folder). Folder structure re-locked 2026-09-29 to the 6-BP scope — see `PROJECT_STRUCTURE_LOCKED.md` for the full layout and the rule against renaming again once a notebook has written a path into it. `src/utils/` is scaffolded (folder + README only) but not yet populated with real code — Notebook 00 and BP1 Notebook 1 will deliver the first real `project_root.py` and `performance_setup.py`.

## 2.1 Multi-Variant Dataset Usage & Validation Strategy (added 2026-09-29)

Six variants exist (Section 2), each an independently-generated synthetic simulation — not subsamples of
one another. Two axes: **HI vs. LI** (Higher vs. Lower embedded illicit-transaction ratio — LI is the
realistic, harder case: laundering as a rare needle in a huge haystack, closer to what a real bank sees; HI is
deliberately easier, generated with proportionally more laundering activity for fast development). **Small vs.
Medium vs. Large** (independent simulations at increasing transaction volume, real-verified: HI-Small 475.7MB,
LI-Small 650.4MB, HI-Medium 3.03GB, LI-Medium 2.98GB, HI-Large 17.05GB/179.7M transactions, LI-Large
16.74GB/176.1M transactions).

**Hard rule: variants are never merged or concatenated.** Because each variant is its own independent
simulation with its own Entity IDs/Bank IDs, pooling rows across variants into one training set would mix
unrelated synthetic worlds — not a valid operation. "Using multiple variants" always means separate runs of
the same notebook against different variants, compared side by side and explicitly labeled by which variant
produced which number — never a blended, unlabeled figure.

**Per-notebook staged pattern (every BP, Section 4):**

| Notebook | Variant(s) used | Why |
|---|---|---|
| 1. Business Understanding & Policy | HI-Small **and** LI-Small, side by side | Cheap at Small scale; documents the real illicit-ratio difference with real numbers before any model is built |
| 2. Feature Engineering & Modeling | HI-Small only | Fast build/debug iteration — a bug costs seconds here, never the reported result |
| 3. Statistical Validation & Deployment | HI-Small baseline + the BP's mandatory realism-validation tier (below) | The identical, unchanged notebook is re-pointed at the harder variant via one config line (`DATASET_VARIANT`) and re-run for real; both results reported side by side |
| 4. Reporting | Whichever real runs Notebook 3 produced, each figure labeled by variant | Never blends a HI-Small number and a harder-variant number into one unlabeled figure |

**Locked policy (user-confirmed 2026-09-29): LI-Medium is the mandatory realism-validation tier for every BP**
before that BP's results count as final — already independently row-count-verified against the paper's real
statistics. HI-Large/LI-Large stay an optional stretch validation per BP, not a blocking requirement, now that
both files' real row counts are independently confirmed (this section, above).

**Per-BP validation-tier detail (why each BP's realism/scale need differs):**

| BP | What it needs beyond HI-Small | Mandatory tier | Optional stretch |
|---|---|---|---|
| BP1 Transaction Monitoring | The realistic-imbalance stress test itself — core "needle in haystack" problem | LI-Medium | LI-Large |
| BP2 Typology Detection | Enough real examples of each of the 8 typologies to train a stable multi-class model — scale matters as much as ratio | LI-Medium (or HI-Medium if typology counts are thin) | HI-Large / LI-Large |
| BP3 Network Intelligence | Real network complexity — long chains and deep fan-out trees only show up at real scale; the BP that benefits MOST from Large | LI-Medium | HI-Large or LI-Large — genuinely worth pushing to if feasible |
| BP4 Structuring/Smurfing | Enough real structuring instances plus the realistic-imbalance check | LI-Medium | LI-Large |
| BP5 Correspondent Banking/Cross-Border | Enough distinct banks/countries for a real cross-border story — scale matters more than ratio | HI-Medium or LI-Medium | HI-Large |
| BP6 Enterprise Rollup | Nothing new — inherits BP1–BP5's own variant choices, each labeled | N/A (pass-through) | N/A |

**One legitimate cross-variant technique, used sparingly and always labeled as such:** for BP1/BP2/BP4, scoring
a model *trained* on HI-Small against LI-Small's transactions is a real, honest out-of-distribution
generalization check — "does this model, never having seen LI-Small's accounts, still perform reasonably on an
independently-simulated harder scenario?" This is reported explicitly as a generalization/robustness check,
never presented as a standard holdout metric, since LI-Small's ground truth belongs to entirely different
synthetic entities than whatever the model trained on.

## 3. Business Problem Portfolio — 6 BPs, all independently ground-truth-verifiable

| BP | Business Problem | Real-world name (verified) | Ground truth in dataset | Core technique |
|---|---|---|---|---|
| BP1 | Transaction Monitoring & Suspicious Activity Detection | "Transaction monitoring system" (Federal Reserve consent order, American Express Bank International) / "computer monitoring system [that] issued alerts" (FinCEN assessment, JPMorgan Chase) | `Is Laundering` — real, direct label | Supervised imbalanced classification, PR-AUC primary |
| BP2 | Typology & Red-Flag Pattern Detection | "Red flags" (FinCEN assessment, JPMorgan Chase, re: the Madoff/BLM case) | `Patterns.txt` — real block-structured ground truth, 8 typologies (fan-out, fan-in, gather-scatter, scatter-gather, cycle, random, bipartite, stack) | Multi-class typology classification |
| BP3 | Transaction Network & Graph Intelligence | Not independently confirmed as that prior platform/JPMorgan-specific terminology (flagged honestly — standard industry practice, not verified in the two primary documents checked) | Account-to-account structure (`From Bank`/`Account`/`To Bank`/`Account.1`) — real, no label needed | Graph analytics — centrality, community detection, money-flow tracing |
| BP4 | Structuring & Smurfing Detection | Tied to the BSA structuring statute (31 U.S.C. §5324) — a mandatory examination area at every BSA-regulated bank | `Amount Paid`/`Amount Received` + `Timestamp` sub-threshold-splitting patterns, cross-checked against `Is Laundering` | Rule-derived feature detection + supervised validation |
| BP5 | Correspondent Banking & Cross-Border Wire Risk | High-priority industry-wide area post-HSBC/Standard Chartered/Danske Bank enforcement actions | `From Bank`/`To Bank` + country-tagged `accounts.csv` (e.g. "Portugal Bank #4507") — real cross-institution, cross-border structure | Cross-border flow analytics |
| BP6 | Enterprise AML Compliance Monitoring & Regulatory Reporting | "AML Compliance Program" oversight function (JPMorgan Chase's own official Global Financial Crimes Compliance page) | Pure rollup of BP1–BP5 outputs — no independent label needed | Executive KPI rollup + regulatory reporting |

**Dropped from the original 8-BP draft, with reasons:** Account/Entity AML Risk Scoring (real function, real terminology at that prior platform — "customer assessment risk-ratings" — but `accounts.csv` carries no independent risk label, so this would be a proxy built by aggregating BP1's own transaction-level label upward, not independently validated); Alert Escalation/SAR-Filing Prediction (no independent SAR-filed/not-filed label exists anywhere in this dataset — only `Is Laundering`); GenAI SAR Narrative Assistant (a generation task with no ground truth to validate output against); Alert Prioritization & Case Decision Engine (a composite/policy layer over the other BPs' scores, not an independently trained or validated model).

**Phase grouping:**

| Phase | BPs | Rationale |
|---|---|---|
| Phase 1 — Detection Foundation | BP1, BP2 | No upstream dependency; both train directly against real dataset labels |
| Phase 2 — Network & Specialized Typology | BP3, BP4 | BP3 soft-depends on BP1's entity-level scores for enrichment; BP4 reuses BP2's typology feature groundwork |
| Phase 3 — Cross-Border Intelligence | BP5 | Consumes BP1–BP4 as contextual features where useful, independently trainable on its own |
| Phase 4 — Executive & Regulatory Intelligence | BP6 | Pure rollup, built last, reads every prior BP's own summary JSON |

Phase 4 here replaces v1.0's Phase 4 (GenAI Augmentation, retired) and Phase 5 (renumbered to Phase 4 since GenAI's phase no longer exists).

## 4. Per-Business-Problem Notebook Lifecycle

4 notebooks per BP (confirmed choice — that prior platform pattern, matches the already-drafted BP1 Notebook 1):
1. Business Understanding & Policy
2. Feature Engineering & Modeling
3. Statistical Validation & Deployment
4. Compliance-Impact Reporting & Packaging — this BP's own executive rollup, its own five-format package (Section 7)

Standing rules carried unchanged (full detail in `LESSONS_LEARNED_APPLIED.md`): zero-fabrication; the execution-boundary rule (Claude writes notebooks/src only, never executes — not even a fixture — in the sandbox; all real numbers come from the user's own run); one markdown intro + one code cell per notebook; idempotent overwrite-in-place outputs; `RANDOM_SEED=42`; two-gate verdict architecture (structural `[CHECK]` vs. statistical-robustness gate, named to fit what's actually being tested, never forced); `configure_performance()` called as the literal first executable step, before any heavy import (Lesson #5); a stale `__pycache__` check after every `src/` change (Lesson #6); every computed ratio gets an explicit undefined-count check, never a silent impute (Lesson #7); a BP's report package generation is gated only on the structural `[CHECK]` gate, never on the statistical-robustness verdict (Lesson #14); no threshold or parameter is ever quietly tuned toward a target verdict (Lesson #15).

## 5. Model Benchmark Specification — AML-Adapted

- **Imbalance handling:** PR-AUC (never ROC-AUC alone) as the primary champion-selection metric; cost-sensitive class weighting, never naive resampling as the default; decision threshold from a real cost curve, not the default 0.5.
- **Candidate set (Stage A):** LightGBM, XGBoost, CatBoost, Random Forest (real single split) plus Isolation Forest as an unsupervised comparator (reported, never blended into the supervised score).
- **Stage B:** 5-fold CV on the top-2 Stage-A candidates; champion = higher mean CV PR-AUC; SHAP + LIME for the champion only; formal CV report with per-fold variance, not just the mean.
- **Graph/network leakage discipline (Lesson #11):** every graph feature (BP3, and any BP that reuses an entity-level graph feature) is computed only from the train-time snapshot; no test-period edges, aggregates, or community-detection output may leak into training features. Enforced as its own structural `[CHECK]` gate, documented explicitly per-BP in that BP's `configs/bpN_*.yaml`.
- **Deployable scoring services (per BP, that prior platform Phase-2-hardening pattern):** each BP that reaches Notebook 3 gets a FastAPI service wrapping its real scoring function, verified bit-identical to direct computation, with a self-test that checks every real row it can reach — never one sample row (Lesson #4) — and reports a magnitude column on any mismatch, not just a pass/fail count (Lesson #4, #superseded-bug-3-pattern). Any weighted-sum reconstruction in a deployable service must replicate the source notebook's real iteration order exactly (Lesson #3), and any value the service consumes must be the full-float-precision value the source notebook saved, never a display-rounded or independently-recomputed one (Lesson #2).

## 6. Regulatory & Compliance Framework

| Framework | Applies to |
|---|---|
| Bank Secrecy Act (31 U.S.C. §5311) | Platform-wide |
| BSA structuring statute (31 U.S.C. §5324) | BP4 |
| USA PATRIOT Act §326 (CIP), §314(a)/(b) | BP1, BP5 |
| FinCEN SAR filing requirements (31 CFR §1020.320) | BP1, BP2 (evidence feeding any future SAR workflow, not itself a SAR-prediction model — see Section 3) |
| OFAC sanctions-list screening | BP1, BP5 |
| FFIEC BSA/AML Examination Manual (5 pillars) | Platform-wide |
| FATF 40 Recommendations | BP2, BP6 |
| Wolfsberg AML Principles (correspondent banking) | BP5, BP6 |
| SR 11-7 Model Risk Management | Every model-bearing BP |
| GDPR / cross-border data handling | BP3, BP5 (network-graph and cross-border PII) |

**Fairness/bias testing:** unchanged from v1.0 — the confirmed schema carries no demographic fields, so an ECOA/FCRA-style disparate-impact test is not computable here. Flagged "Not Possible – Data Limitation," never silently skipped.

## 7. Deliverables Package per Business Problem

Every BP closes with a **five-format executive package**, generated by the shared `src/reporting/report_builder.py` module (that prior lending-risk platform's proven pattern — built once, imported by every BP, never hand-coded per-notebook): a standalone deployable FastAPI scoring service (Section 5); Word report + Excel workbook (real formulas, an Assumptions sheet built FIRST with yellow fill/blue font for every hardcoded input, every other sheet's dollar figures as live formulas referencing it, AutoFilter, recalc-verified) + HTML dashboard (Chart.js bundled locally, never CDN-loaded; real slicers/filters, KPI tiles, and vanilla-JS interactivity — not static images; the dataviz skill's validated CVD-tested palette, never a flat single color) + a PowerPoint executive deck (board/investigator-briefing version of the same real numbers) + a PDF export (rendered from the Word report or deck, never a separately authored source of numbers). Metrics reframed to compliance-impact terms: false-positive reduction (investigator hours saved), true-positive/typology-confirmation uplift, alert-to-case conversion ratio where applicable, illustrative regulatory-exposure-avoidance explicitly labeled ASSUMPTION. Dollar figures always with B/M shorthand. `MODEL_CARD.md` + `CHANGELOG.md` per BP. Docker packaging (`src/docker/{Dockerfile,docker-compose.yml,.dockerignore}` per BP, build-context documented in the Dockerfile header and MODEL_CARD.md — that prior platform's Phase-2-hardening pattern, including its real caught bug: never default a bundle/model path to a file that isn't actually copied into the image).

The moment a BP's HTML dashboard is committed to `github_repo/`, that BP's own README and the root README both get a "Live Dashboard" link added immediately — GitHub's file browser only shows raw source for `.html`, never the rendered page; only a linked GitHub Pages URL renders it (Lesson #13).

## 7A. Before/After Financial Impact — Mandatory in Every BP (added 2026-09-29)

A model's real performance metrics alone are not a financial-impact story on their own — no reader can judge
impact without knowing what the same real holdout looked like *before* the model existed. Every BP computes
both sides on the SAME real holdout run, in that BP's own Notebook 3, and surfaces the comparison as the lead
table + chart in Notebook 4's five-format package: a table with columns `Metric | Before (baseline) | After
(ML model) | Delta | $ Impact`, a paired bar or waterfall chart, and — for BP6's platform rollup — the
platform's main KPI row. Neither side is ever estimated or carried over from a different dataset; both are
real-computed by the same run that produces the champion model. False-positive-reduction $ savings and
true-positive/detection uplift are always reported as two separate lines, never summed into one blended dollar
figure (same discipline as the BENEFIT/COST CONTEXT/PORTFOLIO SCALE separation in Section 8).

**Per-BP "Before" baseline (real, same-data, never a straw-man) — full detail in `LESSONS_LEARNED_APPLIED.md` Lesson #16:**

| BP | Before (baseline) | After (ML model) |
|---|---|---|
| BP1 Transaction Monitoring | Fixed-dollar-threshold rule, no other logic | Real precision/recall at the selected model threshold |
| BP2 Typology Detection | Single-typology heuristic (obvious cases only) | Real per-typology recall across all 8 patterns |
| BP3 Network Intelligence | Single-account (non-network) review | Graph-connected-cluster review (volume-scale KPI, not dollarized without a sourced per-account cost) |
| BP4 Structuring/Smurfing | Fixed threshold-adjacent rule | Multi-transaction/multi-timeframe split-pattern detection |
| BP5 Correspondent Banking/Cross-Border | Binary high-risk-country-list screening | ML-scored cross-border risk signal |
| BP6 Enterprise Rollup | — | Pure sum of BP1–BP5's own already-computed deltas, shown as the platform's main KPI row |

Implementation: one shared `build_before_after_comparison()` function in `src/reporting/report_builder.py`,
written once and reused by all 6 BPs — never a hand-coded per-BP dollar figure.

## 7B. No Synthetic Placeholder Output, Ever — Original Insight Required in Every Document (added 2026-09-29)

Two rules already implicit in zero-fabrication (Section 1), stated explicitly here per direct instruction:
(a) a notebook delivered before its real run prints `NOT YET COMPUTED — requires a real run on real data` for
any section needing a real number, never a synthetic/illustrative placeholder dressed up as a result — BP1
Notebook 1's EDA section already does this and is the template for every notebook after it; (b) every BP's
Notebook 4 narrative states at least one real, dataset-specific observation from that BP's own actual run —
generic AML textbook language is acceptable only as background/definition text, never as a stated finding or a
justification for a business recommendation. Full detail in `LESSONS_LEARNED_APPLIED.md` Lesson #17.

## 8. Executive Rollup Architecture

Two rollup layers, both mandatory:
- **Per-BP rollup:** each BP's own Notebook 4 (Section 4) is that problem's executive rollup — its own five-format package (Section 7), not a raw results dump.
- **Platform-wide rollup:** 4 phase-level rollup notebooks (Section 3) + 1 platform-level master rollup, pure pass-throughs reading each BP's own already-computed summary JSON, recomputing nothing (that prior lending-risk platform's proven pattern).

Both the phase-level rollups and the platform-level master rollup ship the identical five-format package used at BP level, scaled to phase-wide and platform-wide numbers.

Three financial categories never blended, in every rollup: **BENEFIT** (summed into a headline run-rate), **COST CONTEXT** (informational only, never summed into the headline), **PORTFOLIO SCALE** (volume context only).

## 9. WARP — Resource Governance (extended: thermal protection)

Unchanged core: `configure_performance()` sets a hardware-detected thread ceiling via env vars (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, `POLARS_MAX_THREADS`, `RAYON_NUM_THREADS`) BEFORE any heavy import — a safety CAP at ~92% of logical cores and ~92% of RAM, never 100%, never a floor to force by padding workload. No GPU/NPU path exists in this stack (XGBoost/LightGBM/CatBoost/scikit-learn all run CPU-only) for WARP to activate.

**New — thermal protection (this project only, added at the user's explicit request):** a `thermal_checkpoint()` context manager in `performance_setup.py` inserts a real `time.sleep(12)` pause — 12 seconds, user-confirmed 2026-09-29 (no longer an assumption) — after any operation tagged heavy: a full CSV/Parquet load, a model `.fit()` call, a graph-construction step. Not applied after every cell — only after genuinely heavy operations, since pausing after trivial ones burns wall-clock time for no thermal benefit. This code runs on the user's machine when the user runs the notebook; Claude never executes it. Not yet written to `src/utils/performance_setup.py` on disk as of this plan's date — queued as part of Notebook 00's build.

## 9.2 Polars & Vectorization — Mandatory (added 2026-09-29)

A coding-technique mandate, separate from WARP's resource-ceiling mandate above — both apply together. Every
heavy data operation uses Polars lazy scan + expression API (`pl.scan_csv(...).select(...).filter(...).collect()`,
column-projected) or DuckDB SQL, never eager pandas on the larger variants. Every per-row transformation is a
vectorized Polars/NumPy expression — never a Python-level `.apply()`, `.iterrows()`, or manual for-loop over
rows. The goal: turn a full-dataset operation that would take hours in interpreted row-by-row Python (e.g.
loading and aggregating HI-Large's ~17GB file) into minutes, and per-transaction feature computations into
milliseconds, through columnar/vectorized execution. `load_csv_cached()` (already in `performance_setup.py`,
Parquet-over-CSV) is used for any file read more than once across notebooks in the same BP.

Every notebook wraps its heaviest operations in the existing `timer`/`timed` utilities from `performance_setup.py`
and prints the real measured elapsed time. Claude never states an expected speedup number without the user's
own real run confirming it — zero-fabrication applies to performance claims exactly as it does to model
metrics. Full detail in `LESSONS_LEARNED_APPLIED.md` Lesson #18.

## 9.3 Ultra-High-Quality Performance Standard — Real Techniques From Prior Platforms' Logs (added 2026-09-29)

Compiled directly from the real, dated bugfix/build-history logs of the prior credit-risk platform and the prior lending-risk platform (the
only two prior platforms with a dedicated, detailed performance-lesson record — the prior fraud-risk platform and the prior customer-intelligence platform
Navigator have no equivalent log to draw from, honestly disclosed rather than assumed, consistent with Section
15). Every technique below is a real fix to a real, user-reported slow-runtime or low-utilization bug on one
of those platforms, not a generic best-practice list — each is now MANDATORY on this platform:

1. **WARP ceiling actually applied before import** (Lesson #5): `configure_performance()` runs as the literal
   first executable step, before Polars/pandas/scikit-learn/XGBoost/LightGBM/CatBoost are imported. Home
   Credit's real regression: a configured 90–95% ceiling sat unused because the env vars were set after those
   libraries had already imported — the real run measured only ~20% CPU / ~50% RAM on an 8-core/16-thread
   machine.
2. **No-multicore-benefit models dropped from candidate sets**: scikit-learn's `GradientBoostingClassifier`
   (no real multi-core support) and `LogisticRegression` (`n_jobs` has no effect for binary classification) are
   excluded from this platform's Stage-A benchmark screen (Section 5) if either would otherwise be included —
   they silently pin execution to one thread regardless of the WARP ceiling.
3. **Parquet-over-CSV caching** (`load_csv_cached()` in `performance_setup.py`): any file read more than once
   across a BP's notebooks is cached to Parquet on first read; every later read hits the cached Parquet file
   instead of re-parsing raw CSV text.
4. **Lazy, column-projected scans over eager full loads**: `pl.scan_csv(path).select([...]).filter(...)
   .group_by(...).agg(...).collect()` — only the columns and rows actually needed are ever materialized.
   Proven on that prior platform's real 16GB+ raw CSV; directly applicable to this project's own ~17GB HI-Large file.
5. **Closed-form / multinomial resampling over brute-force bootstrap** (real slow-runtime bug, that prior lending-risk platform
   Notebook 05): a bootstrap CI on a chi-square/Cramer's V statistic was rebuilding a `pandas.crosstab` from
   scratch on each of 500 row-level resamples over ~1.67M real rows. Fixed by drawing directly from the
   already-computed contingency table via `rng.multinomial(n, p)` — mathematically equivalent, orders of
   magnitude faster. MANDATED for every bootstrap CI this platform computes (BP2's per-typology chi-square/
   Cramer's V tests, BP4's structuring-pattern significance tests, and any other categorical-association CI).
6. **Vectorized, batched simulation over per-iteration Python loops** (that prior lending-risk platform's MP2 Notebook 03, real
   Vasicek capital Monte Carlo): any simulation draws one batched array (`rng.<dist>(size=(N_SIMS, ...))`) and
   reduces it with array operations — never a Python `for` loop over simulation trials. Applies to any
   resampling/simulation step this platform needs (e.g. a network-propagation or alert-volume simulation in
   BP3/BP6).
7. **Eliminate redundant recomputation across notebook stages** (real architectural fix, that prior platform's Notebook 27 to
   28): a downstream notebook reads an earlier notebook's own saved full-precision value directly rather than
   reloading a multi-GB source file and recomputing the same statistic — a genuine efficiency win that also
   removes an entire class of drift bug (see Lesson #2). MANDATED for every BP-to-BP handoff on this platform:
   BP6's rollup never recomputes what BP1–BP5 already computed; a BP's later notebook never re-derives a
   feature its own earlier notebook already engineered.
8. **`timer`/`timed` instrumentation on every heavy step**: every notebook prints the real measured elapsed
   time for each heavy operation — the only legitimate basis for any speed claim on this platform.

**On "milliseconds to nanoseconds" (user's stated target, addressed honestly):** a single vectorized Polars/
NumPy expression over a column genuinely executes at microsecond-to-nanosecond-per-row scale, because it runs
as compiled, SIMD-vectorized machine code rather than interpreted per-row Python — that PER-OPERATION bar is
real, achievable, and is the mandated code-quality standard for every transformation in this project (never a
`.apply()`, `.iterrows()`, or manual loop, per Lesson #18). Total end-to-end wall-clock time for a full BP run
against real data (up to ~17GB per file) is a separate, honest number: measured live via `timer`/`timed` on the
user's own machine and reported as-is in that notebook's output and in Section 7A. No notebook or report on
this platform claims a nanosecond TOTAL runtime — only genuinely nanosecond/microsecond-scale PER-OPERATION
vectorized execution, the same zero-fabrication discipline that governs every other number this project
reports. Full detail in `LESSONS_LEARNED_APPLIED.md` Lesson #19.

## 10. HYPER — Delivery Acceleration

10 techniques adopted (2 excepted), carried from that prior platform's Hypersonic pass — full detail in `LESSONS_LEARNED_APPLIED.md` Lesson #12: one master notebook template cloned per BP; the same Dockerfile/CI workflow/Makefile/pyproject.toml reused across all 6 BPs; notebook-writing/infra/API-testing run as parallel work streams; batched commits across several notebooks; one parametric notebook driven by `configs/bpN_*.yaml`; a shared `src/` component library built once; auto-generated per-BP docs from docstrings; pre-commit hooks rejecting bad commits before push; parallel CI jobs; a per-BP incremental-validation gate before the next BP starts. Excepted: smoke-test-only as a substitute for full coverage (never — this platform's tests stay full/bit-exact); unverified CLI scaffolding tools (hand-written instead).

## 11. Project Structure & Governance

Folder layout: see `PROJECT_STRUCTURE_LOCKED.md` (re-locked 2026-09-29 to the 6-BP scope). Governance files at project root, added 2026-09-29 to match that prior platform's Phase-2-hardening "Global Standard" pattern: `.github/ISSUE_TEMPLATE/` (bug_report, feature_request, model_improvement), `.github/PULL_REQUEST_TEMPLATE.md`, `pyproject.toml`, `Makefile`, `BENCHMARKS.md` (consolidated real baseline-vs-model comparisons, populated only from real run numbers, never estimated), `.pre-commit-config.yaml`. CI split into `ci.yml` (lint/test/notebook-syntax, pre-existing) and `code-quality.yml` (bandit security scan of `src/` — given extra weight here per AML data sensitivity, same reasoning as v1.0 Section 9).

`requirements.txt` updated 2026-09-29: removed the now-dead GenAI/NLP stack (spacy, sentence-transformers, transformers, tokenizers — BP6-GenAI is retired); added `python-pptx` (was missing entirely despite the five-format package requiring it), `lime` (paired with `shap` per Section 5), `imbalanced-learn`, `pytest-cov`, `bandit`.

## 12. CRISP-DM / AGILE / SMART / 6-Gate SOP

Every BP notebook lifecycle (Section 4) maps to CRISP-DM: Notebook 1 = Business Understanding; Notebook 2 = Data Preparation + Modeling; Notebook 3 = Evaluation + Deployment; Notebook 4 = pure reporting (no new CRISP-DM stage — a compliance-specific addition on top of the standard 6 stages). The 6-Gate SOP (Gate 1 Business Understanding through Gate 6 Production Packaging/Governance) is the same governance overlay used on that prior lending-risk platform, tracked per-BP in the Evidence Ledger. AGILE sequencing: each BP is its own sprint-sized unit of work, one BP completed and validated before the next starts (HYPER's incremental-validation gate, Section 10) rather than all 6 BPs built in parallel with nothing finished. SMART framing applies to every headline finding in every BP's Notebook 4: specific (a named metric), measurable (a real computed number), achievable (grounded in what the dataset can actually support, per Section 3's tiering), relevant (tied to a real regulatory or operational driver, Section 6), time-bound (framed against a stated run-rate or reporting period, never open-ended).

## 13. GitHub Packaging

Unchanged pattern from prior platforms in this same methodology lineage: `git init`/`commit` never happens inside the mounted Documents folder (fuseblk blocks the unlink operations git's object store needs — Lesson #9); content is staged in `github_repo/` here, then actually committed and pushed from a real local disk path outside any mounted/proxied folder. A GitHub PAT is verified via a non-empty `x-oauth-scopes` header containing `repo` before use (Lesson #10), and revoked after the push completes. (The third-party notebook-publication step from the original v1.0 plan has been retired -- this platform's real dataset citation is IBM's own GitHub index page, Kaggle as the real direct-download location, and IBM's own Box storage as a mirror; see README.md's Dataset section.)

## 14. Open Decisions Requiring Confirmation

1. ~~Dataset variant~~ — RESOLVED: HI-Small for primary build (Section 2).
2. ~~Per-BP notebook count~~ — RESOLVED: 4 notebooks (Section 4).
3. ~~Folder/BP structure~~ — RESOLVED: clean rebuild to the 6-BP scaffold (Section 11, `PROJECT_STRUCTURE_LOCKED.md`).
4. ~~Project name~~ — RESOLVED: IBM AML RiskIQ (accurate attribution — the dataset genuinely is IBM Research's).
5. ~~Thermal-protection exact cadence~~ — RESOLVED 2026-09-29: 12 seconds, user-confirmed (Section 9).
6. ~~GitHub repo name~~ — RESOLVED 2026-09-29: `IBM_AML_RiskIQ_Enterprise_Suite`, user-confirmed, matching the folder name.

All open decisions are now resolved. Nothing outstanding blocks Notebook 00 / BP1 build start.

## 15. Lineage & Sources

Built from the original v1.0 plan (2026-09-23), the real device-verified `PROJECT_STRUCTURE_LOCKED.md` and `LESSONS_LEARNED_APPLIED.md` (both already present on-device, predating this session — read and reconciled with, not overwritten wholesale, 2026-09-29), and the standing methodology documented for the prior credit-risk platform and the prior lending-risk platform (both independently re-read this session — Phase 2 hardening pass, HYPER delivery techniques, and the full bugfix/lessons-learned history). the prior fraud-risk platform and the prior customer-intelligence platform remain named as the platforms this project's original folder scaffold was mirrored from 1:1; their detailed build methodology was not independently re-verified in this session beyond that structural match, same flag as v1.0 — no dedicated memory record for either exists to check against, honestly noted rather than assumed.
