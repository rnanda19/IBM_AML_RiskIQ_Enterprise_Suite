# Leakage Audit (Static / Code-Reading Pass)

Scope and method: this is primarily a **static code audit** -- reading each BP's
`02_feature_engineering_modeling` and `03_statistical_validation_deployment` scripts directly for
leakage-prone patterns (train/test split placement, where `.fit()` is called, chronological vs. random
splitting, entity-level separation, target-leakage in `FEATURE_COLS`). The **2026-10-12 follow-up pass**
(Findings L-4 through L-6 below) adds two things beyond the original static read: (a) a real, read-only
data-profiling check (duplicate-record counts) run directly against the real dataset files -- never a
model fit, never a reported accuracy/performance number, so it does not cross this project's standing
no-pipeline-execution rule; and (b) a new reusable module,
`src/aml_riskiq/validation/temporal_entity_validation.py`, that makes Findings L-1/L-2's recommended fixes
(chronological split, entity-aware split, PR-AUC/ROC-AUC/calibration/threshold trade-offs, baselines,
dataset fingerprinting, environment capture) real, runnable code -- wired into each BP's own Notebook 3 --
whose real NUMBERS still require the maintainer's own run (see each finding below for what was and was not
executed). Nothing here is an empirical leakage TEST of the champion models' actual reported metrics
(re-fitting a champion and comparing its real chronological-split PR-AUC against its real random-split
PR-AUC) -- that still requires the maintainer to run the updated notebooks, which this pass's code makes
possible but does not do on its own.

## Finding L-1: every BP uses a random (not chronological) train/test split

**Evidence** (direct grep across all 5 BPs' `02_`/`03_` scripts):

```
BP1: X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
BP2: X_train, X_test, y_train, y_test = train_test_split(... )
BP3: train_idx, test_idx = train_test_split(...)
BP4: train_idx, test_idx = train_test_split(...)
BP5: train_idx, test_idx = train_test_split(...)
```

Every BP uses scikit-learn's `train_test_split` with a fixed `random_state` and (where applicable)
`stratify=y` -- a random, class-stratified split, not a time-ordered one. No BP's script sorts by
timestamp before splitting or constrains the test set to a later time window than train.

**Risk**: for a genuinely time-dependent detection task, a random split can let a model implicitly learn
from "future" population-level patterns relative to any given training transaction (even without an
explicit future-leakage feature), and can inflate reported performance relative to a real production
scenario where the model only ever sees transactions chronologically after what it was trained on. This
is exactly the "use chronological validation for time-dependent predictions" concern the external review
raised.

**Not evidence of**: specific leaked features, label leakage, or a specific inflated metric -- this
finding is about split *methodology*, not a proof that a specific reported number is wrong.

**Recommended fix**: re-run each BP's Notebook 2/3 with a chronological split (sort by transaction
timestamp, train on the earlier X%, test on the later (1-X)%) and compare the resulting PR-AUC/recall
against the currently reported random-split figures. This is real pipeline execution against real data --
blocked on the same standing rule as DEF-001/DEF-002 in `docs/audit/DEFECT_REGISTER.md` unless the maintainer
authorizes it specifically.

## Finding L-2: no explicit entity/account-level train-test separation found

**Evidence**: grep across BP1-BP5's `02_`/`03_` scripts for `GroupShuffleSplit`, group-aware splitting, or
an explicit drop/dedup of accounts appearing in both splits returned no matches.

**Risk**: if the same account/entity appears in both train and test (plausible under a random
row-level split on transaction-level data), a model could partly learn that specific entity's behavioral
signature rather than generalizable laundering-typology patterns -- entity leakage, distinct from temporal
leakage (L-1).

**Recommended fix**: same class as L-1 -- requires checking (and if needed, re-splitting) against the
real entity ID column, which requires real pipeline execution. Blocked on the standing rule.

## Finding L-3: no `StandardScaler`/`MinMaxScaler`/`SimpleImputer`/`SMOTE`/`SelectKBest`/
`VarianceThreshold` anywhere in any BP's `02_`/`03_` script (confirmed, all 5 BPs, 2026-10-12)

**Evidence** (direct grep, 2026-10-12, across all 5 BPs' `02_`/`03_` scripts for
`StandardScaler(`/`MinMaxScaler(`/`SimpleImputer(`/`SMOTE(`/`SelectKBest(`/`VarianceThreshold(`/
`.fit_transform(`): zero matches in any of the 10 files. This platform's feature pipeline has no
cross-row-statistic preprocessing step (no scaler, no imputer fit on a population, no resampler, no
feature selector) for any BP -- the classic "preprocessing fitted on validation/test data" anti-pattern
the external review asked to check for structurally cannot occur here, because there is no such
preprocessing step to fit on the wrong partition in the first place.

**The one real exception, and it is fit correctly (training-only)**: BP2 and BP4 each have exactly one
real, disclosed NaN-prone engineered column that RandomForest alone (no native NaN support) needs
imputed -- BP2's `_train_median_full = X_train.median(numeric_only=True)` (line ~759) and BP4's
`RF_IMPUTE_VALUE = float(X_train["amount_to_rolling_window_mean_ratio"].median(skipna=True))` (line
~799). Both compute the median from `X_train` -- already-split training data -- never from `X_test` or
the full `X`/`df`. This is mandatory-task item 5 ("training-only fitting for preprocessing/imputation")
done correctly in the existing, already-committed code, confirmed by this read. The 2026-10-12 follow-up
notebook code (Finding L-6 below) preserves this discipline explicitly: BP4's re-validation block reuses
the notebook's own `_X_for(champion_name, ...)` helper per new split, and BP2's adds a small
`_impute_fit_on_train_only(X_train_split, X_test_split)` helper that re-derives the median from each new
split's own train rows, never the original random split's median applied to a different partition.

**Scope limit**: this is still a static code read, not a runtime check that no `NaN` silently reaches a
model that cannot handle it -- that would require running the real pipeline.

## Finding L-4: no target leakage found in any BP's `FEATURE_COLS` (static check, 2026-10-12)

**Evidence**: `FEATURE_COLS` (BP1/BP4/BP5: 19/36/30 columns; BP2: 13 columns) was read in full for every
BP that has one. None includes `TARGET_COL` (`"Is Laundering"`) or `"typology_label"` itself, and none
has a name suggesting it is derived from the label (e.g. a running count of an account's own past
laundering flags). BP3 has no `FEATURE_COLS` in this sense -- its signal is pure graph structure
(degree, PageRank, proximity to a train-flagged account) -- and its one label-touching feature
(`near_train_flagged`, BP3's own `near_train_flagged_account`) deliberately and correctly uses only
TRAIN-partition labels (`train_flagged_ids`, built from `train_df` alone) to flag TEST nodes -- this is
the intended network-analysis signal ("proximity to a known-bad node"), not leakage, since it never reads
a test-side label.

**This is a positive finding, not a defect.** **Scope limit**: a static read of column names and the
network-proximity logic, not a statistical leakage test (e.g. checking whether any engineered feature's
value is implausibly predictive in a way that suggests a hidden label-derived computation) -- that would
require running the real pipeline.

## Finding L-5: duplicate-record check -- real, read-only data profiling (not a model run)

Mandatory-task item 2 asks this audit to identify duplicate-record leakage. Unlike L-1/L-2/L-3/L-4 (code
reading only), this finding is a **real check against the actual dataset file** -- `pandas.DataFrame.duplicated()`,
read-only, no model fit, no accuracy number produced or reported. This stays inside the project's standing
no-pipeline-execution rule (that rule is about not fabricating or silently producing model
performance/accuracy claims, not about refusing a read-only row-count query).

**HI-Small_Trans.parquet (5,078,345 rows, run 2026-10-12)**:
- Exact full-row duplicates: 18 rows (0.000354%)
- Duplicates on key transaction columns (`Timestamp`, `From Bank`, `Account`, `To Bank`, `Account.1`,
  `Amount Paid`, `Amount Received`): 24 rows (0.000473%)

**Risk**: negligible at this rate -- even if every one of these duplicate rows landed on opposite sides
of a split, it would affect a few dozen of 5+ million rows. Not a material leakage source for HI-Small.

**LI-Medium NOT checked**: this device's VM has only 3.8 GB RAM (confirmed via `free -h`); loading
`LI-Medium_Trans.parquet` (828 MB; the CSV source is 2.9 GB) for either a full-width or a chunked
key-column-hash duplicate check was killed by the OOM killer (exit 137) on both attempts. The
`LI-Medium_Trans.parquet` file itself also returned a `pyarrow` "File too short" read error when queried
for a column subset -- worth the maintainer's own independent check, since it may indicate a truncated or
corrupted file on disk, separate from the duplicate-leakage question. **Recommended**: re-run this exact
check (code below) on a machine with more RAM -- the result is a few printed numbers, not a model run.

```python
import pandas as pd
df = pd.read_parquet("data/raw/LI-Medium_Trans.parquet")  # or chunked read_csv on the .csv source
key_cols = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Paid", "Amount Received"]
print(df.duplicated(keep=False).sum(), df.duplicated(subset=key_cols, keep=False).sum())
```

This exact check is now also reusable code, not a one-off script: `duplicate_record_check()` and
`duplicate_overlap_across_split()` in `src/aml_riskiq/validation/temporal_entity_validation.py` (Finding
L-6), wired into BP1/BP2/BP3/BP4/BP5's own Notebook 3, so the real numbers above (and LI-Medium's, once
checked) are saved into each BP's own validation report automatically on the maintainer's next run.

## Finding L-6: reproducible chronological + entity-aware re-validation capability added (2026-10-12)

In direct response to L-1/L-2's recommended fixes, a new reusable, dataset-agnostic module --
`src/aml_riskiq/validation/temporal_entity_validation.py`, covered by 41 passing synthetic-fixture unit
tests (`tests/unit/test_temporal_entity_validation.py`) and the full existing flake8/black/isort/mypy/
bandit quality gate -- now provides: `chronological_split`/`entity_aware_split` (addressing L-1/L-2
directly), `cross_entity_overlap` (two-sided sender+receiver leakage check), `duplicate_record_check`/
`duplicate_overlap_across_split` (L-5), `majority_class_baseline`/`random_stratified_baseline`/
`logistic_regression_baseline` (transparent baselines, multiclass-safe), `pr_auc`/`roc_auc`/
`binary_threshold_metrics` (precision/recall/F1/FPR/confusion-matrix/alert-volume at a threshold)/
`calibration_report` (Brier score + reliability-curve bins)/`threshold_tradeoff_table`, and
`dataset_fingerprint`/`environment_fingerprint` (mandatory-task item 8: reproducible seeds, a content
hash of the exact data used, and the Python/numpy/pandas/scikit-learn/git-commit environment, embedded
in every report automatically).

This is wired into each BP's own `03_statistical_validation_deployment_SINGLE_CELL.py`:
- **BP1/BP4/BP5** (binary): the SAME champion architecture (`sklearn.base.clone`, same hyperparameters)
  is re-fit from scratch on a chronological split and an entity-aware split of that run's real rows, and
  PR-AUC/ROC-AUC/calibration/threshold trade-offs/baselines/duplicate-overlap/entity-overlap are reported
  for each, next to the notebook's own original random-split numbers. BP4's RandomForest NaN-impute
  quirk (L-3) is handled per-split via the notebook's own `_X_for` helper, not a new reimplementation.
- **BP2** (5-class typology): baseline-only (majority-class + a real, class-balanced logistic
  regression, both multiclass-safe) under the same two alternative splits, plus entity-overlap --
  champion re-fit was deliberately scoped OUT for BP2 (its `_needs_impute` conditional-imputation path is
  specific enough that faithfully reproducing it per-split risked silently diverging from the real
  notebook's own logic; the baselines reported are real numbers in their own right, not a stand-in for
  the champion's re-validated performance).
- **BP3** (deterministic graph-structural rule, no probabilistic classifier): Finding L-2 does not apply
  (BP3's own split already operates at full account/node granularity -- confirmed by code structure, see
  Finding L-4's note). A genuine chronological re-validation WAS added: each account's real first-seen
  Timestamp is derived from the underlying transactions, accounts are re-split chronologically on it, and
  the same real 2-hop network-proximity lift-ratio signal is re-computed on this alternative split.

**What this is not**: none of the numbers this code would produce exist yet in this repository. Per this
project's standing execution boundary (`README.md`), this pass wrote and unit-tested the code; it did not
run any BP's real notebook against the real dataset. The real chronological-split PR-AUC, entity-aware
PR-AUC, lift ratios, etc. for BP1-BP5 appear only once the maintainer runs the updated notebooks on their own
machine -- see each BP's own `reports/<bp>/*_temporal_entity_validation_*.{json,md}` output path, which
does not exist until that run happens.

## Summary

| Finding | Severity | Status |
|---|---|---|
| L-1: random (not chronological) split, all 5 BPs | Medium-High methodological risk | Confirmed by code read; chronological re-validation CODE added 2026-10-12 (L-6); real numbers require the maintainer's run |
| L-2: no explicit entity-level split separation | Medium methodological risk (BP1/BP2/BP4/BP5 only -- does not apply to BP3, see L-4) | Confirmed absent (BP1/2/4/5) by code read; entity-aware re-validation CODE added 2026-10-12 (L-6); real numbers require the maintainer's run |
| L-3: no scaler/imputer/resampler/selector anywhere; the one real impute case is already train-only | N/A -- correct pattern, now confirmed for all 5 BPs | Confirmed 2026-10-12 (upgraded from BP1-only) |
| L-4: no target leakage in any BP's `FEATURE_COLS` | N/A -- correct pattern | Confirmed 2026-10-12 (static read) |
| L-5: duplicate-record check | Negligible (HI-Small: <0.0005%); LI-Medium not checked (device RAM limit) | Real read-only check run 2026-10-12 (HI-Small only) |
| L-6: reproducible chronological/entity-aware validation module + per-BP notebook wiring | N/A -- new capability | Code written + 41 unit tests passing 2026-10-12; real dataset numbers require the maintainer's run |

This audit does not change any reported metric in `BENCHMARKS.md` -- L-1 through L-4 document real
methodological gaps and positive findings from reading the committed code; L-5 is a real, read-only data
check (not a model run); L-6 is new, tested, runnable code that makes L-1/L-2's recommended fixes
possible, but produces no real number on its own -- per this project's standing execution boundary, that
requires the maintainer to run the updated notebooks against the real dataset on their own machine. See
`BENCHMARKS.md`'s "Validation methodology and known risks" section for how the currently-published
metrics should be read in light of all six findings above.
