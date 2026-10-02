# Lessons Learned - Applied From AMEX RiskIQ, Home Credit RiskIQ & Customer360 Navigator

Real bugs and real fixes from the three prior platform builds, consolidated into standing rules for every
notebook and src/ module in this project. Read this before writing BP1's first notebook.

## 1. Never infer a column's dtype or granularity from its name alone
AMEX Notebook 27 assumed a `_last`-suffixed column was numeric because of its name; it was a real categorical
status code (dtype 'CR'). Home Credit Notebook 34 assumed a file named "features" was per-statement raw data;
it was already aggregated to one row per customer. STANDING RULE: always verify dtype (`pd.api.types.is_numeric_dtype`)
and granularity (row count vs. expected entity count) against the actually-loaded data, every time, never from
a filename or column-name pattern. On this platform this applies directly to the AML transaction schema
(e.g. confirm `Is Laundering`, account/bank ID fields, and amount fields against the real loaded dtypes before
BP1 assumes anything about them).

## 2. Never let a display-rounded or independently-recomputed value feed downstream scoring
AMEX Notebook 28's deployed scorer read a CSV column that had been rounded to 5 decimal places for human
readability, then used that rounded value as a real scoring weight - across ~243 features the rounding error
compounded into real decision-boundary flips (7 of 91,783 real holdout customers). STANDING RULE: any value
consumed by downstream scoring/deployment code is saved at full float precision, never rounded, even in a
column someone might reuse later; the downstream notebook reads that saved value directly rather than
recomputing it from a fresh reload.

## 3. Match iteration order exactly when reconstructing a weighted sum
A saved CSV's row order (often sorted for display, e.g. by weight descending) is not safe to reuse for
re-deriving a float sum computed in a different order (e.g. alphabetical) upstream - floating-point addition is
not associative. STANDING RULE: if a standalone/deployed scorer reconstructs a sum from saved per-feature
values, it must replicate the original notebook's real iteration order explicitly (e.g. `sorted(features)`),
not the display order of the saved file.

## 4. A self-test must check every reachable real row, not one sample
A single-customer self-test can pass "by luck" if that customer isn't near a decision boundary - AMEX's Bug 2
only surfaced on the full ~92k-row real holdout, never on a 500-row fixture. STANDING RULE: every standalone-
scorer or API self-test checks ALL real rows it can reach and reports a magnitude (a diff column), not just a
pass/fail count - a boundary-tie vs. hard-mismatch classification is only trustworthy once backed by a printed
number. On this platform, this applies to any alert-scoring or SAR-priority self-test in BP3/BP7.

## 5. Configure the hardware/thread ceiling before any heavy import, and call it
Home Credit's Notebook 02 computed a WARP thread ceiling but never actually called `os.environ[...] = ` before
polars/pandas/sklearn/xgboost/lightgbm/catboost were imported - no library ever saw the ceiling, and the real
run used ~20% CPU / ~50% RAM on an 8-core/16-thread/32GB machine. STANDING RULE: call
`performance_setup.configure_performance()` as the literal first executable step, before any heavy import.
Also drop any model with no real multi-core support (e.g. sklearn's GradientBoostingClassifier) from a
CPU-parallel benchmark set rather than letting it silently pin execution to one thread.

## 6. A stale __pycache__ can reintroduce an already-fixed bug
A corrected shared/ module still failed to import correctly because an old `.pyc` in `__pycache__/` had a
newer name but an older mtime than the fix. STANDING RULE: after delivering any src/ module change, check for
and truncate any stale `__pycache__/*.pyc` on the device before assuming the fix landed.

## 7. An un-imputed ratio fed into a raw numpy call can fail silently, not loudly
`np.percentile()` on a division result with an undefined denominator returns NaN without raising - the failure
only surfaces later, at an unrelated plotting call. STANDING RULE: any computed ratio (e.g. an account's
outbound/inbound transaction-value ratio in BP2/BP4) gets an explicit undefined-count check and exclusion
(never a silent impute for a purely descriptive ratio), with a finiteness assertion immediately after.

## 8. Fixture testing catches most bugs; only your real run catches the rest
Every bug above except #5 and #8's own lesson was caught only after a real run on real, full-size data, even
though fixture testing had already passed. STANDING RULE (already in the Master Execution Plan's Gap Register
#1 and Quality Gates on the prior platforms): two checkpoints are mandatory for every BP - a schema-matched
synthetic-fixture execution, and your own real run reported back. Neither alone marks a BP complete.

## 9. git cannot run inside this mounted Documents folder
git's object-store bookkeeping needs real unlink, which a device-mounted (fuseblk) folder blocks - confirmed
on AMEX's GitHub push. STANDING RULE: the actual `git init`/`commit` never happens inside this folder. Content
meant for GitHub is staged in `github_repo/` here, then committed and pushed following the workflow documented
in `github_repo/README.md`.

## 10. A GitHub PAT with empty oauth-scopes authenticates but cannot push
A classic PAT can pass a basic `GET /user` check while still having no `repo` scope checked at creation,
causing a silent-looking 404 on `POST /user/repos`. STANDING RULE: verify the `x-oauth-scopes` response header
is non-empty and contains `repo` before assuming any PAT is usable.

## 11. A graph/network feature (new to this platform, BP4) needs its own leakage discipline
Not yet a real-run-observed bug on this platform - flagged in advance, not assumed as fixed. Any network
centrality or money-flow feature (e.g. an account's degree, PageRank, or component size) computed over the
FULL dataset before a train/test split can leak future/test-set structure into training features. STANDING
RULE: compute or re-validate every graph feature within the same train/test (and CV fold) boundaries used for
the rest of BP4/BP7, and document the computation window explicitly in that BP's config.

## 12. HYPER delivery-acceleration techniques (from AMEX's Hypersonic pass) - 10 adopted, 2 excepted
Adopted for this project's build process (build/delivery speed, kept separate from WARP's runtime speed): one
master notebook template cloned per BP; the same Dockerfile/CI workflow/Makefile/pyproject.toml reused across
all 6 BPs; notebook-writing, infra, and API/testing run as parallel work streams; batched commits across
several notebooks rather than one per notebook; one parametric notebook driven by `configs/bpN_*.yaml` rather
than hand-edited copies; a shared `src/` component library built once and imported everywhere; auto-generated
per-BP docs from docstrings; pre-commit hooks rejecting bad commits before push; parallel CI jobs; a
per-BP incremental-validation gate before starting the next BP. EXCEPTED (never applied on this project, same
as AMEX): smoke-test-only as a substitute for full test coverage, and any CLI scaffolding tool not independently
verified as a real installable package - those get hand-written instead.

## 13. An HTML dashboard must be explicitly linked from a README, or nobody can see it rendered
GitHub's own file browser shows raw source for a `.html` file - only GitHub Pages actually renders it. On AMEX,
Phase 2's three dashboards were built and even Pages-deployed, but never linked from any README, so the user
saw "code only" when clicking them. STANDING RULE: every BP's five-format package gets a "Live Dashboard"
section added to that BP's own README AND the root README the moment its HTML dashboard is committed to
`github_repo/`, not deferred to a later cleanup pass.

## 14. A BP's report package is never gated on its own statistical verdict
Home Credit's MP3 Notebook 03 (Repayment Behavior Segmentation) genuinely failed its statistical-robustness gate
on real data (Cramer's V ~0.0179, below threshold) after two honest methodology attempts - and all three report
formats (docx/xlsx/html) plus the governance JSON and model artifact were still generated and delivered exactly
as if it had passed, with the honest "NOT YET STATISTICALLY ROBUST" verdict stated plainly inside them. STANDING
RULE: a BP's five-format package generation is gated only on the structural `[CHECK]` integrity gate completing,
never on the separate statistical-robustness verdict - a failed robustness gate is reported honestly in the
package, not hidden by skipping the package.

## 15. Never loosen a statistical threshold to force a PASS - change methodology and disclose it, or accept the honest result
On Home Credit MP3, a user-sourced suggestion to set `CRAMERS_V_ROBUST_THRESHOLD=0.0` was identified as
check-gaming (proven arithmetically: 0.0149>0.05 is False but 0.0149>0.0 is True - only the threshold moved, not
the underlying number) and rejected; the honest "NOT YET STATISTICALLY ROBUST" verdict was kept instead. By
contrast, MP3 NB02's real fix (loosening `bureau_segment_min_cluster_fraction` from 3% to 1%, matching an
already-established precedent elsewhere in the same platform) was a genuine, disclosed methodology change that
happened to also produce a PASS - the distinction is disclosure and precedent, not the direction of the number.
STANDING RULE for this platform: any threshold or parameter change on this project must be disclosed in the
notebook's own markdown and justified against real precedent, never quietly tuned toward a target verdict.

## 16. Every BP reports a real Before/After financial comparison, never "After" alone - and never a fabricated "Before"
Added at the user's explicit request (2026-09-29): a model's real performance metrics alone ("94% precision")
are not a financial-impact story - a reader cannot judge impact without knowing what the same real holdout
looked like BEFORE the model existed. STANDING RULE: every BP computes both sides on the SAME real holdout run,
in that BP's own Notebook 3, and surfaces the comparison as the lead table + chart in Notebook 4's five-format
package (tabular columns: Metric | Before (baseline) | After (ML model) | Delta | $ Impact). Neither side is
ever estimated, industry-cited, or carried over from a different dataset - both are real-computed by the same
run that produces the champion model.

Honest, real, same-data "Before" baseline per BP (never assumed, never a straw-man):
- BP1 Transaction Monitoring: a fixed-dollar-threshold rule (flag every transaction above a stated amount, no
  other logic) run on the identical real holdout.
- BP2 Typology Detection: a single-typology heuristic (only the structurally obvious cases a human would catch
  without a model) vs. the real multi-class model's per-typology recall across all 8 patterns.
- BP3 Network Intelligence: single-account (non-network) review vs. graph-connected-cluster review - reported
  as a volume-scale KPI (additional real accounts/transactions pulled into an investigation), never dollarized
  without a stated, sourced per-account review-cost assumption.
- BP4 Structuring/Smurfing: the classic fixed threshold-adjacent rule (flag only transactions just under the
  reporting threshold) vs. the trained model catching multi-transaction/multi-timeframe split patterns.
- BP5 Correspondent Banking/Cross-Border: binary high-risk-country-list screening vs. the ML-scored cross-border
  risk signal, applied only to the real cross-border transaction subset.
- BP6 Enterprise Rollup: the pure sum of BP1-BP5's own already-computed Before/After deltas (never recomputed),
  shown as the platform's main KPI row.

Implementation: one shared `build_before_after_comparison()` function in `src/reporting/report_builder.py`,
written once and reused by all 6 BPs - never a hand-coded per-BP dollar figure. False-positive-reduction
$ savings and true-positive/detection-uplift are always reported as two separate lines, never summed into one
blended dollar figure (extends the existing BENEFIT/COST CONTEXT/PORTFOLIO SCALE separation, Master Plan
Section 8).

## 17. No synthetic placeholder output, ever - and every finding must be an original, dataset-specific insight
Two related standing rules, both already implicit in zero-fabrication (Lesson set above) but stated explicitly
here per the user's direct instruction (2026-09-29): (a) if a notebook is delivered before the user has run it
on real data, any section needing a real number prints "NOT YET COMPUTED - requires a real run on real data",
never a synthetic/illustrative placeholder number dressed up as a result - BP1 Notebook 1's EDA section already
does this correctly and is the template for every notebook after it; (b) every BP's Notebook 4 narrative must
state at least one real, dataset-specific observation from that BP's own actual run (a real observed typology
mix percentage, a real per-country cross-border concentration figure, a real precision/recall number) - generic
AML textbook language is acceptable only as background/definition text, never as a stated finding or a
justification for a business recommendation.

## 18. Polars/vectorization is mandatory for every heavy operation - never a Python-level loop
Added at the user's explicit request (2026-09-29): this platform's dataset scales from ~475MB (HI-Small) to
~17GB (HI-Large) per file. A pandas .apply()/.iterrows() row loop or an eager, non-projected pd.read_csv() on
the larger variants turns a real run that should take minutes into one that takes hours. STANDING RULE: every
heavy operation uses Polars lazy scan + expression API (`pl.scan_csv(...).select(...).filter(...).collect()`,
column-projected) or DuckDB SQL over pandas; every per-row transformation is a vectorized Polars/NumPy
expression, never a Python-level loop over rows; `load_csv_cached()` (already in `performance_setup.py`,
Parquet-over-CSV) is used for any file read more than once in the same BP. This is a coding-TECHNIQUE mandate,
separate from WARP's resource-CEILING mandate (Master Plan Section 9) - both apply together. Every notebook
wraps its heaviest operations in the existing `timer`/`timed` utilities and prints the real measured elapsed
time; Claude never states an expected speedup number without the user's own real run confirming it - the same
zero-fabrication discipline that governs every other reported number on this platform.

## 19. Real, log-sourced performance techniques from prior platforms - mandated together, per-operation nanosecond-scale is real, total-runtime nanosecond claims are not
Compiled 2026-09-29 directly from AMEX's and Home Credit's own real, dated bugfix/build-history logs (no
equivalent performance log exists for Fraud Shield or Customer360 Navigator - disclosed, not assumed). Eight
concrete techniques, each a real fix to a real slow-runtime or low-CPU-utilization bug on a prior platform, now
MANDATORY here: (1) `configure_performance()` called literally before any heavy import, never after (Home
Credit NB02's real regression: ~20% CPU/~50% RAM used despite a configured 90-95% ceiling); (2) models with no
real multi-core benefit (GradientBoostingClassifier, LogisticRegression) dropped from CPU-parallel candidate
screens; (3) `load_csv_cached()` Parquet-over-CSV caching for any file read more than once in a BP; (4) lazy,
column-projected Polars scans over eager full loads, proven on AMEX's real 16GB+ raw CSV; (5) closed-form/
multinomial resampling (`rng.multinomial(n,p)` against an already-computed contingency table) replacing
brute-force bootstrap that rebuilds a crosstab from scratch on every resample - the real fix to Home Credit
Notebook 05's real slow-runtime bug (500 resamples x ~1.67M rows); (6) vectorized/batched simulation
(`rng.<dist>(size=(N_SIMS,...))`) over any per-iteration Python loop, proven on Home Credit MP2 NB03's real
Vasicek Monte Carlo; (7) eliminating redundant recomputation across notebook stages - a downstream notebook
reads an earlier notebook's own saved full-precision value rather than reloading and recomputing it, the real
architectural fix from AMEX Notebook 27->28 (also closes a drift-bug class, see Lesson #2); (8) `timer`/`timed`
instrumentation on every heavy step, the only legitimate basis for any speed claim. STANDING RULE on the
"milliseconds to nanoseconds" target: a single vectorized Polars/NumPy expression genuinely runs at
microsecond-to-nanosecond-per-row scale (compiled, SIMD-vectorized execution, never interpreted per-row
Python) - that PER-OPERATION bar is real and mandated. Total end-to-end notebook wall-clock time against real
data (up to ~17GB/file) is a separate, honestly-measured number via `timer`/`timed`, reported as-is - never
asserted as a nanosecond TOTAL runtime, which would violate this platform's zero-fabrication standard.

## 20. A row-wise `.agg(func, axis=1)` is NOT vectorized - it hung the reference laptop at 100% RAM (real incident, 2026-09-30); RAM checks must ENFORCE, never just report
Real incident: BP2 Notebook 3's real LI-Medium run (31.25M real rows in `LI-Medium_Trans.csv`) hung the
reference laptop at 100% RAM usage and required a hard restart. Root cause, confirmed by a local synthetic
re-test after the crash: the real-content join key was built with `trans[KEY_COLS].agg("|".join, axis=1)`,
which LOOKS like a vectorized one-liner but pandas executes it as a genuine per-row Python loop - a direct,
undetected violation of Lesson #18 despite being labeled "vectorized" in that notebook's own header at the
time. On a 2,000,000-row synthetic frame this exact call did not finish in 2 minutes; `pd.util.hash_pandas_object`
(real, vectorized, C-implemented) did the equivalent row-key construction in ~4 seconds using ~16 MB instead of
a large Python-object string array. Contributing factor, also confirmed: `check_ram_headroom()` in
`performance_setup.py` only ever PRINTED a number - nothing in this codebase actually stopped a risky
allocation before it happened.

STANDING RULES, now MANDATORY on every future notebook on this platform:
- Never build a multi-column join/grouping key with `DataFrame.agg(callable, axis=1)`, `DataFrame.apply(...,
  axis=1)`, or any row-wise Python callable, regardless of how it is labeled in a comment. Use
  `pd.util.hash_pandas_object(df[cols], index=False)` (returns a compact uint64 per row, real vectorized C
  code) when a composite key is needed for exact-content matching/joining. A 64-bit hash collision between two
  genuinely different real rows is theoretically possible but astronomically unlikely at this platform's real
  data scale - disclosed as a real, bounded, negligible residual risk, never claimed as zero.
- `performance_setup.py` now has a real ENFORCING gate, `assert_ram_safe(min_available_gb, label)`, added
  2026-09-30 alongside this lesson - it raises `MemoryError` and stops execution if real available RAM is
  already below the given margin, rather than merely printing a number like `check_ram_headroom()` always did.
  Call it immediately before any step already disclosed elsewhere in this file as memory-heavy: a composite-key
  build over a multi-million-row real frame, a large real merge, and every RandomForest fit (this platform's
  own disclosed heaviest single candidate, per Lesson #19's context and BP1 Notebook 3's own "~28min on
  LI-Medium" note).
- RandomForest's `n_estimators`/`max_depth` are downsized for large real training sets (>5,000,000 real rows:
  120 trees / depth 10, vs. the smaller-scale default of 300/14) rather than left fixed regardless of real
  scale - a real, disclosed tradeoff (printed and saved to the run's own JSON report), never a silent
  degradation.
- Applied in BP2 Notebooks 2 and 3 (2026-09-30, same day as the incident). Every future notebook on this
  platform that builds a composite join/grouping key or fits a RandomForest on a real multi-million-row frame
  must use these same two real fixes.

## 21. Full-graph Louvain community detection is not fast enough at real project scale -- caught BEFORE it reached the user's machine (BP3, 2026-09-30)
Before writing BP3 Notebook 1, Claude ran a real, disclosed feasibility test on the user's own device (not a
report of the notebook's own results -- a design-time diagnostic) against HI-Small_Trans.csv, the SMALLEST real
dataset variant this platform uses. Real, measured findings: building a compact-int-node networkx DiGraph
(515,088 real nodes, 1,015,736 real distinct directed edges) took 3.3s and peaked at 1.5GB RAM; PageRank ran in
2.1s; `nx.connected_components` ran in 1.3s but revealed a real, important structural fact -- one giant
component holds 372,089 of 515,088 nodes (72.3%), so raw connected components are NOT a useful clustering
granularity at this scale (a single blob, not meaningful sub-clusters). `nx.algorithms.community.
louvain_communities` on that same real graph did not finish within a 120-second bound and had to be killed --
on the SMALLEST real variant. LI-Medium (BP3's locked mandatory validation tier) is roughly 60x HI-Small's real
transaction volume, so full-graph Louvain there is not a "maybe slow," it is a real, near-certain repeat of the
Lesson #20 incident class (something that looks fine on paper turning out computationally infeasible at real
project scale) if attempted naively.
STANDING RULE for BP3 (and any future BP that runs graph algorithms): (1) never run community detection or
betweenness centrality over the full bank-wide transaction graph -- scope every such algorithm to a bounded,
disclosed subgraph (e.g. a fixed-hop ego-network around already-flagged accounts, or a per-community subgraph
under an explicit node-count cap), which is also the more realistic real investigative workflow (an analyst
pulls the local network around a flagged account, not the whole bank's graph) and a better real GDPR
data-minimization fit for BP3's own flagged regulatory framework (Section 6); (2) degree (in/out, vectorized
pandas) and PageRank are real, confirmed-fast/safe at this platform's real scale and stay in the toolkit,
still behind `assert_ram_safe()` gates; (3) betweenness centrality is never run on a full graph at all (O(V*E),
excluded by complexity-class reasoning, same caution class as Lesson #20), only ever on a bounded subgraph
already reduced by rule (1); (4) any full-graph algorithm's real feasibility is re-verified with a real,
disclosed, time-boxed test BEFORE it is written into a notebook the user will run, never assumed safe by
analogy to a smaller unrelated dataset.
Applied in BP3 Notebook 1 (2026-09-30). Locked as this BP's own graph-computation-feasibility policy, written
to `configs/bp3_network_graph_intelligence.yaml`.

## Lesson #22: `CalibratedClassifierCV(cv="prefit")` was removed in newer scikit-learn -- caught by
local testing BEFORE it reached a real notebook (BP1 Notebook 3 corrections pass, 2026-09-30)
While adding real isotonic probability calibration to BP1 Notebook 3 (part of a corrections review that also
added PSI production-monitoring, real alert-routing tiers, and fixed a missing `src/services/` scoring-service
file), the originally-written code used `CalibratedClassifierCV(uncalibrated_model, method="isotonic",
cv="prefit")` -- the standard pattern for calibrating an already-fitted model on a held-out split, and the
correct API in older scikit-learn. Tested locally (synthetic, severely-imbalanced data mirroring BP1's real
class imbalance) before shipping into the notebook, per this project's standing practice of testing new risky
logic against synthetic data first. The real result: `sklearn.utils._param_validation.InvalidParameterError:
The 'cv' parameter of CalibratedClassifierCV must be an int ... Got 'prefit' instead` -- confirmed on real
scikit-learn 1.8.0. Newer scikit-learn removed the `cv="prefit"` option entirely; the already-fitted estimator
must instead be wrapped in `sklearn.frozen.FrozenEstimator` before being passed to `CalibratedClassifierCV`.
FIX: try the new `FrozenEstimator` path first, fall back to `cv="prefit"` in an honest `except ImportError`
guard -- the same try-the-newer-thing-first-fall-back-honestly pattern this platform already uses for SHAP/
LIME/graph-library availability checks -- so the notebook works whichever real scikit-learn version the user's
own machine has installed, rather than silently breaking on one of them.
STANDING RULE: any new library-version-sensitive API call (calibration, any other sklearn/lightgbm/xgboost/
catboost API this platform hasn't exercised before) gets a real local test against synthetic data on THIS
session's own Python environment before being written into a notebook, specifically because a real API surface
can differ from what training data suggests is "the standard way" -- caught here before the user ever saw it,
not after a real run failed on their machine.
Applied in BP1 Notebook 3 (2026-09-30), as part of the same corrections pass that added PSI monitoring,
alert-routing tiers, and the missing scoring-service file.

## Lesson #23: BP1 Notebook 3 repeatedly crashed the reference laptop for real -- true root cause was RAM exhaustion (`assert_ram_safe()` existed since Lesson #20 but was never actually called), NOT OS sleep; full checkpoint/resume + a real memory-accumulation bug fixed (2026-10-01)
Real incident, several real runs: BP1 Notebook 3 (Stage A/B model selection on the full LI-Medium split) hung
or crashed the reference laptop multiple times across this session, including one real 8-hour silent hang (0%
CPU, confirmed via Task Manager) that Claude originally misdiagnosed as a Windows-sleep-triggered
joblib/multiprocessing deadlock. The user directly corrected this: sleep prevention had already been enabled
("system will never sleep") well before that hang, ruling the sleep theory out. Re-investigating
`performance_setup.py` for real found the actual gap: `assert_ram_safe()` (the real, ENFORCING gate added at
Lesson #20, 2026-09-30) was never being called anywhere in BP1 Notebook 3 -- only the report-only
`check_ram_headroom()` was in use, the exact same gap Lesson #20 itself was written to close platform-wide.
A second real, confirmed bug compounded it: `stage_a_candidates`, a dict holding all 4 fitted Stage A models
simultaneously with zero downstream read (confirmed via grep), caused available RAM to drop 6.98 -> 6.93 ->
6.87 -> 4.53 GB across just three model fits.

FIXES, all tested locally before shipping, all confirmed by a real, complete, successful LI-Medium run
(champion XGBoost, PR-AUC 0.1242, two-gate verdict PASS):
- `assert_ram_safe()` is now actually called before every heavy fit in BP1 Notebook 3 (3.0 GB bar for
  LightGBM/XGBoost/CatBoost/IsolationForest; 5.0 GB bar for RandomForest, the Stage B 5-fold CV loop, and the
  champion's full-data refit) -- closing the real gap Lesson #20 intended to close platform-wide but this
  notebook had not actually adopted.
- `stage_a_candidates` dict removed entirely; each candidate model is `del`'d and `gc.collect()`'d immediately
  after its PR-AUC is captured, in both the fresh-fit and checkpoint-resume paths.
- Full checkpoint/resume system added (pickle each Stage A candidate's result, each Stage B candidate's 5-fold
  CV result, and the champion's full-data refit the moment it completes; on re-run, an existing checkpoint is
  loaded and that step's real computation is skipped entirely) -- verified via a true two-process (not
  in-process mock) crash/restart simulation before shipping. `RANDOM_FOREST_N_JOBS` capped at 4 (down from
  `-1`) as an additional real memory/time tradeoff lever, disclosed in-line.
- Windows sleep-prevention (`SetThreadExecutionState`, platform-guarded) baked directly into Notebook 3 itself
  as a backup to the OS power setting -- real, but NOT the root cause here; kept because the user's earlier
  "re-run from the top" pain mode (losing 2+ hours of completed Stage A/B work on any interruption) is a
  separate real problem the checkpoint system above actually solves.
- Platform-wide bug found and fixed in the same pass: `src/monitoring/drift_monitor.py`'s
  `save_score_baseline()` saved every raw score with no cap -- a real 174.5 MB file on LI-Medium's ~7.8M-row
  test set. Every future BP imports this exact module, and GitHub refuses files over 100MB without Git LFS
  (not set up here) -- a real platform-wide blocker, not hypothetical. Fixed via `MAX_BASELINE_SAMPLE_SIZE =
  100_000` random subsampling (tested locally first: a 100k-row subsample reproduces full-data PSI within 0.5%
  and the identical verdict band), with the real original row count always recorded alongside the saved count
  so a reader never mistakes the subsample for the full distribution.
- BP1 Notebook 4 corrections review (same day): its own one real memory-heavy step (reloading each variant's
  full raw transaction CSV to recompute the naive "Before" baseline) now calls `assert_ram_safe()` too, same
  4.0 GB bar pattern -- it had the identical gap (a disclosed memory-heavy step with no enforcing gate in
  front of it) even though it never actually crashed.

STANDING RULE, now MANDATORY: adding `assert_ram_safe()` to `performance_setup.py` (Lesson #20) was not
sufficient by itself -- every notebook's own heavy steps must be audited to confirm the gate is actually
CALLED there, not just available in the shared module. When reviewing or writing any notebook on this
platform, explicitly check every step already disclosed (in that notebook's own comments) as memory-heavy
against this question: is `assert_ram_safe()` actually in front of it, or only `check_ram_headroom()` (or
nothing)? A function existing in a shared module is not itself a fix until every real call site adopts it.
Applied in BP1 Notebooks 3 and 4, and `src/monitoring/drift_monitor.py` (2026-10-01). Every future BP's
Notebook 3 (or any notebook with a multi-candidate model-selection stage) must ship with this same
checkpoint/resume + per-candidate-cleanup + `assert_ram_safe()` pattern from the start, not added reactively
after a real crash.

## Lesson #24: BP2 Notebook 3 upgraded proactively with the same checkpoint/resume + sleep-prevention hardening just proven on BP1 Notebook 3 (2026-10-01)
Real review, not a reactive fix: BP2 Notebook 3 never actually crashed, but it has the exact
same real risk shape Lesson #23 just fixed on BP1 -- a multi-candidate Stage A (LightGBM/
XGBoost/CatBoost/RandomForest/IsolationForest, single split) feeding a Stage B 5-fold CV on
the top-2 candidates, on the same real multi-million-row LI-Medium data. BP2 NB3 already had
real, correctly-placed `assert_ram_safe()` gates from the 2026-09-30 incident fix (Lesson
#20) -- that part did not need repeating. What it was missing, audited against Lesson #23's
own new standing rule ("every notebook's heavy steps must be checked for whether the proven
fix is actually there, not just available"): checkpoint/resume and Windows sleep-prevention.
Both added here, before a real crash forced it, using the identical, already-proven helper
functions and control-flow pattern from BP1 Notebook 3 (verified structurally sound locally:
a synthetic round-trip test confirmed the two BP2-specific new pieces -- the Isolation
Forest mean-anomaly-by-class Series, which round-trips through a plain dict since JSON/pickle
both serialize dicts natively, and the champion-refit model object, whose loaded copy was
confirmed to predict bit-for-bit identically to the original fit).
Added: per-candidate checkpointing for all 5 Stage A candidates (LightGBM/XGBoost/CatBoost/
RandomForest/IsolationForest -- metrics only, mirroring BP1's trimmed-payload pattern, except
IsolationForest which saves its per-class anomaly-score dict); per-candidate checkpointing
for Stage B's 5-fold CV loop (with a `continue` early-exit on resume, same as BP1); a
checkpoint around the champion's full-data refit (this one DOES save the real fitted model
object, since SHAP/LIME/test-eval/the final pickle save all need it downstream); Windows
sleep-prevention baked in directly; four STAGE MARKER print boundaries. A real, deliberate
design choice carried over from BP1: the RandomForest/Isolation Forest median-impute step
(`X_train.fillna(median)`) and the champion's `X_train_champ` are always recomputed even on a
checkpoint-resume -- cheap vectorized pandas, and downstream steps (Isolation Forest, LIME)
need those DataFrames to exist regardless of which upstream fit was skipped.
Same review also checked BP2 Notebook 4 (no real heavy step exists there at all -- it reads
only Notebook 3's already-saved JSON, unlike BP1 Notebook 4's raw-CSV reload, so nothing to
add) and Notebook 2 (bounded to the small HI-Small variant only, already has a correctly-
placed `assert_ram_safe()` gate and already clears its own `stage_a_candidates` dict with
`gc.collect()` right after Stage A -- real, bounded risk given the small data size, left
unchanged rather than over-corrected).
STANDING RULE reinforced: when a notebook's own real architecture matches one that already
crashed elsewhere on this platform, apply that proven fix proactively on review, not only
after a real incident repeats it.
Applied in BP2 Notebook 3 (2026-10-01).

## Lesson #25: Shared report_builder.py upgraded platform-wide for "world class" HTML + branded Word/Excel/PPTX (2026-10-01)
User request: "i want pleasent back ground colour and highly animated html reports and other
reports that should be world class." Since report_builder.py is the HYPER-pattern shared
module (built once in BP1 Notebook 4, imported UNCHANGED by every later BP's Notebook 4 --
BP2 and every future BP get this automatically, no per-BP work needed), this was done once
here rather than per notebook.

HTML dashboards (write_html_dashboard + write_html_dashboard_multiclass): added a layered
radial-gradient page background (tinted, not textured -- sits behind solid-surface cards so
text contrast is untouched), an animated shimmering top accent bar, a pulsing status-banner
dot, a JS-computed sliding tab-indicator (offsetLeft/offsetWidth -> CSS transform/width
transition), a fade-in transition on tab-section switch, and a shimmer overlay on progress
bars. Verified with real headless-Chromium (Playwright, /opt/pw-browsers/chromium) against
the real vendored chart.umd.js (not a stub) -- 0 console/page errors, screenshots visually
confirmed, tab-click interaction confirmed working across all 4 tabs on both the binary and
multiclass dashboards.

Word/Excel/PPTX: added a shared branding-helpers block (right after the PALETTE dict) so
every writer function reuses the identical, already-proven-safe technique instead of each
reinventing it: _apply_word_brand_styles() colors the Title/Heading 1/Heading 2 STYLES once
(doc.styles[...].font.color.rgb -- pure public python-docx API, so every doc.add_heading()
call anywhere in the function picks it up for free); _brand_word_table_headers() shades every
table's header row via the standard, widely-documented w:shd OXML snippet (one child
element, no reordering -- this exact technique is in python-docx's own cookbook); on Excel,
_brand_excel_sheet() sets a per-sheet tab color + frozen header row, _band_excel_rows() adds
light alternating-row banding on real data rows only (skips any cell that already carries its
own meaningful fill, e.g. the yellow Assumption highlight), and _color_verdict_cells() applies
real green/red PASS/FAIL fills to the Gate 1/Gate 2/Overall Verdict cells; on PPTX,
_add_branded_slide() wraps prs.slides.add_slide() to also add a full-width accent-color bar
(standard MSO_SHAPE.RECTANGLE + solid fill, no outline/shadow) and a light background tint
(slide.background.fill.solid()) -- applied at all 20 real add_slide() call sites across both
write_pptx_deck() and write_pptx_deck_multiclass() via a scripted regex replace, then verified
by grep that all 20 landed correctly with original indentation intact (including the two
conditional chart-slide call sites).

Explicit, disclosed limitation -- NOT implemented, on purpose: real PowerPoint slide
transitions (p:transition/p:fade). python-pptx has no public API for this; it would require
hand-written raw OOXML with strict element-ordering rules (cSld/clrMapOvr?/transition?/
timing?) that cannot be verified safe from this sandbox -- python-pptx re-opening the file
only proves XML well-formedness, not real-PowerPoint schema validity, and no real PowerPoint
is available here to confirm the file won't trigger a "repair" prompt. Decision: ship a
static, Office-safe accent bar instead of an unverifiable animation, and disclose this
honestly to the user rather than risk a corrupted deliverable.

Testing before delivery: all six writer functions (binary + multiclass x Word/Excel/PPTX)
run against realistic synthetic context fixtures; round-trip re-open checks via python-docx/
openpyxl/python-pptx confirmed on every file (table header shading element present, sheet tab
colors + freeze_panes set correctly, PASS/FAIL verdict cells independently green/red even
within the same row's mixed verdicts, all 10 slides per deck carry the accent bar + background
fill and reopen without error). HTML dashboards separately verified via headless-Chromium
screenshot testing (see above). py_compile clean throughout.

Delivered: updated report_builder.py sent via SendUserFile + device_commit_files, confirmed
on-device (163,644 bytes, fresh mtime, zero rejected entries).

STANDING REMINDER for the user: this module is never executed by Claude against real data
(execution-boundary rule) -- BP1's Notebook 4 and BP2's Notebook 4 must be RE-RUN on the
user's machine to regenerate the five-format report packages in the new branded style. Any
already-generated HTML/Word/Excel/PPTX files currently on disk are still in the OLD style
until that re-run happens. Every future BP (BP3+) picks up this branding automatically the
first time its own Notebook 4 runs, since it imports report_builder.py unchanged.
Applied platform-wide (2026-10-01).

## Lesson #26: BP3 Notebook 3 -- networkx avoided for the full LI-Medium graph; hand-rolled vectorized PageRank + memory-efficient frontier BFS used instead, after a real OOM caught in pre-build testing (2026-10-01)
Context: BP3 Notebook 1's own real pre-build diagnostic (Lesson #21) already found networkx's pure-Python
graph algorithms show real, serious scaling problems even on HI-Small, the smallest real variant (Louvain
did not finish in 120s). Before writing Notebook 3 (BP3's mandatory LI-Medium validation tier -- 31,251,484
real transaction rows, confirmed via a real `wc -l` on the user's device this session), Claude proactively
engineered and REAL-TESTED an alternative to building a full `networkx.DiGraph` at this larger scale, rather
than wait to discover the same class of problem a second time.

Real correctness check (not just asserted): a hand-rolled sparse-matrix power-iteration PageRank
(scipy.sparse + numpy, fully vectorized, no DiGraph object) was verified against `networkx.pagerank()`'s
own reference output on a real local synthetic graph (400 nodes, 2000 edges): max absolute difference
1.45e-06, identical top-5 ranking. This exact check is reproduced live inside Notebook 3 itself (Section 0)
so it re-verifies on every real run, not just trusted from this session's one-off test.

Real scale/memory test, with an honest disclosure of WHERE it ran: NOT a live run against the real
LI-Medium file on the user's own device -- the on-device sandbox this platform's Claude session uses for
file operations has only ~4GB total RAM (confirmed via a real `psutil.virtual_memory()` check this
session), materially less than this platform's real 8-core/16-thread/32GB target machine, so a timing/
memory number measured there would not be representative. Instead the test ran in Claude's own cloud test
environment (~7.8GB RAM) against a synthetic graph matching LI-Medium's real confirmed scale (31,251,484
edges, 2,000,000 nodes). A REAL BUG was caught here: the first version of the 2-hop proximity signal built
a full undirected, deduplicated edge table (`pd.concat` of both directions + `drop_duplicates()`) before
expanding the BFS frontier -- this doubled real edge storage, and the dedup step alone triggered a real,
measured `exit code 137` (OOM-killed) in the 7.8GB test container, after peak RSS had already reached
4.2GB from the earlier PageRank step. Fixed by never materializing the doubled/deduped table: each BFS hop
instead does two small DIRECTED merges against the real edge table (frontier-as-src -> find real dst;
frontier-as-dst -> find real src). Re-tested after the fix: real measured wall-clock ~36s (distinct-edge
aggregation) + ~12s (sparse PageRank) + ~8s (2-hop frontier BFS, 20,000 real seed-equivalent nodes), peak
RSS steady at ~4.2GB -- well inside the real 32GB target ceiling, no further OOM.

STANDING RULE reinforced (extends Lesson #20/#21's own standing rule to graph-structured data
specifically): before committing a new notebook's methodology at a real scale this platform has not yet
proven safe, test the RISKY KERNEL (not just the overall pipeline) against a synthetic graph/array matched
to the real target scale, in whatever test environment is actually large enough to be representative --
disclosing honestly when the normal on-device diagnostic sandbox itself is too small to trust, rather than
either skipping the test or passing off a misleadingly-OOMed small-sandbox result as if it reflected the
real target machine. A "looks vectorized" one-liner (here: `pd.concat` + `drop_duplicates` for an
undirected edge table) can still be the real memory bottleneck, same lesson as Lesson #20's row-wise
`.agg("|".join)` surprise -- vectorized does not automatically mean memory-cheap at scale, and the fix is
always to test it for real before trusting it.
Applied in BP3 Notebook 3 (2026-10-01).

## Lesson #27: report_builder.py STRUCTURAL extension + BP3 Notebook 4 built, tested, delivered (2026-10-01)
BP3 (Transaction Network & Graph Intelligence) has no trained ML model -- its real output is a
champion structural signal (degree/PageRank/network-proximity) selected by real network-lift
ratio with a real bootstrap 95% CI, not a classification metric. The existing report_builder.py
writer functions (binary, from BP1; multiclass, from BP2) both assume a classifier's metrics
(PR-AUC/precision/recall or macro-F1) and could not represent this shape, so a third,
structural writer path was added rather than forcing BP3's real numbers into the wrong
template.

New report_builder.py functions (all reused UNCHANGED: compute_bp_status, write_changelog,
export_pdf_from_docx, every _brand_*/PALETTE helper -- confirmed fully generic already):
build_signal_comparison_table_structural() (real Signal|Threshold|Flagged|Exposed|Rate|Lift
table, sorted by real lift ratio -- the raw stage_results JSON list is NOT pre-sorted),
build_ego_network_illustration_table_structural() (Before: 1-account review vs. After: real
bounded 2-hop ego-network, built strictly from NB3's own 3 real illustrative examples --
explicitly labeled as such, never presented as a population-wide average since that aggregate
was never computed), generate_smart_recommendations_structural() (detects and reports real
champion agreement/divergence between the HI-Small Stage A prior and the LI-Medium mandatory-
tier result -- never silently picks one), render_signal_lift_chart_png_structural() (matplotlib
horizontal bar, champion highlighted in brand blue vs. muted gray for others), and the five
structural writers (write_word_report_structural / write_excel_workbook_structural /
write_html_dashboard_structural / write_pptx_deck_structural / write_rule_card_structural --
the last deliberately named and framed as a RULE CARD, not a model card, since BP3's real
deployable artifact is a threshold/set-membership RULE, never a pickled classifier).

Locked-policy discipline carried through literally: BP3 Notebook 1's own policy states the
Before/After KPI is volume-scale only, "never converted to a dollar figure without a real,
sourced per-account investigation-cost assumption, which does not exist for this BP and is
therefore not invented" -- so NO ASSUMPTIONS dict and NO dollar figure appears anywhere in any
of the 5 structural output formats, unlike BP1/BP2's ASSUMPTION-labeled illustrative $ figures.
The Excel workbook's first sheet is "Parameters & Policy" (real locked methodology constants:
seed, bootstrap resamples, node cap, top-decile percentile) rather than "Assumptions", since
there is no dollar assumption to disclose.

Testing before delivery, two layers: (1) report_builder.py's new functions were called
directly against a synthetic context dict built from the EXACT real schema of the user's own
actual LI-Medium bp3_notebook3_validation_report + champion_rule JSON files (read live off the
user's device via device_bash before building, not guessed) -- all 5 formats + PNG + rule card
generated successfully; round-trip reopened (python-docx/openpyxl/python-pptx) confirmed table
header shading, tab colors, PASS-verdict green cell coloring, 10/10 slides intact; headless-
Chromium (Playwright) confirmed 0 console/page errors and real tab/table/chart rendering on the
HTML dashboard. (2) The full BP3 Notebook 4 orchestration script was run end-to-end in the
sandbox against the earlier synthetic NB2/NB3 outputs already on disk there (full project-root
bootstrap, real file loads, Docker/RULE_CARD/CHANGELOG generation, PDF export) -- zero errors,
all 5 report files + RULE_CARD.md + CHANGELOG.md + Dockerfile produced correctly.

Docker packaging adapted for BP3's RULE artifact (a small JSON file) rather than a pickled
model: COPY instruction references the real champion_rule JSON path, Dockerfile disclosed note
flags that a deployed 2-hop-proximity-type champion would also need the real TRAIN-flagged
seed-account set persisted to disk (NB3 computes it in-kernel but does not currently save it) --
a real gap, honestly flagged rather than silently glossed over, same convention as the
already-disclosed src/services/*_scoring_service.py extraction gap shared with BP1/BP2.

Delivered: report_builder.py (extended, confirmed on-device, 0 rejected) and BP3's
04_compliance_impact_reporting_packaging_SINGLE_CELL.py (confirmed on-device, 0 rejected).
BP3 is now fully complete, Notebooks 1-4, pending the user's own real run.
Applied in BP3 Notebook 4 (2026-10-01).

## Lesson #28 -- Vectorized trailing-time-window features: naive groupby+rolling does not scale, a hand-rolled sort+searchsorted method does (BP4 Notebook 1/2)

BP4's locked feature policy (Section 5 of Notebook 1) requires two real trailing-24h-window
per-account statistics (structuring_window_txn_count, structuring_window_amount_sum). Before
locking a computation method into any notebook, this was feasibility-tested privately (never on
the user's device) at a representative REAL scale -- synthetic data matching LI-Medium's real
row/entity counts (~31M rows, ~2M accounts) -- per the Lesson #21/#26 pre-build-testing
discipline.

Real finding: the naive `pandas groupby('Account').rolling('24h', on='Timestamp')` approach
timed out (>120 real seconds, never completed) at that scale -- this would have been a direct
repeat of the BP1 Notebook 2 v4 rolling-window crash and the BP3 Notebook 3 OOM incident
(Lesson #26), caught here BEFORE it ever reached a notebook or the user's machine.

Fix: a fully vectorized alternative with no per-group Python loop -- global `np.lexsort` by
(account, time), encode each row as a single sortable integer key
(`key = account_id * BIG_OFFSET + time_seconds`), one global `np.searchsorted` call per window
boundary to find each row's window start, and the windowed sum via a single global cumulative-
sum difference. Real-tested at the same 31M-row/2M-account scale: ~29 real seconds, ~3.6GB real
peak RSS (vs. >120s timeout for the naive approach). The generalized helper
(`vectorized_trailing_window_features`) is used in BP4 Notebook 2 and ships with its own real
correctness self-test (brute-force spot-check on 10 random rows) that RAISES rather than
silently shipping a wrong feature if it ever fails.

Secondary finding during correctness testing: the windowed-sum-via-cumsum-difference technique
loses float64 precision (catastrophic cancellation) when the running cumulative total is large
(~1.3e10) relative to the window sum (~538) -- a real, benign ~1e-9 relative-error effect, not a
logic bug. Fix: all correctness self-tests for this technique (both the private validation and
BP4 Notebook 2's own self-test) use a RELATIVE tolerance
(`max(1e-6, 1e-9 * max(abs(brute_force_sum), 1.0))`), never an absolute 1e-6, to avoid a false
failure from this expected effect.

Applied in BP4 Notebook 1 (policy + feasibility test) and Notebook 2 (production use +
correctness self-test) (2026-10-01).

## Lesson #29 -- pandas Series.map() on a 'category'-dtype column can silently return a Categorical, breaking numeric comparisons (BP4 Notebook 2)

While testing BP4 Notebook 2 end-to-end against synthetic fixtures (before delivery -- caught
by Claude's own pre-delivery test run, not by the user), `near_threshold_flag`'s per-currency
TRAIN-fit percentile bounds were looked up via
`df["Payment Currency"].map(train_currency_bounds["low"])`. `Payment Currency` is a real
'category'-dtype column (per the locked TRANS_DTYPES schema, shared with BP1). pandas'
`Categorical.map()` path can return a Categorical result (not a plain float Series) when it
dispatches the lookup internally via `.cat` rather than treating it as a generic Series mapping
-- this is silent; no warning is raised. The very next line then compared that result with
`>=` / `<`, which raised `TypeError: Unordered Categoricals can only compare equality or not`.

Fix: force `.astype("float64")` on the result of any `.map()` call performed on a
category-dtype Series before using it in a numeric comparison, regardless of what dtype the
mapped values "should" be. Generalizes to every other per-category threshold/lookup pattern in
this codebase (BP1/BP2/BP3 do not currently do this exact lookup, but any future BP that maps a
numeric lookup table onto a category-dtype column must apply this fix).

Applied in BP4 Notebook 2 (2026-10-01).

## Lesson #30 -- Same-timestamp ties broke the vectorized trailing-window feature's "exclude current row" logic at real scale (BP4 Notebooks 2 & 3)

Real incident, 2026-10-01: the user's own real HI-Small run of BP4 Notebook 2 (5,078,345 real
rows) hit the notebook's own correctness self-test failing 8/10 real spot-checked rows --
caught by the notebook's own guard, exactly as designed (it raised rather than silently
shipping a wrong feature), but a real bug nonetheless, not a false alarm.

Root cause: `vectorized_trailing_window_features()` (Lesson #28) originally excluded "the
current row" by SORTED-ARRAY POSITION (`row_idx - left_idx`, where `row_idx` is the row's index
within the globally sorted-by-(account,time) array). When multiple real transactions share the
exact same (account, timestamp) -- common at real scale (5M+ rows, minute-granularity
timestamps), vanishingly rare in the small synthetic fixtures used for every earlier test this
session -- `np.lexsort`'s tie-breaking (stable, falls back to original row order) makes that
position-based exclusion ARBITRARY: some same-timestamp sibling rows end up counted in the
window, others don't, depending only on incidental file order, not on anything temporally
meaningful. The self-test's own brute-force comparison used a strict `ts < ts_i` check, which
disagreed with the vectorized method whenever ties existed -- exposing the ambiguity rather than
creating it.

Fix: redefined the window inclusively and deterministically -- every OTHER same-account row
with timestamp in `[t_i - window, t_i]` counts (same-timestamp siblings INCLUDED, since
simultaneous same-account transactions are themselves relevant structuring/smurfing signal, not
noise to exclude), with the current row excluded BY ITS OWN ARRAY POSITION
(`right_idx = searchsorted(key, key, side='right')`, then `(right_idx - left_idx) - 1`), never by
a timestamp comparison that can't distinguish "self" from "a tied sibling". The self-test was
updated to match this exact definition (`mask[i] = False` instead of a strict `<` comparison).
Real-tested (private, before re-shipping) against three cases: a dense-tie stress scenario, an
extreme all-500-rows-identical-timestamp case, and the original no-ties case -- 0 mismatches in
all three, plus 25/25 (up from 10/10) real spot-checks passing on the user's own real HI-Small
file's actual tie pattern.

Secondary, unrelated finding caught while re-testing: `SEARCH_SUBSAMPLE_SIZE = min(1_500_000,
len(X_train))` in Notebook 2's hyperparameter-search step becomes exactly `len(X_train)` whenever
the train set is smaller than the cap, and sklearn's stratified `train_test_split` then raises
(first on a zero-row complementary split, then on a too-small one to stratify). This never
triggers at BP4 NB2's real locked scope (HI-Small only, ~3.8M real train rows, always far above
the cap) but was blocking this notebook's own sandbox testing -- fixed defensively with
`min(1_500_000, int(len(X_train) * 0.9))`, a no-op at real scale. NOTE: BP1 Notebook 2 v6 is
described as using "the same grid shape" for its own hyperparameter search and likely carries
the identical `min(1_500_000, len(X_train))` pattern -- flagged here for a future check, not
fixed now (BP1 was not touched this pass; BP1's own real HI-Small/LI-Medium scale has never
hit this either, same reasoning as BP4).

Both Notebook 2 and Notebook 3 (which share the identical helper function and self-test code)
were fixed together, re-tested clean end-to-end (self-test PASS, two-gate verdict PASS, FastAPI
self-test 0 mismatches, in both the HI-Small and LI-Medium-shaped sandbox runs), and redelivered
to the user's device, confirmed `rejected: []`. The user was told directly to re-download and
re-run Notebook 2 from the top before trusting its real output.

Applied in BP4 Notebook 2 and Notebook 3 (2026-10-01).

## Lesson #31 -- BP4 Notebook 4 built on the EXISTING report_builder.py binary writer path (no extension needed) + disclosed scoring-service extraction gap

BP4 Notebook 4 (Compliance-Impact Reporting & Packaging) closes out BP4, reusing
report_builder.py's existing binary-classification writer functions (write_word_report /
write_excel_workbook / write_html_dashboard / write_pptx_deck / write_model_card) completely
UNCHANGED -- unlike BP3, which needed a new "structural" writer path (Lesson #27), BP4 is a
standard binary classification task shape identical to BP1's, so no report_builder.py extension
was needed at all. Tested end-to-end against the real NB3 validation-report JSON schema this
session's own sandbox run of Notebook 3 produced (both HI-Small and LI-Medium) -- all 5 formats
+ PNG generated, round-trip reopened (python-docx/openpyxl/python-pptx: 68 paragraphs/3 tables,
5 sheets, 10 slides respectively, all readable), headless-Chromium confirmed 0 console/page
errors on the HTML dashboard, MODEL_CARD.md/CHANGELOG.md/Docker packaging/alert-routing
addendum all generated correctly.

Disclosed gap (same honest pattern as BP3 Notebook 4's rule-JSON gap, Lesson #27): Notebook 3
builds and self-tests its real scoring function/FastAPI app IN-KERNEL (score_transaction/app)
but no standalone src/services/bp4_scoring_service.py module has been extracted from it yet,
unlike src/services/bp1_scoring_service.py which already exists -- Notebook 4's Dockerfile
references the expected real path and prints an explicit ACTION NEEDED check confirming the
module is missing, rather than silently assuming it is there or building a Dockerfile that
would fail opaquely.

With this, BP4 (Structuring & Smurfing Detection) is code-complete across all 4 notebooks,
pending the user's own real on-device run of all four in order (NB1 already run for real by the
user; NB2/NB3/NB4 pending their real run following the Lesson #30 tie-handling fix).

Applied in BP4 Notebook 4 (2026-10-01).

---

## Lesson #32: Lesson #30's tie-handling fix was real but NOT the true root cause of the
real self-test failure -- a third, independent bug in the SAME function was. (BP4 NB2/NB3,
2026-10-01)

The user's real HI-Small run (5,078,345 rows, pandas 3.0.6, numpy 2.5.3) re-failed the
`vectorized_trailing_window_features` self-test AFTER the Lesson #30 tie-handling fix
shipped -- now 14/25 mismatches, always count-correct/sum-wrong, always on rows whose TRUE
window sum is exactly 0.0 (the account's first transaction in the lookback window, nothing
to sum). This ruled out tie-handling (already fixed) and, on direct testing, ruled out a
separately-found and separately-real timestamp-resolution bug (pandas 3.x infers
`datetime64[us]` for this dataset, not `[ns]`, so `.astype("int64") // 10**9` silently
divided microseconds by 1e9 -- a real bug, fixed, but proven NOT to explain the self-test
disagreement since both sides of the self-test consume the same (buggy or fixed)
`ts_seconds_arr`).

ROOT CAUSE: the function computed each window's sum via a single GLOBAL `np.cumsum()` over
all n rows, then recovered a window's sum by differencing two cumsum values. At real scale
(millions of rows, a real multi-hundred-billion-dollar cumulative total), float64 addition
rounds at the CURRENT running total's magnitude, not the small local window being recovered
-- so by the time the running sum reaches into the hundreds of billions, each addition's
rounding error already exceeds the self-test's tolerance for a window sum that should be
exactly 0.0. Reproduced directly: a 5,000,000-row/500,000-account synthetic test with a
realistic log-normal amount distribution (sum ~$276B) hit 18/25 self-test mismatches, all
count-correct/sum-wrong, all on empty-window rows -- matching the user's real pattern.

FIX: replaced the global running sum with a PER-ACCOUNT-GROUP running sum
(`pd.Series(amt_s).groupby(pd.Series(acct_s), sort=False).cumsum()`, which restarts its
accumulator at 0 for every new account), bounding float error to a single account's own
magnitude instead of the whole dataset's. A second, subtler bug then surfaced during fixing:
`right_idx` (the position just past a row's own tied siblings) can itself be the first row
of the NEXT account's group when the current row is the last transaction for its own account
-- indexing the per-group array directly at `right_idx` in that case silently reads the next
account's (near-zero) running total instead of this account's. Fixed by reading the
INCLUSIVE per-group cumsum at `right_idx - 1` instead (always still inside this row's own
account group, by construction of the key encoding).

Verified: 0/100 mismatches (fresh random seed) + 0/500 mismatches on a stress test targeting
every account's own LAST transaction specifically (the exact boundary case that broke the
first attempt at this fix) -- both on the 5,000,000-row/500,000-account realistic
reproduction. NB2 and NB3's copies of the function cross-checked to produce byte-identical
output on the same input.

LESSON: when a vectorized aggregate uses cumsum-differencing to recover a small local value
from a large global running total, the float64 error does NOT cancel in the subtraction at
real scale -- the fix is to re-scope the running total to the smallest group the subtraction
is ever taken within (here: per-account, never global), not to loosen the tolerance. Also:
a self-test passing on every synthetic fixture I construct does not rule out a real bug --
my synthetic amount distributions were too small/uniform in magnitude to trigger the float
precision floor this bug lived at; the fix was only found by reproducing the REAL scale
(5M rows) and REAL magnitude (realistic heavy-tailed dollar amounts), not just real row
COUNT.

Applied in BP4 Notebook 2 and Notebook 3 (2026-10-01).

---

## Lesson #33: Standing Lesson #20 RandomForest downsizing rule was never wired into BP4
Notebook 3 -- real RAM gate tripped twice on the real LI-Medium run as a direct result (BP4
NB3, 2026-10-01)

The user's real LI-Medium run (31,251,483 rows) made it through Stage 1 and three of Stage
A's four supervised candidates (LightGBM PR-AUC 0.0038, XGBoost 0.1253, CatBoost 0.1005, all
checkpointed successfully), then tripped the RAM safety gate twice in a row -- first needing
3GB before RandomForest's own fit (failed on the first attempt at 3.39GB available), then
needing 5GB before RandomForest's fit on a retry (failed again at 3.88GB available). Both
trips were the gate correctly doing its job (per the 2026-09-30 incident it exists to
prevent), not a crash -- but the underlying cause was avoidable: this notebook's
RandomForestClassifier was hardcoded at n_estimators=300, max_depth=14 regardless of real
training-set size, even though Lesson #20 (BP2 Notebook 3's real RAM-hang incident) already
established a standing, user-requested, project-wide rule -- downsize to n_estimators=120,
max_depth=10 for any real training set over 5,000,000 rows -- "to be applied to every future
notebook on this project." It was simply never wired into BP4 Notebook 3's two RandomForest
call sites (Stage A's own fit, and the champion-refit candidate-rebuild function). At
LI-Medium's real 23,438,612-row training set (4.7x the 5M threshold), the full 300-tree/
depth-14 forest was both Stage A's heaviest candidate by far and the one most likely to tip
the gate.

FIX: computed RF_N_ESTIMATORS/RF_MAX_DEPTH once, from this run's real len(X_train), applying
the exact Lesson #20 threshold (120/10 above 5M rows, 300/14 at or below), and reused the
same two variables at both RandomForest call sites so they can never drift apart again. Also
added a secondary WARP memory-discipline fix found while fixing this: the two full-size
median-imputed DataFrame copies RandomForest and Isolation Forest need (X_train_rf,
X_test_rf) were being built unconditionally even when both candidates were already resumed
from checkpoint (meaning nothing would read them) -- now only built when at least one of the
two will actually use them, guarded by the same `_ckpt_exists()` checks already used for
resume logic.

LESSON: a standing project-wide rule established after a real incident needs to be checked
against EVERY new notebook's actual code, not assumed to have been inherited just because it
was "applied to every future notebook" in principle -- a hardcoded literal (300, 14) sitting
right next to a correctly-firing safety gate is easy to miss when the gate itself is doing
its job and the notebook LOOKS like it's handling memory responsibly (it has the gate, the
checkpoint/resume system, the thermal sleeps -- just not this one specific parameter).

Applied in BP4 Notebook 3 (both the primary file and its NB3b / _v2 twin).

---

## Lesson #34: Real memory leak -- the pre-split X/y DataFrame (~5.4GB at LI-Medium scale)
was never freed after train/test split (BP4 Notebook 3, 2026-10-01)

Third real RAM-gate trip in a row on the user's real LI-Medium run -- but this time with a
HEALTHY 20.09GB free at kernel startup, ruling out "low external headroom" (the cause of the
first two trips) and pointing to a real leak inside this notebook's own pipeline. Found: the
"build X/y matrices" step does `X_train, X_test = X.loc[is_train], X.loc[~is_train]` --
boolean `.loc[...]` indexing on a pandas DataFrame always returns a NEW COPY, never a view --
so the full, un-split 31,251,483-row `X` (and the much smaller `y`) stayed alive in memory for
the rest of the notebook, duplicating most of X_train+X_test's combined ~5.4GB footprint for
zero benefit (confirmed via grep: neither bare `X` nor bare `y` is referenced anywhere after
the split). This sat on top of the already-checkpointed LightGBM/XGBoost/CatBoost models
loaded back into memory and the X_train_rf/X_test_rf imputed copies RandomForest needs --
between all of it, available RAM dropped from a healthy 20GB to 3.74GB by the time
RandomForest's fit needed 5GB, even with Lesson #33's RF downsizing already in place.

FIX: `del X, y; gc.collect()` immediately after the split, plus a `_print_resource()` call
right after so the recovered memory is visible in the real run's own printed output, not just
asserted.

LESSON: Lessons #32 and #33 were both real, correctly-diagnosed fixes for their own specific
causes (a float-precision bug, a missing downsizing rule) -- but a RAM gate tripping three
times in a row on the same notebook, even after two real fixes, should have prompted a
systematic audit of every DataFrame this notebook's Stage 1 creates and whether each one is
actually freed when no longer needed, rather than treating each trip as its own isolated
incident. `.loc[boolean_mask]` always copying (never viewing) is a easy-to-miss pandas
behavior worth specifically checking for in any notebook that splits a large frame this way.

Applied in BP4 Notebook 3 (both the primary file and its NB3b / _v2 twin).

## Lesson #35 (2026-10-01) -- RAM gate checked AFTER the risky allocation it was meant to guard, not before (BP4 NB3/NB3b)

**Symptom (real, user's own LI-Medium runs):** the RAM safety gate kept tripping at
"before Stage A: RandomForest fit" even after Lesson #33 (RandomForest downsizing) and
Lesson #34 (pre-split X/y leak) were fixed and confirmed -- and real available-RAM
headroom at the crash point got WORSE across successive retries (3.74GB -> 3.88GB ->
2.29GB), not better, despite real, independently-verified fixes landing in between.

**Root cause (confirmed by direct code audit, not a guess):** two places in NB3 built a
full `X_train.copy()`/`X_test.copy()` (to median-impute one column for RandomForest/
IsolationForest, which has no native NaN support) *before* the `assert_ram_safe()` gate
that was supposed to protect exactly this risk -- not after. On LI-Medium's real
~23-25M-row train split, each of these copies is itself a multi-GB allocation (confirmed
via pandas' own `memory_usage(deep=True)`, not estimated). So every observed crash was
the gate correctly firing on a memory state that its own protected step had *already*
degraded by the time the check ran -- and because the exception aborts the cell with
`X_train_rf`/`X_test_rf` (or `X_train_champ`/`X_test_champ`) still bound by name, a
reused kernel (cell re-run instead of a true kernel restart) carries that already-bloated
state into the next attempt, compounding run over run. This is why headroom kept getting
worse, not better, despite three real, separately-confirmed logical fixes elsewhere.

**Fix (both occurrences, Stage A RandomForest/IsolationForest block and the
champion-refit block):** moved `assert_ram_safe()` to run BEFORE the copy-build, gated on
the REAL measured cost of the copy (`X_train.memory_usage(deep=True).sum() + X_test...`,
never a guessed constant) plus a fit-time buffer, so the gate protects the actual risky
step instead of checking after it already happened.

**Secondary hardenings added alongside the real fix:**
- A startup diagnostic prints this process's own RSS before Stage 1 loads anything (a
  fresh kernel is normally well under 0.3GB here); if it's high, prints an explicit
  warning that this is likely a reused kernel still holding objects from an earlier
  crashed attempt, and recommends a true Kernel -> Restart.
- Stage 1 (CSV load + feature engineering + train/test split, ~4 real minutes,
  previously uncheckpointed) is now checkpointed, so a true kernel restart -- now cheap
  to recommend given the diagnostic above -- resumes in seconds instead of ~4 minutes.

**Applies to:** BP4 Notebook 3 (`03_statistical_validation_deployment_SINGLE_CELL.py`)
and its NB3b duplicate (`_v2.py`). Both delivered and committed 2026-10-01, verified via
py_compile + ast.parse + line-by-line diff against the pre-fix file (0 mismatches).
**Not yet confirmed** against a real re-run on the user's machine -- next LI-Medium run
is the real test.

**General pattern to check on every future RAM-gated notebook:** a safety gate placed
immediately before the *named* heavy step (a `.fit()` call) is not automatically placed
before every expensive allocation feeding that step -- an imputed/transformed copy built
to prepare the input for that step is itself worth gating on, separately, using the
input's real measured size rather than assuming the gate before the fit covers it.

## Lesson #35 REVISION (2026-10-01) -- merged a better copy technique from a second-opinion review

User ran a second LLM against the Lesson #35 fix above and pasted back its output for review.
Audited it line-by-line (diffed against the delivered file, not read in isolation) and found:

**Adopted (real improvement, verified before adopting):** replaced the full `X_train.copy()`/
`X_test.copy()` in the Stage A RandomForest/IsolationForest block and in `_X_for()` with
`frame.copy(deep=False)` + a full top-level column reassignment. Verified directly against
this project's real pandas 3.0.2 (not assumed): this pattern never mutates the source frame
(confirmed empirically -- source frame's NaN values stay intact after the "copy's" column is
imputed) and leaves every untouched column genuinely sharing memory with the source, not
duplicated (confirmed via `np.shares_memory`). Net effect: the imputed-copy build now costs
roughly ONE float64 column's real memory instead of a full duplicate of X_train/X_test --
strictly better than gating on the real cost of a full copy (the original Lesson #35 fix),
since it avoids needing that memory at all rather than just checking for it first.

**Rejected (unjustified, reverted):** the same review also dropped several RAM-gate floors
that protect the actual model *fits* (not the copy) from their real, historically-used values
down to smaller guessed ones -- RandomForest fit 5.0GB -> 2.0GB, Isolation Forest fit (was
already an explicit 5.0 in this project's practice) -> 2.0GB, Stage B 5-fold CV 5.0GB ->
3.0GB, champion-refit 5.0GB -> 3.0GB. None of these reductions follow from the copy-technique
change (the copy and the fit are different memory costs), and every real crash this project
has traced back so far had a different, specific root cause -- never "the gate was too
conservative" -- so there is no real evidence a smaller floor is safe. Reverted all four back
to 5.0GB (explicit, not relying on the function's 3.0 default) pending real confirmation.

**Net result delivered:** the lower real memory cost of the shallow-copy technique, combined
with the full, historically-proven 5.0GB floors on every heavy fit. Applied to both NB3 and
NB3b, redelivered and confirmed on-device (`rejected: []`).

**Standing takeaway for this project:** a second opinion from another LLM is worth reviewing
on its merits (diffed line-by-line against the real delivered file, each change checked
independently -- including empirically verifying a claimed-safe pandas pattern against the
project's own real pandas version before trusting it) rather than accepted wholesale or
dismissed outright. Good ideas get merged in; unjustified parameter changes get flagged and
reverted, with the reasoning written down so it doesn't need re-litigating next time.

## Lesson #35 REVISION #2 (2026-10-01): threading-backend merge from a third reviewed version; two other changes explicitly rejected

User pasted a THIRD version of BP4 Notebook 3 claiming it was "the one I reran and got the
full results" from another LLM. Verified via on-device forensics (md5sum of the notebook
folder, `ls -la --time-style=full-iso` on the checkpoint directory, and a re-read of the
LI-Medium validation report's content and mtime) that this third version had NEVER actually
executed on this machine -- every checksum, checkpoint timestamp, and reported metric
(RandomForest PR-AUC 0.0767294309951752 in particular, consistent with a full-data fit) was
identical before and after the user's claim. The user was told this directly, with the
specific evidence, rather than the claim being accepted at face value.

Three distinct changes in that pasted version were evaluated independently on their own
merits, not accepted or rejected as a bundle:

**Rejected:** moving `sklearn.metrics`/`sklearn.model_selection`/`sklearn.ensemble` imports to
the top of the file, before `configure_performance()` runs. This directly violates this
project's own locked Lesson #5 (numpy/pandas/scikit-learn/xgboost/lightgbm/catboost must never
be imported before `configure_performance()` sets thread-count env vars). Not adopted --
original import locations preserved.

**Rejected, per the user's own explicit choice:** `max_samples=200_000` subsampling cap on
RandomForest's training data when `len(X_train) > 5_000_000`. This would make Stage A's
RandomForest-vs-boosted-tree comparison uneven (RF trained on 200K rows vs. XGBoost/CatBoost/
LightGBM on the full ~23M), and -- because Stage A's RandomForest checkpoint already existed
on disk from the earlier, pre-subsampling, full-data run -- would never actually have been
exercised by a real re-run anyway (checkpoints are keyed by dataset variant, not by which code
built them). Presented to the user as an explicit decision via a direct question rather than
decided unilaterally; user chose "Drop it, keep full-data RF." No subsampling in the final
file; RandomForest continues training on the full dataset for every variant.

**Adopted, after independent verification of the mechanism:** wrapping every RandomForest and
IsolationForest `.fit()`/`.predict_proba()`/`.decision_function()` call in
`with joblib.parallel_backend("threading"):`, combined with raising `RANDOM_FOREST_N_JOBS`
from the hardcoded `2` (a defensive cap shipped during the Lesson #34/#35 RAM-gate
investigation) to `perf_config["threads_configured"]` (the already-computed WARP ~92%-of-
logical-cores value). Reasoning verified independently before adopting: joblib's default
"loky" backend parallelizes across worker PROCESSES, each of which gets its own copy of the
input data -- this is exactly the memory-multiplication risk that motivated capping n_jobs to
2 in the first place. The "threading" backend instead parallelizes across worker THREADS
within the same process, which share memory rather than duplicating it, and scikit-learn's
tree-building code is Cython that releases the GIL during the heavy numeric work, so real
parallel speedup still occurs. This lets n_jobs rise back to the WARP-configured thread count
without reintroducing the per-worker memory duplication Lesson #35 originally guarded against.
Applied at all five RandomForest/IsolationForest fit call sites: Stage A RandomForest fit,
Stage A IsolationForest fit, Stage B 5-fold CV loop (generic across whichever candidate is
being cross-validated), champion-refit, and the isotonic-calibration refit.

Applied to both NB3 and NB3b/_v2 (byte-identical, md5 verified), redelivered and confirmed
on-device (`rejected: []`).

**Standing takeaway reinforced:** the same discipline applied in the original Lesson #35
REVISION continues to hold even when the user's own belief about which version produced a
result turns out to be mistaken -- on-device checksums/timestamps/report content are the
ground truth, checked directly, never assumed from either my own prior delivery or the user's
own claim about what they ran.

## Lesson #36 (2026-10-01): report_builder.py HTML dashboard -- visibly distinct backgrounds, stronger slicer/filter animations, and a real pre-existing tab-indicator bug fixed

User feedback on the shared HTML dashboard (used by every BP's Notebook 4, HYPER pattern):
the page read as flat white with no visible structure, and the dataset-variant slicer /
view-tab filters felt plain. Two real issues, fixed together:

**1. Page vs. card backgrounds were visually indistinguishable.** `PALETTE["page"]`
(`#f9f9f7`) and `PALETTE["surface"]` (`#fcfcfb`) differed by about 1% lightness -- on a real
monitor this reads as a single flat white, which is why every card (`.tile`, `.narrative`,
`.rec-card`, header, tabs/filters bar -- all styled with `background:var(--surface)`)
appeared to float on a white page with no visible separation. Fixed by widening the gap to
two clearly distinct tones: `page` -> `#e9ebee` (light grey, the page plane) and `surface`
-> `#fbfaf7` (off-white, every card/text-block surface). Single edit point in the shared
`PALETTE` dict -- applies automatically to all three HTML report templates (binary,
multiclass, structural) and the Matplotlib chart face/figure colors, since they all read
from the same dict.

**2. Slicer/filter animation upgrade.** The dataset-variant filter buttons previously only
changed background color and lifted 1px on hover -- functional but minimal. Added: a
click-triggered ripple effect (an expanding/fading circle spawned at the real click
coordinates, self-removing via its own `animationend` event, `pointer-events:none` so it
never blocks a second click), a spring/overshoot "pop" animation on the button that becomes
active (`cubic-bezier(.34,1.56,.64,1)`, the same bounce-ease used throughout for a
consistent feel), a real box-shadow lift on hover (matching the tiles' existing hover
treatment, not just a bare 1px translate), and a stronger active-state shadow. The view-tabs'
sliding underline indicator got the same bounce easing, a 2-stop gradient fill, a soft glow
shadow, and a background highlight on hover.

**3. Real pre-existing bug found and fixed: the MULTICLASS report template's tab-indicator
was never wired up.** All three HTML templates (binary/multiclass/structural) ship the same
`<span class="tab-indicator" id="tabIndicator">` markup and CSS, but only two of the three
(binary, structural) actually had the JS that measures the clicked tab button and moves the
indicator under it (`moveTabIndicator()`, called on click, on window resize, and once on
load via `requestAnimationFrame`). The multiclass template's script never defined or called
this function at all -- the indicator element existed but sat at `width:0` forever,
invisible, on every multiclass dashboard this project has ever generated. Fixed by copying
the exact, already-working wiring from the binary/structural templates into the multiclass
one. Caught by diffing the three templates' JS side by side while making the animation
pass, not by the user reporting a visible break -- a genuinely silent bug (a missing
`width:0` -> some-px transition doesn't throw, it just never visibly happens).

**Verification (both a full-pipeline render and an isolated unit check, real headless
Chromium, 0 console/page errors either way):**
- Rendered the real binary-dashboard template end-to-end with the project's own real,
  already-confirmed BP4 HI-Small/LI-Medium Notebook-3 metrics (champion/PR-AUC/precision/
  recall/threshold/verdict -- the financial-impact "before/after" inputs were clearly-labeled
  placeholders for this rendering test only, never presented as findings). Screenshotted the
  overview tab, clicked to the Model Performance tab (confirmed the indicator visibly slides
  under it), and clicked a dataset-variant filter button -- 0 console errors throughout.
- For the multiclass fix specifically: extracted the EXACT shipped JS snippet (not a
  rewritten approximation) into an isolated DOM harness replicating the real tabs/filters/
  ripple markup and CSS, and drove it with Playwright. Confirmed: indicator width is real
  (not 0/empty) immediately after load, `transform:translateX(...)` updates correctly after
  a tab click, the clicked view-section gets `.active` and the previous one loses it, a
  ripple span is spawned on click and removes itself via its own animation (not a leak that
  would eventually block clicks), and a filter-button click both calls `render()` and
  updates the `.active` class correctly. 0 console/page errors.

Applied to the single shared `src/reporting/report_builder.py` (one file, all BPs), confirmed
on-device (`rejected: []`). Per the standing rule from Lesson #25 (the prior "world class"
pass): the user must re-run each BP's own Notebook 4 to regenerate that BP's report package
with this styling -- a notebook that already ran before this fix is holding an HTML file
generated by the OLD report_builder.py and will not pick this up until re-run.

---

## Lesson #37 (2026-10-01/02) -- BP5 cross-border country-tagging methodology (real,
verified-before-lock decision, not a bug fix)

**Context:** BP5 (Correspondent Banking & Cross-Border Wire Risk) needs a sender/receiver
COUNTRY for every transaction, but the raw dataset carries no country column at all -- only
`From Bank`/`To Bank` integer IDs and a `Bank Name` string per account. Before writing any
notebook code, the real on-device `accounts.csv` files for HI-Small, LI-Small, and LI-Medium
were inspected directly (via `device_bash` grep/awk against the real files, not assumed or
fabricated) to check whether Bank Name carries a usable, honest country signal.

**Real finding (verified, not guessed):** some real Bank Names follow the exact literal
pattern `"{Country} Bank #{integer}"` (real observed examples: `"Spain Bank #16393"`,
`"Canada Bank #2827"`, `"Saudi Arabia Bank #0"`, `"UK Bank #1"`) with zero exceptions found
across all three inspected files; every other real Bank Name (e.g. `"Bank of New Orleans"`,
`"The Pine Bancorp"`) carries no country prefix -- domestic/US-style naming. Exactly 65
distinct Bank-Name first-tokens exist across all three variants (identical set), of which 32
are real country names (31 single-word + the one two-word exception, "Saudi Arabia") and 33
are generic domestic bank-naming words (Bank, First, Capital, Savings, City, The, National,
Acme, and 24 more invented-brand words). Bank ID -> Bank Name is a verified clean 1:1
mapping -- safe to use as a lookup table.

**Design decision (locked in BP5 Notebook 1, Section 5-7):** `COMMON_COUNTRY_NAMES` is a
REAL, EXTERNAL, objective reference list of ~150+ common English country names (not derived
from or fitted to this dataset), used with a longest-match-first regex
(`^({Country})\s+Bank\s+#\d+$`) to tag each Bank Name as foreign (with its real country) or
domestic -- cross-checked against the dataset's own live-observed 65-token prefix set before
being locked, so the reference list is neither fabricated nor silently wrong for this data.
`sender_country`/`receiver_country` derive from this tag; `is_cross_border`,
`sender_is_foreign`, `receiver_is_foreign`, `foreign_to_foreign` are deterministic booleans
built from it; `sender_country_empirical_risk`/`receiver_country_empirical_risk` are a
Laplace-smoothed (pseudo_count=20) empirical rate of `Is Laundering` by country, fit on
TRAIN rows only (leakage discipline, Lesson #11) -- explicitly disclosed throughout as a
DATA-DRIVEN PROXY computed from this synthetic dataset's own label, never presented as a
real-world OFAC/sanctions score. OFAC sanctions-list screening itself is explicitly flagged
"Not Possible -- Data Limitation" in Notebook 1's regulatory-framing section rather than
silently attempted or silently skipped.

**Why this is filed as a lesson, not just a feature:** this is the first BP on this project
where a core feature set had to be DERIVED from a string-parsing heuristic rather than read
directly from a structured column, so the verify-against-real-data-before-locking discipline
(inspect the real file first, check for a clean 1:1 mapping, cross-check the external
reference list against the data's own observed tokens, explicitly disclose what the feature
is and is not measuring) is recorded here as the reusable pattern for any future BP that
needs to derive a feature from an unstructured name/description field.

**Delivery:** BP5 Notebooks 1-3 (Business Understanding & Policy, Feature Engineering &
Modeling, Statistical Validation & Deployment) built by mirroring BP4's fully lesson-hardened
Notebook 1-3 structure (checkpoint/resume, RAM-safety gates, threading-backend fits,
two-gate verdict, FastAPI self-test, etc. -- all carried through unchanged) with BP5's own
27-column feature set (BP1's 19 + these 8 cross-border features) substituted in. Delivered
to `notebooks/bp5_correspondent_banking_crossborder_risk/`, confirmed via on-device md5sum
match (no OneDrive sync-conflict this time, unlike the report_builder.py incident -- Lesson
#36). Notebook 4 intentionally NOT built yet: it hard-depends on Notebook 3's real saved
validation-report JSON, which does not exist until the user runs Notebook 3 for real on
their own machine (same standing rule as BP1-4).

**Pending platform-wide deliverable (user request, 2026-10-02):** once every BP (1-8) has
real, user-run Notebook 3/4 results recorded, a final `00_EXECUTIVE_ROLLUP_SUMMARY_REPORT`
notebook/report will be built, comprehending all BPs' real validated metrics, gates, and
business framing into one master executive report (same `report_builder.py` HYPER pattern).
Not built yet -- cannot be, under the zero-fabrication rule, until there is real data from
every BP to roll up. Logged here so it is not lost.

---

## Lesson #38 (2026-10-02) -- Overnight production-hardening pass, BP1-BP4 ("Global Standard" /
AMEX Phase-2-hardening pattern, run while the user slept)

**Scope:** closed the governance/deployment gap between "notebooks complete and validated" and
"actually production-packaged", for BP1-BP4, mirroring the AMEX RiskIQ platform's own Phase 2
hardening pass (the closest real precedent on record -- no dedicated Customer360 Navigator
hardening log exists in memory to check against, honestly noted rather than assumed).

**Root-level governance added (shared across all BPs, HYPER "build once" pattern):**
`BENCHMARKS.md` (consolidated real baseline-vs-model numbers for BP1/BP2/BP3/BP4, every figure
copied verbatim from that BP's own real MODEL_CARD.md/RULE_CARD.md, grep-verified, zero new
computation), `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`,
`.github/workflows/code-quality.yml` (bandit, blocking on Medium+), `.github/ISSUE_TEMPLATE/`
(bug_report, feature_request, model_improvement), `.github/PULL_REQUEST_TEMPLATE.md` -- all
previously locked in `master-execution-plan.md` Section 11 but never actually built until
tonight.

**Real, confirmed bug found and fixed, platform-wide (all 4 BPs, identical root cause):** every
BP's `src/docker/<bp>/docker-compose.yml` had `build.context: ../../../..` -- one level too high.
Verified via `realpath --relative-to` from each compose file's own directory that the correct
repo-root-relative path is `../../..` (3 levels, not 4). Left as-is, `docker-compose build` would
have resolved its context to the PARENT of the project folder (the Documents/ folder itself),
where none of the Dockerfile's COPY targets (`requirements.txt`, `src/`, `models/...`) exist --
a real, silent future failure that had never been hit only because no real `docker-compose build`
had been run yet. Fixed in all 4 BPs in one pass (same copy-paste origin, same fix).

**Deployable scoring services -- the actual centerpiece of this pass:**
- **BP1**: `src/services/bp1_scoring_service.py` already existed and was already correct --
  reviewed, not rebuilt. Added its first real structural/wiring pytest suite (5 tests).
- **BP4**: built `src/services/bp4_scoring_service.py` from scratch, closing a gap flagged
  since BP4's own Notebook 4 run. BP4's real validation report JSON already carried
  `champion_needs_rf_impute`/`rf_impute_value` (no notebook patch needed) -- confirmed the
  service's conditional RandomForest-impute branch exactly mirrors Notebook 3's own real
  `score_transaction` logic (verified by reading that notebook directly). 8/8 real tests pass.
- **BP2**: built `src/services/bp2_scoring_service.py`. Real investigation found BP2's
  RandomForest champion DOES have one real NaN-prone column (`amount_paid_received_ratio`,
  undefined when `Amount Received == 0`, Lesson #7 disclosed-undefined-case discipline) with
  NO impute value previously persisted anywhere. PATCHED BP2's real Notebook 3 (additive only --
  reused the already-computed `_train_median_full` Series, added zero new computation) to persist
  `champion_needs_rf_impute`/`rf_impute_value` into its validation report JSON, reusing BP4's own
  key-naming convention for platform consistency. **This means BP2's Notebook 3 (LI-Medium) needs
  one real re-run by the user before the new keys actually exist in a fresh report JSON** -- same
  standing pattern as every other notebook-dependency in this project, disclosed, not worked
  around. Multi-class output required a different response shape than BP1/BP4 (`predicted_typology`
  via the real label encoder's `inverse_transform` + full `class_probabilities`, no single
  threshold, since macro-F1/argmax has no decision threshold). 8/8 real tests pass.
- **BP3**: built `src/services/bp3_rule_scoring_service.py` -- architecturally the hardest of
  the four, since BP3 has no trained model, only a graph-structural RULE. Real investigation of
  Notebook 3's own already-proven-correct in-kernel FastAPI self-test found it round-trips an
  ALREADY-COMPUTED per-row boolean (`near_train_flagged`), never a live graph lookup -- the real
  underlying artifact is `near_flagged_ids` (a Python set of node IDs from a full-graph 2-hop
  BFS, Lesson #26's `vectorized_frontier_bfs`), applied only to the TEST split and never
  persisted to disk. PATCHED BP3's real Notebook 3 (additive only -- same existing `.isin()` call,
  scope extended from the TEST subset to the full node population it was already defined over) to
  persist a `node_key -> near_train_flagged` lookup table as a new Parquet artifact. **BP3's
  Notebook 3 (LI-Medium) also needs one real re-run before this lookup file exists.** The service
  honestly reports `"account_not_in_graph_as_of_last_run"` with `near_train_flagged: null` for any
  queried account key not present in the persisted lookup, rather than fabricating a flag for an
  account outside the known data. 7/7 real tests pass.

**Testing discipline applied (new pattern for this project, worth keeping):** every new/reviewed
service got a REAL, REAL-EXECUTED pytest suite (28/28 passing across all 4 BPs combined, re-run
twice for stability) built entirely against a synthetic stub classifier/label-encoder/lookup table
constructed in a pytest fixture -- never against the real trained model, real label encoder, or
real dataset, consistent with the standing execution-boundary rule (Claude writes and statically
verifies code; real business numbers only ever come from the user's own real notebook runs). This
is the first time this project's `tests/` folders hold real, executable content rather than just a
README placeholder -- `pip install pytest` was needed on-device (now installed).

**Bandit security scan (`.github/workflows/code-quality.yml`'s new blocking gate):** found 4 real
Medium-severity `B301` findings, all `pickle.load()` calls on this project's own trained-model
artifacts (bp1/bp2 x2/bp4 services) -- a standard, low-risk pattern for ML-serving code (loading a
path resolved via this project's own PROJECT_ROOT/env-var convention, never external untrusted
input), silenced with a one-line `# nosec B301` justification comment at each site, matching the
AMEX platform's own precedent of reaching "0 blocking findings" this same way rather than by
avoiding pickle (not a realistic option for a scikit-learn/XGBoost-style model artifact). 6
pre-existing Low-severity findings (subprocess/pickle import notices in `report_builder.py` /
`performance_setup.py`) are below this gate's blocking threshold and were left as advisory,
consistent with AMEX's own non-blocking-style-only scoping decision.

**Honest limitation of this whole pass:** real `docker build`/`docker-compose build` could not be
executed in this session (no Docker daemon/registry access in this sandbox, same constraint AMEX's
own hardening pass hit) -- verified instead via the same static method AMEX used (COPY-path /
build-context resolution check against the real on-device file tree), not a real build. The two
notebook patches (BP2, BP3) are real code, verified via `py_compile`, but their new persisted
artifacts do not exist on disk yet -- both need exactly one real Notebook 3 re-run (LI-Medium)
before their respective new service can actually start against real data.

## Lesson #39 (2026-10-02) -- BP5 real Bank-ID join bug: leading-zero string mismatch, not a coverage gap

**What happened:** User ran BP5 Notebook 1 (real) and got `nan%` cross-border-vs-domestic lift and
`[DISCLOSED GAP]` showing 100% of (sender+receiver) bank-ID lookups unmapped on both HI-Small and
LI-Small. Notebook 2's real run then showed all 8 new cross-border features at exactly **0** feature
importance -- not low, zero. Both numbers were correctly and honestly printed by the notebooks (no
fabrication), but the underlying feature set was fully non-functional.

**Root cause (confirmed by direct inspection of the real raw CSVs on-device, not guessed):**
`HI-Small_Trans.csv`'s `From Bank`/`To Bank` columns store real bank IDs with inconsistent
leading-zero padding (e.g. real observed `"0322605"`, `"034418"`), while `HI-Small_accounts.csv`'s
`Bank ID` column stores the identical underlying IDs unpadded (e.g. `"331579"`, `"210"`). Both are
loaded as pandas `"string"` dtype per this BP's own `TRANS_DTYPES`/`ACCOUNTS_DTYPES` dicts, so
`"010" != "10"` as strings -- every `.map()` lookup from transactions onto the accounts-derived
country-tag table failed end to end. Verified numerically: casting both sides to `int64` on the real
HI-Small files produces a perfect 30,470-way Bank-ID overlap -- this was never a real coverage gap
(the two files genuinely describe the same bank-ID space), only a string-representation mismatch.

**Why the self-test didn't catch it:** Notebook 2/3's in-kernel brute-force self-test
(`name_lookup.get(row["From Bank"])`) uses the exact same unconverted bank-ID join key as the
vectorized `.map()` path it's meant to cross-check -- both paths shared the identical root cause, so
they agreed with each other while both were wrong. A redundancy check only catches divergent bugs,
not a bug baked into the shared input both paths consume.

**Secondary finding (contributing factor, not independently a bug):**
`src/utils/performance_setup.py`'s `load_csv_cached()` ignores the `dtype` kwarg entirely on a cache
hit (`pd.read_parquet(cache_path)` with no re-cast) -- meaning a dtype fix applied only to the
`TRANS_DTYPES`/`ACCOUNTS_DTYPES` dicts would silently NOT take effect against an existing Parquet
cache from an earlier run. The fix below re-casts explicitly after the `load_csv_cached()` call
returns, so it holds regardless of cache state.

**Fix applied (additive, all three BP5 notebooks -- each carries its own self-contained copy of this
join per the platform's per-notebook independence convention):** immediately after loading the
Trans and accounts dataframes, explicitly re-cast `From Bank`/`To Bank`/`Bank ID` to `int64` before
any `.map()`/lookup is built. No other code changed -- `is_self_transaction`/`is_cross_bank`
(`From Bank == To Bank`, same file, same cast) are unaffected since both sides of those comparisons
get the identical cast.

**User impact:** BP5 Notebooks 1 and 2 need a fresh real re-run (HI-Small/LI-Small for NB1,
HI-Small for NB2) before the cross-border features carry any real signal. NB3 (not yet run by the
user) already carries the fix.

**Standing takeaway for any future notebook that joins two independently-sourced real files on an
ID column:** never assume a shared "same dtype" declaration means the same *representation* --
explicitly normalize (int cast, zfill, or strip) and verify non-trivial overlap count before trusting
a `.map()`/merge result, especially when a brute-force "independent" self-test reuses the same raw
join key as the thing it's checking.

## Lesson #40 (2026-10-02) -- BP5 Notebook 4 built; real delivery-tool pitfall caught (stagedPath vs fileUuid commit)

BP5 Notebook 4 (Compliance Impact & Reporting Packaging, 603 lines) built from both of Notebook 3's
real, confirmed validation reports (HI-Small: champion XGBoost, test PR-AUC 0.4306, 422x lift,
Gate1/Gate2/Overall PASS; LI-Medium: champion XGBoost, test PR-AUC 0.1399, 272.5x lift, PASS) --
reuses the shared `src/reporting/report_builder.py` binary writer path (write_word_report,
write_excel_workbook, write_html_dashboard, write_pptx_deck, write_model_card, write_changelog)
unchanged, same as BP1/BP4. Confirmed before writing any path into the notebook: the real on-disk
`bp5_hi_small_model_v1.pkl`/`bp5_li_medium_model_v1.pkl` ARE Notebook 3's XGBoost champions (NB3's
own save code overwrites whatever NB2 left there) -- NOT assumed. OFAC sanctions-screening
"Not Possible - Data Limitation" disclosed in three places (caveats, dedicated OFAC_NOTE, alert-
routing addendum), never silently implied as done. Port 8002 assigned for bp5_scoring_service.py
(not yet built -- disclosed as a gap) since 8000/8001/8003 are already taken and BP4's Dockerfile
already has an undisclosed collision with BP2 on 8001 (noted in-code, not fixed here -- out of
scope for this notebook).

REAL TOOLING PITFALL (caught by verification, not assumed clean): the first `device_commit_files`
call, using `stagedPath` pointing at the persistent `/mnt/user-data/outputs/` directory, reported
`"written"` successfully but had actually written a STALE LEFTOVER BP1 Notebook 4 file from an
earlier session (that output directory persists and accumulates same-named files across sessions) --
md5/line-count/content all showed BP1's file, not BP5's. Caught only by verifying post-commit
content on-device rather than trusting the tool's "written" response. Fixed by re-running
`device_commit_files` with the `fileUuid` returned by `SendUserFile` (tied to the actual sent
bytes) plus `force: true`. STANDING TAKEAWAY: prefer `fileUuid` over `stagedPath` for
`device_commit_files` when the outputs directory may hold same-named files from earlier sessions,
and ALWAYS verify on-device content (md5 + a content grep, not just the "written"/"rejected"
response) after any delivery -- this is now the second real case this session of a commit call
reporting success while the real file ended up wrong (the first was the OneDrive sync-conflict
bug earlier in this session).

## Lesson #41 (2026-10-02) -- Real platform-wide doc bug found+fixed while verifying BP5 Notebook 4's real output

While checking BP5's real executive package (user confirmed "BP5 is completed" -- verified by reading
the real on-device files directly, not taking the claim at face value): MODEL_CARD.md's
"## Explainability" section says "see each variant's own saved `bp1_notebook3_validation_report_*.json`
for full real values" -- but this is BP5's model card, not BP1's. Root cause found in the SHARED
`src/reporting/report_builder.py`: `write_model_card()` (the binary-BP path used by BP1/BP4/BP5) had
this one sentence hardcoded to literally say "bp1_..." instead of using the already-available
`context['bp_id']` (every other line in the same function correctly uses it, e.g. the title).
`write_model_card_multiclass()` (BP2's path) had the identical pattern hardcoded to "bp2_..." --
harmless today since BP2 is the only multiclass BP, but the same latent bug for any future one.
Real impact: BP1's MODEL_CARD.md read correctly only by coincidence (BP1 IS "bp1"); BP4's and BP5's
MODEL_CARD.md both really said "bp1_notebook3_validation_report" where they should say their own id.
Confirmed NOT present in the HTML/Word/Excel/PPTX outputs (grep found 0 occurrences there) -- isolated
to write_model_card's one sentence. Fixed at the source (both functions now use
`context['bp_id'].lower()` via `.format()`, verified with an isolated smoke test producing the
correct string, plus py_compile clean) AND patched the two already-generated real MODEL_CARD.md
files in place (BP4's and BP5's -- deterministic text-only fix, no recomputation, no need to re-run
Notebook 4 for this alone). Standing takeaway: a hardcoded literal in a SHARED multi-BP module is a
standing platform-wide risk -- any future binary or multiclass BP's generated docs should get a
quick grep-for-the-wrong-bp-id spot check the first time its Notebook 4 actually runs, same as this
one was caught.

## Lesson #42 (2026-10-02) -- BP6 Enterprise Rollup build: sourcing architecture, 4-notebook structure, and the three-never-blended-categories discipline

BP6 (Enterprise AML Compliance Monitoring & Regulatory Reporting, this platform's Phase 4
capstone) has no trained model and no independent ground-truth label -- it is a pure,
read-only rollup of BP1-BP5's own already-computed real figures. Three real build decisions,
documented here for the next rollup-shaped BP on any future platform:

**1. Sourcing architecture.** No single persisted "Notebook 4 summary JSON" existed per BP
before this build -- each of BP1-BP5's real figures lived only in that BP's own rendered
MODEL_CARD.md/RULE_CARD.md narrative text and its own Notebook-3 `validation_report_*.json`.
Rather than recompute anything, a one-time, deterministic, read-only extractor script
(`notebooks/bp6_enterprise_compliance_monitoring/_extract_platform_source_data.py`) was
written to regex-parse each BP's real MODEL_CARD.md/RULE_CARD.md Financial Impact/Rule
Details section and load each BP's real NB3 validation_report JSON directly, producing
`bp6_platform_source_data.json` -- the one real, zero-fabrication bridge artifact every BP6
notebook reads from. STANDING RULE for any future rollup-shaped BP: build this one
deterministic extractor once, never have each downstream notebook re-parse the upstream
BPs' narrative text independently (that would risk N slightly different regexes drifting
out of sync with each other).

**2. 4-notebook structure, reconciling Section 3's phase table with Section 8's "4
phase-level rollups + 1 platform master" language.** BP6 kept the platform's standard
4-notebook shape but repurposed the middle two: Notebook 1 = business understanding +
honest sourcing-architecture disclosure (no new figures); Notebook 2 (repurposed from
"Feature Engineering & Modeling") = Phase-Level Aggregation, building the 3 real phase
rollups (Phase 1 = BP1+BP2, Phase 2 = BP3+BP4, Phase 3 = BP5); Notebook 3 (repurposed from
"Statistical Validation & Deployment") = Platform-Level Master Rollup + Structural
Validation, aggregating those 3 phase rollups into the one platform-wide master rollup
(completing the Phase 4/platform level) and running a genuine two-gate verdict; Notebook 4 =
the real "00 EXECUTIVE ROLLUP SUMMARY REPORT," reading Notebook 3's saved report and calling
the new `write_platform_*` functions. STANDING RULE: Notebook 3's Gate 2 for a rollup-shaped
BP is honestly NOT a statistical-robustness bootstrap (BP1-BP5's own Gate 2 definition) --
BP6 has no held-out test set of its own to bootstrap against. Its real Gate 2 is instead a
deterministic RECONCILIATION check: the platform rollup computed by aggregating the phase
rollups must equal, to the integer, `bp6_platform_source_data.json`'s own already-computed
platform_rollup. This real run reconciled exactly on every checked field (cat1 total
$13,877,192, cat2 total $97,950,000, investigator-hours, fewer-FP-alerts,
additional-cases-caught, BP3's node/edge counts, and all five BPs' verdicts) -- confirmed by
a real, deterministic equality check, not asserted.

**3. The three-never-blended-categories discipline, implemented structurally, not just
narratively.** `report_builder.py`'s new `_platform` suffix path (`build_platform_benefit_table`,
`compute_platform_status`, `generate_platform_smart_recommendations`,
`write_platform_word_report`, `write_platform_excel_workbook`, `write_platform_html_dashboard`,
`write_platform_pptx_deck`, `write_platform_card`) keeps BENEFIT category 1 (FP-reduction,
BP1+BP4+BP5), BENEFIT category 2 (TP-uplift, BP1+BP4+BP5), BENEFIT category 3 (BP2's own two
figures), COST CONTEXT (no real figure sourced -- none invented), and PORTFOLIO SCALE (BP3's
real node/edge counts) as five structurally separate dict keys and five separate
table/tile/sheet sections in every one of the five output formats -- never one combined
"total platform savings" number anywhere. Notebook 3's own Gate 1 re-confirms this
structurally (five separate keys present, cost_context/portfolio_scale carry no
dollar-looking key) rather than trusting it by convention alone. The Excel workbook's first
sheet is "Source Provenance" (not an Assumptions sheet -- BP6 invents no new assumptions),
listing exactly which real BP1-BP5 file each platform figure traces back to, making the
zero-fabrication chain of custody visible in the deliverable itself.

**Real tooling pitfall caught again this session (third real occurrence of the Lesson
#40/#41-class bug):** the first `device_commit_files` call for the updated
`report_builder.py` reported `"written"` successfully but the real on-device file still had
the OLD (pre-BP6) content -- confirmed by a real `wc -l`/`md5sum` mismatch against the
container's own copy immediately after. Fixed by re-running `device_commit_files` with
`force: true` and re-verifying `wc -l`/`md5sum` match on-device afterward (all subsequent
file commits this session were verified the same way before being trusted). STANDING
TAKEAWAY (reconfirmed): never trust a `device_commit_files` "written" response alone --
always verify real on-device content (line count + md5sum, not just existence) immediately
after, every time, not only when something looks wrong.

---

## Lesson #43 (2026-10-02) -- BP6 Platform Rollup: interactive-dashboard upgrade on top of a
## zero-fabrication report, without re-deriving a single number

**Context.** After BP6's first build (4 notebooks + the `_platform` report_builder.py writer
path) was already validated end-to-end, the end user asked -- in their own informal words --
for the rollup to have "contrast backgrounds," "best animations," "best slicers and filters,"
"tables that are highly interactive," "the very best SMART recommendations," and "the very
best descriptions of all the five BPs separately and what they mean for the business ... if
they were deployed for production." None of this is a request for new data: it is a request
for a materially better *presentation* of data that was already fully computed and already
cited verbatim in `bp6_platform_source_data.json` and each BP's own MODEL_CARD.md/RULE_CARD.md.
The discipline this session held to: every pixel of new UI had to be backed by a real number
or a real sourced sentence already on file -- expanding the *presentation* surface (CSS/JS/
narrative prose) is not the same thing as expanding the *evidence* surface, and the latter was
never touched.

**What changed, concretely, in `write_platform_html_dashboard`:** light/dark-aware CSS surface
tokens (new -- none existed before this upgrade, since the binary/multiclass/structural
dashboards this one's CSS shell was cloned from didn't need one), card backgrounds + shadows +
hover transforms on every KPI tile/chart box/table/recommendation card (the existing
CVD-validated `PALETTE` dict's hex values were reused completely unchanged -- only the neutral
surface/page/ink tokens gained a dark-mode variant; status colors stayed reserved for
verdict states and always paired with an icon, never color alone), a vanilla-JS `countUp()`
KPI animation and a Chart.js `animation: {duration, easing}` config (eased entrance, not an
instant snap -- deliberately subtle, since this is an executive compliance report and not a
marketing page), a real three-group filter bar (BP / Phase / financial-category, with BP and
Phase made mutually exclusive since every BP belongs to exactly one phase) wired through one
`filterState` object and one `applyFilters()` function that actually dims/hides/highlights
chart series, KPI tiles, and table rows together, and three real sortable tables (the existing
per-BP status grid, plus two new ones -- a full benefit-breakdown table and a phase-rollup
table) via one generic `makeSortable()` function rather than three bespoke ones.

**The one genuinely new function, `build_bp_business_narratives_platform()`:** returns one
substantial, distinct narrative per BP1-BP5 (what it does + its real regulatory grounding,
its real validated performance, and what production deployment would concretely mean),
built entirely from fields already present in `bp6_platform_source_data.json` (champion,
threshold, precision/recall/PR-AUC, macro-F1, lift ratio + bootstrap CI, node/edge counts,
feature counts, dollar figures) -- no new source file was read to write it. BP3's narrative
explicitly uses its real `no_dollar_reason` field instead of inventing a dollar figure, the
one place this BP6 platform's governing discipline (BP3 has no dollar-figure basis) could
most easily have been violated under upgrade pressure, and wasn't. This single function is
called from three places (`write_platform_html_dashboard`'s 5-card accordion tab,
`write_platform_word_report`'s new "Per-BP Business Narratives" section, and
`write_platform_card`'s equivalent markdown section) -- Notebook 4 now computes it once and
passes it through `context["bp_narratives"]` rather than letting each writer recompute it
independently, avoiding triple computation of the same real data on every run.

**`generate_platform_smart_recommendations` grew from 7 to 12** by adding exactly one
BP-specific recommendation per BP1-BP5 (threshold review at BP1's real 0.9798 operating
point, BP2's class-count imbalance, BP3's bootstrap-CI tightening, BP4's precision/recall
trade-off, BP5's feature-redundancy audit) -- each citing that BP's own already-sourced
numbers, none invented for the occasion.

**Real tooling pitfall caught a fourth time this session (same Lesson #40/#41/#42-class
bug, now confirmed as a *recurring* characteristic of `device_commit_files` rather than a
one-off):** the first `device_commit_files` call for the upgraded `report_builder.py`
reported `"written"` successfully, but an immediate on-device `wc -l`/`md5sum` showed the
file still at its OLD (pre-upgrade) line count and md5 -- identical to the pre-upgrade
baseline, not merely similar. A second `device_commit_files` call with `force: true`,
followed by a short pause and re-verification, produced the correct real content
(confirmed by exact line-count and md5 match against the locally-built file). STANDING
TAKEAWAY, now reconfirmed a fourth time: treat every `device_commit_files` "written"
response as provisional until a same-session `wc -l` + `md5sum` on the device matches the
source file exactly -- a single verification pass immediately after the call, every time,
catches this before it can silently ship stale content.

**Verification performed before reporting this upgrade complete:** local syntax check
(`ast.parse` + `py_compile`) of the recombined ~6,038-line `report_builder.py` with zero
duplicate top-level function definitions; a full local smoke-test run producing all five
real formats plus `PLATFORM_CARD.md`/`CHANGELOG.md` against the real
`bp6_platform_source_data.json`; a local dry-run of the updated Notebook 4 against the
existing stub `utils/` harness; then the real on-device re-run of Notebook 4, with content
`grep` on the real generated `BP6_Platform_Rollup_Dashboard.html` confirming the new CSS/JS
(`filterState`, `applyFilters`, `countUp`, `makeSortable`, `prefers-color-scheme`,
`easeOutCubic`, the narrative accordion markup) actually landed in the generated file (not
only in the source), and a direct number-by-number spot-check of every new narrative
sentence's figures (thresholds, precision/recall, PR-AUC, macro-F1, lift ratio, node/edge
counts, dollar totals) against both the real HTML output and `bp6_platform_source_data.json`
itself, confirming an exact match in every case.

**Honest limitation flagged, not silently skipped:** the Word, Excel, and PowerPoint/PDF
formats are inherently static documents and cannot carry CSS transitions, Chart.js
animation, or JS-driven filters/sorting -- the "best animations/slicers/filters" request is
fulfilled in full in the HTML dashboard (the one format capable of it) and NOT reproduced in
the other four, which instead gained only the new narrative content and the expanded
recommendations. This is a real constraint of the file formats themselves, not an
implementation gap, and is recorded here rather than left for someone to discover later.

---

## Lesson #44 (2026-10-02) -- BP6 Platform Rollup: pulling real methodology/regulatory depth
## from each BP's own MODEL_CARD.md/RULE_CARD.md, by extending the extractor, not by writing

**Context.** After the interactive-dashboard upgrade (Lesson #43), the end user clarified what
"comprehend all the BPs, all in one" actually meant: the per-BP narrative cards were judged
too shallow because they covered business impact only -- they wanted each BP's real
methodology (champion model, feature count, SHAP drivers), named engineered features, and
regulatory citations pulled from each BP's own already-rendered MODEL_CARD.md/RULE_CARD.md
text as well. The discipline this required: add real extraction, not new writing -- every
new sentence had to come from a real file already on disk, parsed with the same raise-
loudly-if-missing regex discipline the original extractor already used for financial figures.

**What changed in `_extract_platform_source_data.py`:** two new real-extraction functions,
`parse_business_objective_and_regulatory()` (pulls each BP's real `## Business Objective` and
`## Regulatory Mapping` sections verbatim out of its own MODEL_CARD.md/RULE_CARD.md -- BP3's
RULE_CARD.md uses the identical heading, so one function covers all five) and
`top5_shap_features()` (the real top-5 entries of each BP's own already-computed
`shap_mean_abs_importance` dict from its NB3 validation_report JSON). BP4/BP5's real named-
engineered-feature lists (5 and 8 features respectively) are parsed OUT OF the real Business
Objective sentence text via a single regex (`-- ([a-z_]+(?:, [a-z_]+)+) --`) rather than
hardcoded, so the extractor stays correct if that sentence's wording ever changes -- verified
against both BP4's and BP5's real text before relying on it. BP3 correctly gets neither
`top_shap_features` nor `named_engineered_features` -- re-confirmed honestly absent in the
regenerated real `bp6_platform_source_data.json`, not silently defaulted to an empty list.
Re-running the extractor reproduced the exact same platform-rollup dollar totals as before
($13,877,192 / $97,950,000 / $1,313+$1,104,000 / 2,032,095 nodes), confirming the new parsing
logic touched nothing financial.

**What changed in `build_bp_business_narratives_platform()`:** each of BP1/BP2/BP4/BP5 (and
BP3, in its own honest terms) gained a second real-content layer, "methodology" --
Methodology & Regulatory Basis -- built from the real business_objective (tightened to a
sentence or two, never pasted verbatim at full paragraph length, never changing its
substance), the already-available champion/feature-count/threshold, the real top-5 SHAP
drivers translated into plain language via a small, explicit name->phrase lookup
(`_SHAP_FEATURE_PHRASES`, covering only the real feature names that actually appear in this
platform's own top-5 lists -- an unrecognized name falls back to its own raw name in
backticks rather than inventing a phrase), BP4/BP5's own real named engineered features, and
1-2 sentences naming each BP's 2-3 most relevant real regulatory citations (never the raw
bullet dump). One genuinely honest moment worth recording: BP5's own MODEL_CARD.md narrative
text claims `sender_country_empirical_risk` is "the top cross-border feature" -- true only
among BP5's own 8 cross-border-specific features, not the real overall top-5 SHAP list (which
remains dominated by the shared transaction-monitoring features). The methodology text states
both facts side by side rather than either overclaiming cross-border dominance or silently
dropping the model card's own real claim.

**HTML surfacing:** rather than appending a wall of text to the existing per-BP accordion
card, each card gained a small two-button sub-tab bar ("Business Impact" / "Methodology &
Regulatory Basis") toggling two panels inside the same card body -- vanilla JS/CSS, no new
dependency, consistent with the rest of this dashboard's interaction model. The Word report
and PLATFORM_CARD.md each gained an equivalent "Methodology & Regulatory Basis"
heading/section directly under each BP's existing three business-impact headings.

**Verification performed:** local regex testing of the Business Objective / Regulatory
Mapping / named-feature extraction against all 5 real card files before touching the device;
real on-device re-run of the extended extractor (confirmed BP3's two fields correctly absent,
all dollar totals unchanged); local `ast.parse`/`py_compile` of the recombined ~6,193-line
`report_builder.py` (55 top-level functions, zero duplicates); a full local smoke test;
deployment to device (second `device_commit_files` attempt needed again -- see below); a real
on-device re-run of Notebook 4; and content-`grep`/python-docx extraction confirming every new
regulatory citation, SHAP feature name, and BP4/BP5 named engineered feature appears verbatim
in the real generated HTML, Word, and PLATFORM_CARD.md (not only in the source).

**Real tooling pitfall caught a fifth time this session (same `device_commit_files`-class
bug):** the first commit of the upgraded `report_builder.py` again reported `"written"`
successfully while leaving the PRIOR version's exact line count and md5 on-device; a second
`force: true` commit followed by a short pause produced the correct content. By now this is a
structural characteristic of the tool to plan around on every single commit of this file in
this environment, not an occasional glitch -- standing practice for the rest of this project:
always commit twice and re-verify, or at minimum never trust a single `device_commit_files`
call for this file without an immediate on-device `wc -l`/`md5sum` check.

---

## Lesson #45 (2026-10-02) -- BP6 Platform Rollup: "all in one, in all formats" means a
## single real narrative source feeding five writers, not five independent narratives

**Context.** After the per-BP methodology/regulatory depth (Lesson #44) landed in the HTML
dashboard, Word report, and PLATFORM_CARD.md, the end user's follow-up -- "all in one in all
formats" -- turned out to mean exactly what it said: the same depth had to reach the Excel
workbook and PowerPoint deck too, which the user had checked directly and found genuinely
lacking (Excel: zero per-BP narrative content anywhere in its 4 sheets; PPTX: one generic
platform-wide "What This Means for the Business" slide and one generic "Regulatory &
Compliance Mapping" slide, neither broken out per BP). The discipline this required: extend
`build_bp_business_narratives_platform()` itself -- the one function already supplying
HTML/Word/Card -- rather than writing separate narrative logic for Excel and PPTX, so all
five output formats stay provably in sync off one real source, never five copies that could
silently drift.

**What was added to the narrative function:** two new per-BP keys, `regulatory_citations`
(the exact 2-3 real citation names each BP's own methodology prose already names, extracted
by a new `_citation_names()` helper that picks by index out of the real `regulatory_mapping`
list and trims each to just its citation name -- never a new citation invented) and
`business_objective_tightened` (a one-to-two-sentence real summary matching the opening of
each BP's own methodology paragraph, for a format like an Excel cell where the full paragraph
would not fit even with wrap_text). Both are pure extraction/reuse of text this function
already had the inputs for -- no new source file was read.

**Excel (`write_platform_excel_workbook`):** added a 5th sheet, "Per-BP Business &
Methodology" -- one row per BP (BP1-BP5), 9 columns (Business Objective, Champion/Signal,
Feature Count, Threshold, Top SHAP Drivers, Named Engineered Features, Regulatory Citations,
Business Impact), wrap_text + 130px row height so real text displays without truncation, same
`_brand_excel_sheet`/header-styling convention as the other 4 sheets. BP1/BP2/BP3's Named
Engineered Features cells are genuinely `None` (blank) -- confirmed by direct openpyxl
inspection after the real run, not dressed up as "N/A" text, since this platform's standing
rule is that an absent real value stays genuinely absent. BP2/BP3's Threshold cells are
likewise genuinely blank (BP2 is multi-class argmax, BP3 is a rule with no decision
threshold) -- real structural absence, not a fabricated placeholder.

**PPTX (`write_platform_pptx_deck`):** replaced the two old generic slides with 10 new
slides -- 2 per BP (Business Impact, then Methodology & Regulatory Basis) -- rather than
cramming both sections onto one slide per BP, so no real sentence needed truncation. The
old platform-wide "What This Means for the Business" slide was kept (retitled "...
(Platform-Wide)" for clarity against the new per-BP ones); the old generic "Regulatory &
Compliance Mapping" slide was removed outright since its content now lives, correctly
attributed, on each BP's own real Methodology slide. Deck grew from 8 slides to 18.

**Verification performed:** local `ast.parse`/`py_compile` of the recombined ~6,330-line
`report_builder.py` (56 top-level functions, zero duplicates); a full local smoke test;
direct openpyxl/python-pptx extraction confirming the new sheet's real BP4/BP5 named-feature
lists, BP1-5 real regulatory citations, and real business-impact text landed correctly, with
BP1/BP2/BP3's blank cells confirmed genuinely blank (not a fabricated placeholder); real
on-device re-run of Notebook 4; and the same openpyxl/python-pptx extraction repeated against
the real device-generated files, confirming identical content landed there too (not only in
the local smoke-test copy). All platform dollar/volume totals remained unchanged across the
re-run, confirming this round of changes touched only presentation, never the underlying
real figures.

**Real tooling pitfall caught a sixth time this session:** the first `device_commit_files`
call for this round's `report_builder.py` again reported `"written"` while leaving the PRIOR
version's exact content on-device; the second `force: true` commit (now standard practice,
applied without waiting to discover the problem first) produced the correct real content on
the first re-check. Treating every single commit of this file as needing two attempts plus
verification, rather than hoping each one lands first try, is now this session's default
working assumption for the rest of this project.


## Lesson #46 (2026-10-02) -- BP6 is the one exception to this platform's "4 separate notebook files per BP" convention: consolidated into a single real `00_Executive_Rollup_Report.ipynb` per explicit user request ("only one ipynb... not seperate files for each format"; the file was briefly named `BP6_Enterprise_Rollup_All_In_One.ipynb` before a follow-up explicit user request to rename it to `00_Executive_Rollup_Report.ipynb`, matching this platform's `NN_name` notebook-numbering convention), reformatting (not rewriting) the same real logic from its 4 original SINGLE_CELL `.py` files into one notebook's cells; the 4 old files were deleted (not left stale alongside it) once the single `.ipynb` was confirmed, via `nbformat.validate` + a real `jupyter nbconvert --to notebook --execute` run, to reproduce byte-identical real headline figures (PASS, $13,877,192 / $97,950,000 / etc.) and regenerate the real five-format package end-to-end.

## Lesson #47 (2026-10-02) -- Real JS Unicode-escape bug class (`\XXXX` vs `\uXXXX`) crashes
an entire `<script>` block when it lands inside a template literal, but only silently
mis-renders a character inside a regular JS string -- and is valid CSS either way
The user reported BP6's HTML dashboard rendering all "$0" KPI tiles and a completely empty
Per-BP table via a screenshot. Root cause, found with `node --check` on the extracted
`<script>` block (never guessed): `src/reporting/report_builder.py`'s
`write_platform_html_dashboard` wrote a handful of Unicode escapes without the required `u`
prefix (`\25BE`, `\2713`, `\26A0`, `\2715`, `\2022`). JavaScript (ES6+) forbids octal-style
`\NNNN` escapes in **template literals** (backtick strings) -- a hard `SyntaxError` that kills
the *entire* enclosing script before any of it runs, which is exactly why every DATA-driven
render call (countUp, table population, applyFilters) silently never executed even though the
real data embedded in the page (`const DATA = {{...}}`) was always complete and correct. The
same bare pattern inside a **regular** (non-template) JS string is NOT a syntax error in
non-strict mode -- it's legacy octal-escape interpretation, so it silently renders the WRONG
character instead of crashing (easy to miss without comparing rendered output char-by-char).
The same pattern inside a **CSS** `content:` property value is actually valid CSS syntax (CSS
never needed a `u` prefix) -- do not "fix" those; two of the five occurrences found here were
exactly this harmless case and were correctly left untouched. Lesson for future report-builder
work: any `\NNNN`-style escape meant as a Unicode code point must always be written `\uNNNN` in
JS, with the fatal/cosmetic/non-issue severity depending entirely on which of these three
contexts it sits in -- check all three before assuming a fix is complete.

## Lesson #48 (2026-10-02) -- BP5 + BP6 hardening pass; and a real environment-boundary
disclosure: this device_bash sandbox cannot import xgboost/sklearn, so a deployable
service's real-model import can only be `py_compile`-verified here, never actually run
Completed the hardening pass for BP5 and BP6 -- the only 2 of this platform's BPs that had not
yet been through it (BP1-BP4 already had it; see Lesson context in each BP's own CHANGELOG).
BP5: extracted `src/services/bp5_scoring_service.py` from Notebook 3's own in-kernel FastAPI
self-test (`score_transaction` copied verbatim, both variants' self-test already proved
bit-identical to direct `predict_proba`, 5,000 rows, 0 mismatches) -- simpler than BP4's
service, since BP5 has no disclosed-NaN feature column, so no Optional/impute branch is
needed. Added 5 structural pytest tests against a synthetic stub classifier (never the real
trained XGBoost model); 5/5 passed for real. Found and fixed BP5's `docker-compose.yml` build
context (`../../../..`, one level above the real repo root -- the exact bug already fixed
platform-wide for BP1-BP4 but missed for BP5 since it had not been hardened yet; confirmed via
`realpath --relative-to`, corrected to `../../..`). BP6: closed its Dockerfile's own disclosed
gap (requirements.txt missing nbformat/nbconvert/ipykernel, needed for its
`jupyter nbconvert --execute` batch-job CMD) by adding them to requirements.txt and updating
the Dockerfile's gap comment to a dated RESOLVED note; re-verified BP6's own build context was
already correct (not a bug there).

Real environment-boundary finding, disclosed rather than silently worked around: this session's
`device_bash` sandbox (a separate, restricted Linux VM from whatever environment actually runs
the user's Jupyter kernel) has neither `xgboost` nor `sklearn` installed, and `pip install`
inside it failed with a real "No space left on device" (its own `/sessions` mount was at 99%,
148M free, at the time). This means every deployable scoring service in this platform --
including the already-hardened BP1-BP4 ones, confirmed by testing BP1's here too -- can only be
`py_compile`-verified and pytest-verified against a synthetic stub from this sandbox; actually
importing one of these modules against its real pickled champion model has never been possible
from here, and was never silently assumed to have been done. The real, bit-identical proof that
each service's `score_transaction` logic is correct comes entirely from Notebook 3's own
in-kernel FastAPI self-test, run by the user in their own real environment (which does have
xgboost/sklearn) -- not from anything this sandbox can independently confirm end-to-end.

================================================================================
Lesson #49 (2026-10-02): GitHub-readiness final sweep + closing BP6's missing
test-coverage gap -- platform-wide hardening pass, post-BP1-BP6.
================================================================================
Context: with BP1-BP5 real-confirmed and BP6's Dockerfile/requirements.txt gap
closed (Lesson #48), the user asked to "start GitHub works for BP1-BP6" and to
harden whatever was left. Did a final readiness sweep before `git init`:
- Large-file scan (`find -size +10M`, `+5M -10M`) outside already-gitignored
  data/models dirs -- only the known 167MB bp1_score_baseline_li_medium.json
  (already covered by the Lesson #48 .gitignore pattern). models/ itself is a
  real 11GB of .pkl files, already excluded via `models/**/*.pkl`.
- Secret scan (`.env`/`.pem`/`.key`/`*credentials*`/`*token*`/API-key-shaped
  strings) across src/, notebooks/, configs/ -- clean (the only hits were
  data/raw/*_Patterns.txt matching the `*_pat*` glob, a harmless false
  positive, already gitignored anyway).
- Final bandit (-lll, matches the CI gate) and py_compile across all of src/
  -- 0 findings, clean.
`git init` + `git branch -m main` + local identity (name "Nandagopal", email
rnanda19@hotmail.com -- the user's own stated resume/LinkedIn email; trivially
changeable with one `git config` command if they want a different one, e.g. a
GitHub-noreply address). Staged 254 files, 4.9MB total -- confirmed via
`git status --short | grep -E "models/.*\.pkl|data/raw/|score_baseline"` that
nothing large slipped through. Initial commit made locally. No remote push yet
-- no repo URL or PAT has been provided for this project (unlike the AMEX
platform's own repo, which the user already has). This sandbox's device_bash
VM has no `gh` CLI, no global git config, and no SSH keys -- confirmed before
assuming any credential path was already available.

Second, separate real gap found and closed during this same pass: every other
BP's tests/ folder had its own test_<bp>_scoring_service.py; BP6's folder had
only a README.md -- the one BP with no test file platform-wide. Not a scoring-
service gap (BP6 has no model, no API -- disclosed explicitly in its own
Dockerfile/PLATFORM_CARD.md) but a real gap in exercising BP6's own
report_builder.py code path (compute_platform_status,
build_platform_benefit_table, generate_platform_smart_recommendations,
build_bp_business_narratives_platform, write_platform_html_dashboard). Built
tests/bp6_enterprise_compliance_monitoring/test_bp6_report_builder.py against
a small, clearly-synthetic platform_source_data fixture matching the real
documented shape field-for-field (read every real field-access path directly
from report_builder.py before writing the fixture, per the standing Lesson #3
no-guessing rule) -- never the project's real bp6_platform_source_data.json or
any real trained model/data. Verified standalone first (ran in a scratch
location, not tests/, caught one real missing fixture field
`headline_grand_total_note` via a real KeyError, fixed, re-ran clean) before
moving it into the real tests/ folder.

This test doubles as a permanent regression test for the same day's "Phase 1 /
Phase 2 label repeated on every row" dashboard fix: the fixture deliberately
gives BP1/BP2 and BP3/BP4 the same phase (mirroring the real platform's own
phase grouping, confirmed from the real bp6_platform_source_data.json read
during that fix's QA), and asserts the generated dashboard's JS passes
`node --check` and still contains the data-sort/collapseRepeatedCell/
COLLAPSE_CONFIG code -- so a future edit that silently reintroduces the
repeated-label bug fails this test, not just a future screenshot complaint.

Platform-wide test count: 33 -> 39, all passing. Committed to the new local
git repo as a second commit, after the initial-commit baseline. Per the
project's own standing "code should give the outputs, not Claude" rule: this
entire pass only wrote/tested code and ran `git`/`pytest`/`bandit` -- it never
executed any BP's real notebook or generated a real deliverable report.
