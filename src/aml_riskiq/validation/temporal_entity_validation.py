"""Reusable, model-agnostic re-validation helpers: chronological and entity-aware splits,
baseline comparisons, and precision/recall/PR-AUC/calibration/threshold-trade-off reporting.

Added 2026-10-12 in response to `docs/data/LEAKAGE_AUDIT.md` Findings L-1 (every BP1-BP5
notebook uses a random, non-chronological `train_test_split`) and L-2 (no explicit
entity-level train/test separation) -- both documented methodological risks, not proof
that a published metric is wrong. This module makes it possible to re-check that, with
real numbers, reproducibly.

Scope and non-scope, stated plainly:
- This module contains NO dataset-loading or feature-engineering code, and never reads a
  real CSV/Parquet file itself. It operates purely on arrays/Series a caller's own
  notebook has already built in memory -- the same X/y/timestamp/entity columns each
  BP's 02_/03_ script already constructs after its own real feature engineering. This
  keeps it reusable across BP1/BP2/BP4/BP5 without duplicating any BP's feature-
  engineering logic (which would risk silently diverging from the real pipeline).
- This is a library, not a runner. It computes a real number from whatever real array it
  is given, and produces no result on its own -- it holds none of this project's real
  data. A human must import it from inside the relevant notebook and run that notebook on
  real data for any of this module's output to mean anything. This keeps it inside this
  project's standing execution boundary (see README.md's "Execution boundary" section):
  Claude writes this code; the code produces real numbers only when the user runs it.
- The binary-classifier-specific functions (`pr_auc`, `calibration_report`,
  `binary_threshold_metrics`, `threshold_tradeoff_table`, `prevalence_baseline_pr_auc`)
  apply to BP1/BP4/BP5 (binary "Is Laundering" classifiers). BP2 is a 5-class typology
  classifier -- use `majority_class_baseline`/`random_stratified_baseline`/
  `logistic_regression_baseline`, which are multiclass-safe, instead. BP3 has no
  probabilistic classifier at all (a deterministic graph-structural rule) -- only
  `entity_aware_split`/`cross_entity_overlap` apply to it.
- Every number this module's results carry is about the SYNTHETIC IBM AML dataset this
  platform is built on. `SYNTHETIC_DATA_DISCLAIMER` exists so that fact is never dropped
  silently from a generated report -- see `build_temporal_entity_validation_report`.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit

SYNTHETIC_DATA_DISCLAIMER = (
    "All inputs to this report are drawn from IBM's published SYNTHETIC AML transaction dataset "
    "(github.com/IBM/AML-Data; Kaggle: ealtman2019/ibm-transactions-for-anti-money-laundering-aml). "
    "No real account, transaction, or financial institution is represented. Every number below is a "
    "real, reproducible computation against that synthetic data -- it is evidence about this "
    "platform's modeling methodology, not a claim about real-world AML detection performance, "
    "regulatory effectiveness, or production readiness."
)

__all__ = [
    "SYNTHETIC_DATA_DISCLAIMER",
    "chronological_split",
    "entity_aware_split",
    "cross_entity_overlap",
    "duplicate_record_check",
    "duplicate_overlap_across_split",
    "dataset_fingerprint",
    "environment_fingerprint",
    "majority_class_baseline",
    "random_stratified_baseline",
    "prevalence_baseline_pr_auc",
    "logistic_regression_baseline",
    "binary_threshold_metrics",
    "pr_auc",
    "roc_auc",
    "calibration_report",
    "threshold_tradeoff_table",
    "build_temporal_entity_validation_report",
    "render_markdown_report",
]


# ----------------------------------------------------------------------------------------
# Splits
# ----------------------------------------------------------------------------------------


def chronological_split(
    timestamps: Sequence | pd.Series, train_frac: float = 0.75
) -> tuple[np.ndarray, np.ndarray]:
    """Time-ordered split: train gets the earliest `train_frac` of rows by `timestamps`,
    test gets the rest -- the direct fix for Finding L-1 (every BP currently uses a
    random `train_test_split`, which can inflate reported performance relative to a real
    production scenario where a model only ever sees transactions chronologically after
    what it was trained on).

    Returns (train_idx, test_idx): 0-based positional index arrays, each already sorted
    chronologically ascending, referencing `timestamps` AFTER an internal
    `reset_index(drop=True)`. Apply them with `.iloc`, and make sure every array you slice
    with them (X, y, timestamps, entity columns) shares that same row order first -- these
    are positions, not label-based index values.

    Ties (identical timestamps) keep their original relative order (stable mergesort), so
    the split is deterministic for a given input order.
    """
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be strictly between 0 and 1")
    ts = pd.Series(timestamps).reset_index(drop=True)
    n = len(ts)
    if n < 2:
        raise ValueError("need at least 2 rows to split")
    order = np.argsort(ts.to_numpy(), kind="mergesort")
    n_train = min(max(int(round(n * train_frac)), 1), n - 1)
    return order[:n_train], order[n_train:]


def entity_aware_split(
    entity_ids: Sequence | pd.Series, test_frac: float = 0.25, random_state: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Group-aware split: no `entity_ids` value appears in both the returned train and
    test index sets -- the direct fix for Finding L-2 (no explicit entity/account-level
    separation found in any BP's split). Backed by scikit-learn's `GroupShuffleSplit`,
    which guarantees disjoint groups by construction (not by a post-hoc check).

    Returns (train_idx, test_idx): 0-based positional index arrays referencing
    `entity_ids` after an internal `reset_index(drop=True)`. `test_frac` is approximate --
    `GroupShuffleSplit` balances by group count, not row count, so a split with very
    unevenly-sized groups (e.g. a handful of accounts with huge transaction volumes) can
    land further from `test_frac` than a row-level split would.
    """
    ids = pd.Series(entity_ids).reset_index(drop=True)
    n = len(ids)
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=random_state)
    train_idx, test_idx = next(splitter.split(X=np.zeros((n, 1)), groups=ids.to_numpy()))
    return train_idx, test_idx


def cross_entity_overlap(
    train_entities: Iterable[Sequence], test_entities: Iterable[Sequence]
) -> dict[str, Any]:
    """Honest entity-leakage check for AML's two-sided sender/receiver structure, where a
    single `entity_aware_split` on one column (e.g. the sender `Account`) does not by
    itself guarantee the *receiver* (`Account.1`) side never leaks -- a test-set
    transaction's receiver can still be an account the model saw as a sender in training.

    `train_entities`/`test_entities`: one or more array-likes each (e.g. the sender and
    receiver entity columns for the train split, and the same two for the test split).
    Every value is cast to `str` before comparison (so an int and a string-typed account
    ID that represent the same account still match).

    Returns the count and fraction of unique test-side entities (union across every
    column passed in `test_entities`) that also appear anywhere in the train-side
    universe (union across every column passed in `train_entities`). A fraction of 0.0 is
    the honest "no entity leakage found by this check" result; it is not a guarantee no
    other form of leakage exists.
    """
    train_universe: set[str] = set()
    for col in train_entities:
        train_universe.update(pd.Series(col).astype(str).unique().tolist())
    test_universe: set[str] = set()
    for col in test_entities:
        test_universe.update(pd.Series(col).astype(str).unique().tolist())
    overlap = train_universe & test_universe
    n_test_unique = len(test_universe)
    return {
        "n_train_unique_entities": len(train_universe),
        "n_test_unique_entities": n_test_unique,
        "n_overlapping_entities": len(overlap),
        "overlap_fraction_of_test_entities": (len(overlap) / n_test_unique) if n_test_unique else 0.0,
    }


# ----------------------------------------------------------------------------------------
# Baselines -- "compare against appropriate baselines"
# ----------------------------------------------------------------------------------------


def majority_class_baseline(y_train: Sequence, y_test: Sequence) -> dict[str, Any]:
    """Predicts the single most common class in `y_train` for every test row. Binary- and
    multiclass-safe (so it applies to BP1/BP4/BP5's binary label and BP2's 5-class
    typology label alike). For a heavily imbalanced binary label (laundering is rare),
    expect this to report zero recall on the minority class by construction -- that is
    the correct, expected baseline result, not a bug."""
    y_train_s = pd.Series(y_train)
    y_test_arr = np.asarray(y_test)
    majority_class = y_train_s.mode().iloc[0]
    y_pred = np.full(len(y_test_arr), majority_class)
    return {
        "majority_class": majority_class,
        "accuracy": float(accuracy_score(y_test_arr, y_pred)),
        "macro_precision": float(precision_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_test_arr, y_pred, average="macro", zero_division=0)),
    }


def random_stratified_baseline(y_train: Sequence, y_test: Sequence, random_state: int = 42) -> dict[str, Any]:
    """Predicts a random label for every test row, drawn according to `y_train`'s own
    class distribution (not uniform at random) -- a slightly stronger, still-naive
    baseline than `majority_class_baseline`. Binary- and multiclass-safe."""
    rng = np.random.RandomState(random_state)
    y_train_s = pd.Series(y_train)
    counts = y_train_s.value_counts(normalize=True)
    classes = counts.index.to_numpy()
    probs = counts.to_numpy()
    y_test_arr = np.asarray(y_test)
    y_pred = rng.choice(classes, size=len(y_test_arr), p=probs)
    return {
        "accuracy": float(accuracy_score(y_test_arr, y_pred)),
        "macro_precision": float(precision_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_test_arr, y_pred, average="macro", zero_division=0)),
    }


def prevalence_baseline_pr_auc(y_test: Sequence) -> float:
    """The real, well-known no-skill PR-AUC for a binary classifier: a model with zero
    discriminative ability has an expected PR-AUC equal to the positive class's
    prevalence in `y_test`. Binary 0/1 labels only (BP1/BP4/BP5) -- raises on anything
    else rather than silently returning a meaningless number."""
    y_test_arr = np.asarray(y_test)
    unique = set(np.unique(y_test_arr).tolist())
    if not unique.issubset({0, 1}):
        raise ValueError("prevalence_baseline_pr_auc is defined for binary 0/1 labels only")
    return float(y_test_arr.mean())


def logistic_regression_baseline(
    X_train, y_train: Sequence, X_test, y_test: Sequence, max_iter: int = 500, random_state: int = 42
) -> dict[str, Any]:
    """A real, fitted, class-balanced logistic regression as a standard, non-trivial
    baseline to compare the champion model against (binary- and multiclass-safe). Adds
    `pr_auc` to the result when the label is binary 0/1."""
    model = LogisticRegression(max_iter=max_iter, random_state=random_state, class_weight="balanced")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_test_arr = np.asarray(y_test)
    result: dict[str, Any] = {
        "accuracy": float(accuracy_score(y_test_arr, y_pred)),
        "macro_precision": float(precision_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_test_arr, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_test_arr, y_pred, average="macro", zero_division=0)),
    }
    train_classes = set(np.unique(np.asarray(y_train)).tolist())
    if train_classes.issubset({0, 1}) and len(train_classes) == 2:
        positive_col = list(model.classes_).index(1)
        y_prob = model.predict_proba(X_test)[:, positive_col]
        result["pr_auc"] = pr_auc(y_test_arr, y_prob)
    return result


# ----------------------------------------------------------------------------------------
# Binary-classifier metrics -- "precision, recall, PR-AUC, calibration and threshold
# trade-offs" (BP1/BP4/BP5 only -- see module docstring)
# ----------------------------------------------------------------------------------------


def pr_auc(y_true: Sequence | np.ndarray, y_prob: Sequence | np.ndarray) -> float:
    """Area under the precision-recall curve (`sklearn.metrics.average_precision_score`)
    -- the primary metric this platform's own `MODEL_CARD.md`s already name for every
    binary BP, computed here against whichever split the caller built."""
    return float(average_precision_score(np.asarray(y_true), np.asarray(y_prob)))


def roc_auc(y_true: Sequence | np.ndarray, y_prob: Sequence | np.ndarray) -> float | None:
    """Area under the ROC curve (`sklearn.metrics.roc_auc_score`) -- reported alongside
    PR-AUC, never in place of it, since ROC-AUC is well known to look optimistic on the
    heavily imbalanced label AML detection always has (PR-AUC remains this platform's
    primary metric). Returns `None` (not a fabricated 0.5) when `y_true` has only one
    class present, since ROC-AUC is undefined in that case."""
    y_true_arr = np.asarray(y_true)
    if len(np.unique(y_true_arr)) < 2:
        return None
    return float(roc_auc_score(y_true_arr, np.asarray(y_prob)))


def binary_threshold_metrics(y_true: Sequence, y_prob: Sequence, threshold: float) -> dict[str, Any]:
    """Precision/recall/F1/alert-rate at one specific decision threshold, computed
    directly from the real confusion counts (not a library shortcut), so the four counts
    (tp/fp/tn/fn) are always visible alongside the derived rates."""
    y_true_arr = np.asarray(y_true)
    y_prob_arr = np.asarray(y_prob)
    y_pred = (y_prob_arr >= threshold).astype(int)
    tp = int(np.sum((y_pred == 1) & (y_true_arr == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true_arr == 0)))
    tn = int(np.sum((y_pred == 0) & (y_true_arr == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true_arr == 1)))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "alert_rate": float(np.mean(y_pred)),
        "alert_volume": int(tp + fp),
    }


def calibration_report(y_true: Sequence, y_prob: Sequence, n_bins: int = 10) -> dict[str, Any]:
    """Brier score (lower is better-calibrated; 0.0 is perfect) plus a real reliability
    curve (predicted-probability bins vs. actual observed positive fraction per bin) --
    the "calibration" half of the requested report. Falls back from quantile to uniform
    binning if the probability distribution is too concentrated for `n_bins` distinct
    quantile edges (common for a model producing many near-identical low scores)."""
    y_true_arr = np.asarray(y_true)
    y_prob_arr = np.asarray(y_prob)
    brier = float(brier_score_loss(y_true_arr, y_prob_arr))
    try:
        frac_pos, mean_pred = calibration_curve(y_true_arr, y_prob_arr, n_bins=n_bins, strategy="quantile")
    except ValueError:
        frac_pos, mean_pred = calibration_curve(y_true_arr, y_prob_arr, n_bins=n_bins, strategy="uniform")
    return {
        "brier_score": brier,
        "n_bins": int(len(frac_pos)),
        "bin_mean_predicted": [float(x) for x in mean_pred],
        "bin_fraction_positive": [float(x) for x in frac_pos],
    }


def threshold_tradeoff_table(
    y_true: Sequence,
    y_prob: Sequence,
    thresholds: Sequence[float] | None = None,
    production_threshold: float | None = None,
) -> pd.DataFrame:
    """A precision/recall/F1/alert-rate row per candidate decision threshold -- the
    "threshold trade-offs" half of the requested report, letting the already-selected
    production threshold be compared directly against nearby alternatives rather than
    taken on faith. Defaults to a 0.05-wide grid from 0.05 to 0.95; `production_threshold`
    (the BP's own real `selected_threshold` from its saved validation report) is always
    inserted as its own row, flagged in the `is_production_threshold` column, even if it
    falls between grid points."""
    if thresholds is None:
        thresholds = sorted(set(np.round(np.arange(0.05, 1.0, 0.05), 2).tolist()))
    else:
        thresholds = sorted(set(float(t) for t in thresholds))
    if production_threshold is not None:
        thresholds = sorted(set(thresholds) | {float(production_threshold)})
    rows = [binary_threshold_metrics(y_true, y_prob, t) for t in thresholds]
    table = pd.DataFrame(rows)
    if production_threshold is not None:
        table["is_production_threshold"] = np.isclose(table["threshold"], float(production_threshold))
    return table


# ----------------------------------------------------------------------------------------
# Data-quality and reproducibility helpers -- duplicate-record leakage, dataset
# fingerprinting, and environment capture (so a report says exactly what was run, against
# what data, on what code/library versions -- never just a bare number).
# ----------------------------------------------------------------------------------------


def duplicate_record_check(df: pd.DataFrame, key_columns: Sequence[str] | None = None) -> dict[str, Any]:
    """Honest duplicate-record check against a real (or synthetic-fixture) dataframe --
    "duplicate-record leakage" from the mandatory task list: if the same transaction (or
    its key fields) appears more than once in the raw data, a later random split can put
    one copy in train and the other in test, letting the model see what is effectively
    the exact same row on both sides. Reports both an exact full-row duplicate count and,
    when `key_columns` is given, a duplicate count on just those columns (e.g. every
    column except a near-unique transaction ID), which is usually the more meaningful
    check for AML transaction data. This function only counts and is deliberately silent
    about SPLIT ASSIGNMENT -- see `duplicate_overlap_across_split` for whether duplicates
    actually straddle a specific train/test partition."""
    n = len(df)
    exact_dup = int(df.duplicated(keep=False).sum())
    result: dict[str, Any] = {
        "n_rows": n,
        "n_exact_duplicate_rows": exact_dup,
        "exact_duplicate_fraction": (exact_dup / n) if n else 0.0,
    }
    if key_columns:
        cols = [c for c in key_columns if c in df.columns]
        key_dup = int(df.duplicated(subset=cols, keep=False).sum()) if cols else None
        result["key_columns_checked"] = cols
        result["n_key_duplicate_rows"] = key_dup
        result["key_duplicate_fraction"] = (key_dup / n) if (key_dup is not None and n) else None
    return result


def duplicate_overlap_across_split(
    df: pd.DataFrame,
    train_idx: Sequence[int] | np.ndarray,
    test_idx: Sequence[int] | np.ndarray,
    key_columns: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Whether any duplicate-key row group (per `duplicate_record_check`'s `key_columns`,
    or the full row if `key_columns` is omitted) has at least one copy in `train_idx` AND
    at least one copy in `test_idx` -- the concrete leakage event a duplicate-record
    count alone does not tell you. `train_idx`/`test_idx` are positional indices into
    `df` (as returned by this module's own `chronological_split`/`entity_aware_split`,
    or `sklearn.model_selection.train_test_split`'s own integer indices)."""
    cols = [c for c in key_columns if c in df.columns] if key_columns else list(df.columns)
    keys = df[cols].astype(str).agg("|".join, axis=1).to_numpy()
    train_keys = set(keys[np.asarray(train_idx)].tolist())
    test_keys = set(keys[np.asarray(test_idx)].tolist())
    straddling = train_keys & test_keys
    return {
        "key_columns_checked": cols,
        "n_unique_keys_straddling_split": len(straddling),
        "straddling_fraction_of_test_keys": (len(straddling) / len(test_keys)) if test_keys else 0.0,
    }


def dataset_fingerprint(df: pd.DataFrame, label: str = "") -> dict[str, Any]:
    """A reproducibility fingerprint for whatever real dataframe a notebook loaded --
    row/column counts, the column list, and a deterministic content hash
    (`pandas.util.hash_pandas_object`, summed and hex-encoded) so two runs can state
    plainly whether they saw the same data, without needing to diff the raw file."""
    row_hash = int(pd.util.hash_pandas_object(df, index=False).sum()) & 0xFFFFFFFFFFFFFFFF
    return {
        "label": label,
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "columns": list(df.columns),
        "content_hash_hex": f"{row_hash:016x}",
    }


def environment_fingerprint() -> dict[str, Any]:
    """Best-effort capture of the run environment -- Python version, platform, and the
    installed versions of this module's own real dependencies -- plus the current git
    commit when this code is running inside a git checkout (silently omitted, never
    fabricated, if `git` is unavailable or this is not a checkout)."""
    import numpy
    import pandas as _pd
    import sklearn

    info: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy_version": numpy.__version__,
        "pandas_version": _pd.__version__,
        "scikit_learn_version": sklearn.__version__,
    }
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
        info["git_commit"] = commit
    except Exception:
        info["git_commit"] = None
    return info


# ----------------------------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------------------------


def build_temporal_entity_validation_report(
    *,
    business_problem: str,
    dataset_variant: str,
    split_kind: str,
    y_test: Sequence,
    y_prob: Sequence | None = None,
    production_threshold: float | None = None,
    baselines: dict[str, dict[str, Any]] | None = None,
    entity_overlap: dict[str, Any] | None = None,
    duplicate_check: dict[str, Any] | None = None,
    dataset_fingerprints: dict[str, Any] | None = None,
    random_seed: int | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Assembles one structured report dict for a single (business_problem, dataset_variant,
    split_kind) run -- e.g. `("BP1", "LI-Medium", "chronological")`. `split_kind` is a
    free-text label the caller chooses (typically "chronological" or "entity-aware");
    this function does not compute the split itself. Every report carries
    `SYNTHETIC_DATA_DISCLAIMER` -- it is never left out, even if the caller forgets to
    mention it elsewhere. `dataset_fingerprints` (optional) is whatever dict of
    `dataset_fingerprint()` results the caller wants recorded (e.g. {"full_df": ...});
    `environment_fingerprint()` is always embedded automatically -- a report never omits
    it and a caller never has to remember to ask for it."""
    report: dict[str, Any] = {
        "business_problem": business_problem,
        "dataset_variant": dataset_variant,
        "split_kind": split_kind,
        "n_test": int(len(y_test)),
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
        "random_seed": random_seed,
        "environment": environment_fingerprint(),
    }
    if dataset_fingerprints:
        report["dataset_fingerprints"] = dataset_fingerprints
    if y_prob is not None:
        report["pr_auc"] = pr_auc(y_test, y_prob)
        report["roc_auc"] = roc_auc(y_test, y_prob)
        report["calibration"] = calibration_report(y_test, y_prob)
        tradeoff = threshold_tradeoff_table(y_test, y_prob, production_threshold=production_threshold)
        report["threshold_tradeoff"] = tradeoff.to_dict(orient="records")
        if production_threshold is not None:
            report["production_threshold_metrics"] = binary_threshold_metrics(
                y_test, y_prob, production_threshold
            )
        report["prevalence_baseline_pr_auc"] = prevalence_baseline_pr_auc(y_test)
    if baselines:
        report["baselines"] = baselines
    if entity_overlap:
        report["entity_overlap"] = entity_overlap
    if duplicate_check:
        report["duplicate_check"] = duplicate_check
    if notes:
        report["notes"] = notes
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    """Renders a report dict from `build_temporal_entity_validation_report` as a
    standalone markdown document, always leading with the synthetic-data disclaimer."""
    bp = report.get("business_problem", "?")
    variant = report.get("dataset_variant", "?")
    split_kind = report.get("split_kind", "?")
    lines = [
        f"# Temporal/Entity-Separated Validation -- {bp} ({variant}, {split_kind} split)",
        "",
        f"> {report.get('disclaimer', SYNTHETIC_DATA_DISCLAIMER)}",
        "",
        f"- n_test: {report.get('n_test')}",
    ]
    if "pr_auc" in report:
        lines.append(f"- PR-AUC: {report['pr_auc']:.4f}")
    if report.get("roc_auc") is not None:
        lines.append(f"- ROC-AUC: {report['roc_auc']:.4f} (reported alongside PR-AUC, never in place of it)")
    if "prevalence_baseline_pr_auc" in report:
        lines.append(f"- No-skill (prevalence) baseline PR-AUC: {report['prevalence_baseline_pr_auc']:.4f}")
    if "production_threshold_metrics" in report:
        m = report["production_threshold_metrics"]
        lines.append(
            f"- At the production threshold ({m['threshold']:.4f}): precision={m['precision']:.4f}, "
            f"recall={m['recall']:.4f}, f1={m['f1']:.4f}, fpr={m['fpr']:.4f}, "
            f"alert_rate={m['alert_rate']:.4f}, alert_volume={m['alert_volume']} "
            f"(tp={m['tp']}, fp={m['fp']}, tn={m['tn']}, fn={m['fn']})"
        )
    if "calibration" in report:
        lines.append(
            f"- Brier score: {report['calibration']['brier_score']:.4f} (0.0 = perfectly calibrated)"
        )
    if report.get("random_seed") is not None:
        lines.append(f"- Random seed: {report['random_seed']}")
    if "environment" in report:
        env = report["environment"]
        lines.append(
            f"- Environment: Python {env.get('python_version')}, "
            f"numpy {env.get('numpy_version')}, pandas {env.get('pandas_version')}, "
            f"scikit-learn {env.get('scikit_learn_version')}"
            + (f", git commit {env['git_commit']}" if env.get("git_commit") else "")
        )
    if "dataset_fingerprints" in report:
        lines += ["", "## Dataset fingerprints"]
        for name, fp in report["dataset_fingerprints"].items():
            lines.append(
                f"- **{name}**: {fp.get('n_rows')} rows x {fp.get('n_columns')} cols, "
                f"content hash `{fp.get('content_hash_hex')}`"
            )
    if "duplicate_check" in report:
        d = report["duplicate_check"]
        lines += ["", "## Duplicate-record check"]
        lines.append(
            f"- Exact duplicate rows: {d.get('n_exact_duplicate_rows')} "
            f"({d.get('exact_duplicate_fraction', 0):.6%} of {d.get('n_rows')} rows)"
        )
        if d.get("n_key_duplicate_rows") is not None:
            lines.append(
                f"- Duplicate rows on key columns {d.get('key_columns_checked')}: "
                f"{d['n_key_duplicate_rows']} ({d.get('key_duplicate_fraction', 0):.6%})"
            )

    if "baselines" in report:
        lines += ["", "## Baselines"]
        for name, vals in report["baselines"].items():
            rendered = ", ".join(
                f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in vals.items()
            )
            lines.append(f"- **{name}**: {rendered}")

    if "entity_overlap" in report:
        lines += ["", "## Entity overlap (Finding L-2 check)"]
        for k, v in report["entity_overlap"].items():
            lines.append(f"- {k}: {v}")

    if "threshold_tradeoff" in report:
        lines += [
            "",
            "## Threshold trade-off table",
            "",
            "| threshold | precision | recall | f1 | alert_rate | production? |",
            "|---|---|---|---|---|---|",
        ]
        for row in report["threshold_tradeoff"]:
            flag = "yes" if row.get("is_production_threshold") else ""
            lines.append(
                f"| {row['threshold']:.3f} | {row['precision']:.4f} | {row['recall']:.4f} | "
                f"{row['f1']:.4f} | {row['alert_rate']:.4f} | {flag} |"
            )

    if report.get("notes"):
        lines += ["", "## Notes"]
        for note in report["notes"]:
            lines.append(f"- {note}")

    return "\n".join(lines) + "\n"
