# Leakage Audit (Static / Code-Reading Pass)

Scope and method: this is a **static code audit** -- reading each BP's `02_feature_engineering_modeling`
and `03_statistical_validation_deployment` scripts directly for leakage-prone patterns (train/test split
placement, where `.fit()` is called, chronological vs. random splitting, entity-level separation). It is
**not** an empirical leakage test (re-running a split with a chronology check, or re-fitting with a
held-out time window) -- that requires executing the real pipeline against real data, which is blocked by
this project's standing no-pipeline-execution rule (see `docs/audit/INITIAL_REPOSITORY_AUDIT.md`). What
follows is what a careful reading of the real, committed code shows -- not a guarantee that no leakage
exists, and not a claim that this is a full line-by-line review of every one of the 20 notebook scripts.

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
blocked on the same standing rule as DEF-001/DEF-002 in `docs/audit/DEFECT_REGISTER.md` unless the user
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

## Finding L-3: model `.fit()` calls occur after the split, not before, in BP1 (spot-checked)

**Evidence**: in BP1's `02_feature_engineering_modeling_SINGLE_CELL.py`, every `.fit(` call found
(`model.fit(X_train, y_train)`, the cross-validated search's `m.fit(X_search.iloc[train_idx], ...)`)
operates on already-split training data, not the full `X`/`y`. No `StandardScaler`/`MinMaxScaler`/
`Imputer` call fit on the full dataset before the split was found in this file.

**This is a positive finding, not a defect** -- BP1's split-then-fit order is the correct pattern and
does not show the "preprocessing fitted on validation/test data" anti-pattern the external review asked
to check for. **Scope limit**: only BP1 was checked at this level of detail in this pass; BP2-BP5 were
only checked for the split call's existence (Finding L-1/L-2), not for fit-call placement.

## Summary

| Finding | Severity | Status |
|---|---|---|
| L-1: random (not chronological) split, all 5 BPs | Medium-High methodological risk | Confirmed by code read; fix requires pipeline execution |
| L-2: no explicit entity-level split separation | Medium methodological risk | Confirmed absent by code read; fix requires pipeline execution |
| L-3: split-before-fit ordering (BP1) | N/A -- correct pattern | Confirmed correct in BP1; BP2-BP5 not yet checked at this depth |

This audit does not change any reported metric in `BENCHMARKS.md` -- it documents a real methodological
gap (non-chronological, non-entity-aware splitting) that the external review's Priority 1 recommendation
("add temporal and entity-level leakage checks") correctly identified, and that this platform has not yet
addressed because doing so requires real pipeline execution against real data.
