"""
Input/data-quality monitoring and retraining-trigger logic -- added 2026-10-12 (Improvement
3, production-readiness pass) to close a real, disclosed gap in `monitoring/drift_monitor.py`:
that module already provides a real, tested PSI implementation for SCORE-distribution drift
(see its own docstring and `MONITORING.md`), but nothing in this platform checked the
INPUT side -- whether an incoming batch of real feature data is even well-formed, how much of
it is missing, whether it has drifted out of the range the model was trained on, or whether a
single FEATURE column's own distribution has shifted (as opposed to the model's output score,
which is a different, downstream signal). This module is the input-side counterpart.

Design discipline, matching `drift_monitor.py`'s own: every function here is a pure,
synthetic-fixture-testable function over real pandas/numpy data the caller supplies -- never
a live, continuously-running service, never a fabricated number. See `MONITORING.md`'s
"What this is NOT (yet)" section for the same honest scope note applied to this module.

SYNTHETIC-DATA LIMITATION (stated once, here, for every function in this module): this
platform's underlying dataset is IBM's synthetic AML transaction data (see `DATA_PRIVACY.md`),
and there is no real production traffic to compare against. Every "baseline" this module's
functions compare a "current" batch to is, in this platform's own real usage, itself a
synthetic-data baseline (e.g. a notebook's own held-out test split) -- never a real live
production feed. A caller of this module is responsible for carrying that distinction into
whatever report it produces (see `build_input_quality_report`'s own `baseline_is_synthetic`
field, which is never silently defaulted to False); this module does not and cannot detect on
its own whether the data it is given is real or synthetic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .drift_monitor import PSI_MODERATE_SHIFT_MAX, PSI_NO_SHIFT_MAX, compute_psi

# Default alert-volume anomaly thresholds -- a ratio of current-period alert count to the
# baseline period's, NOT an absolute count (an absolute count is meaningless without knowing
# the real transaction volume that produced it, which this module does not assume access
# to). These are deliberately the same kind of "disclosed, not fabricated" convention as
# drift_monitor.py's PSI bands: a ratio outside [0.5x, 2x] of baseline is the standard
# starting point for "something changed enough to look at" in alert-volume monitoring
# (a sudden halving or doubling of alert volume, with no corresponding change in underlying
# transaction volume, is the real-world signal this threshold exists to catch), not a
# platform-specific invention.
ALERT_VOLUME_RATIO_LOW = 0.5
ALERT_VOLUME_RATIO_HIGH = 2.0


def validate_input_schema(
    df: pd.DataFrame, expected_columns: list[str], expected_dtypes: dict[str, str] | None = None
) -> dict[str, Any]:
    """Real, synchronous schema check -- confirms every column in `expected_columns` is
    present (reports exactly which are missing, never a generic "schema invalid"), flags any
    EXTRA column `df` has that `expected_columns` does not list (informational, not a
    failure -- an upstream producer adding a column is usually benign), and, when
    `expected_dtypes` ({column: pandas-dtype-name}) is given, confirms each listed column's
    real `dtype` matches (reported, not coerced -- this function never silently casts data)."""
    actual_columns = list(df.columns)
    missing_columns = [c for c in expected_columns if c not in actual_columns]
    extra_columns = [c for c in actual_columns if c not in expected_columns]
    dtype_mismatches: dict[str, dict[str, str]] = {}
    if expected_dtypes:
        for col, expected_dtype in expected_dtypes.items():
            if col in df.columns:
                actual_dtype = str(df[col].dtype)
                if actual_dtype != expected_dtype:
                    dtype_mismatches[col] = {"expected": expected_dtype, "actual": actual_dtype}
    is_valid = len(missing_columns) == 0 and len(dtype_mismatches) == 0
    return {
        "is_valid": is_valid,
        "n_rows": int(len(df)),
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "dtype_mismatches": dtype_mismatches,
    }


def missing_value_report(df: pd.DataFrame, columns: list[str] | None = None) -> dict[str, Any]:
    """Real per-column missing-value rate (NaN/None/NaT via pandas' own `isna()`, not a
    hand-rolled definition of "missing") over `columns` (defaults to every column in `df`).
    Raises on an empty DataFrame rather than silently reporting 0% missing everywhere, which
    would be a meaningless, misleadingly "clean" result for data that was never actually
    checked."""
    if len(df) == 0:
        raise ValueError(
            "missing_value_report requires a non-empty DataFrame -- a 0-row "
            "input has no real missing-value rate to report."
        )
    cols = columns if columns is not None else list(df.columns)
    per_column: dict[str, dict[str, Any]] = {}
    for col in cols:
        if col not in df.columns:
            per_column[col] = {"present": False}
            continue
        n_missing = int(df[col].isna().sum())
        per_column[col] = {
            "present": True,
            "n_missing": n_missing,
            "missing_fraction": n_missing / len(df),
        }
    worst = max(
        (v["missing_fraction"] for v in per_column.values() if v.get("present")),
        default=0.0,
    )
    return {"n_rows": int(len(df)), "per_column": per_column, "max_missing_fraction": worst}


def out_of_range_report(
    df: pd.DataFrame, baseline: pd.DataFrame, columns: list[str], *, baseline_quantile: float = 0.01
) -> dict[str, Any]:
    """Real out-of-range check: for each numeric column in `columns`, derives [low, high]
    bounds from `baseline`'s own real `baseline_quantile` / `1 - baseline_quantile`
    quantiles (e.g. the 1st/99th percentile with the default), then reports the fraction of
    `df`'s rows falling outside that real range -- never a hardcoded, feature-agnostic bound,
    since a reasonable range for one feature column (e.g. an hour-of-day column, [0, 23]) is
    meaningless for another (e.g. a dollar amount). A column with zero spread in `baseline`
    (every value identical) is reported with `bounds_degenerate: True` rather than silently
    treated as "everything is out of range" or "nothing is"."""
    per_column: dict[str, dict[str, Any]] = {}
    for col in columns:
        if col not in df.columns or col not in baseline.columns:
            per_column[col] = {"present_in_both": False}
            continue
        baseline_values = baseline[col].dropna().to_numpy(dtype="float64")
        if len(baseline_values) == 0:
            per_column[col] = {"present_in_both": True, "baseline_empty": True}
            continue
        low = float(np.quantile(baseline_values, baseline_quantile))
        high = float(np.quantile(baseline_values, 1.0 - baseline_quantile))
        current_values = df[col].dropna().to_numpy(dtype="float64")
        if low == high:
            per_column[col] = {
                "present_in_both": True,
                "bounds_degenerate": True,
                "bound_low": low,
                "bound_high": high,
            }
            continue
        if len(current_values) == 0:
            fraction_out_of_range = 0.0
        else:
            out_of_range = (current_values < low) | (current_values > high)
            fraction_out_of_range = float(out_of_range.mean())
        per_column[col] = {
            "present_in_both": True,
            "bounds_degenerate": False,
            "bound_low": low,
            "bound_high": high,
            "fraction_out_of_range": fraction_out_of_range,
        }
    worst = max(
        (
            v["fraction_out_of_range"]
            for v in per_column.values()
            if v.get("present_in_both") and not v.get("bounds_degenerate")
        ),
        default=0.0,
    )
    return {
        "baseline_quantile": baseline_quantile,
        "per_column": per_column,
        "max_fraction_out_of_range": worst,
    }


def feature_drift_report(
    df: pd.DataFrame, baseline: pd.DataFrame, columns: list[str], *, n_bins: int = 10
) -> dict[str, Any]:
    """Per-FEATURE-column drift, reusing `drift_monitor.compute_psi` exactly as-is (PSI is a
    distribution-comparison statistic -- it does not care semantically whether the values it
    is given are model output scores or a raw feature column, so this is intentionally NOT a
    reimplementation, just a different, honest application of the same real, tested
    function). This is the FEATURE-side complement to drift_monitor.py's own SCORE-side PSI
    (already wired into BP1's own Notebook 3) -- distinct signals: a feature can drift while
    the model's score distribution happens to stay stable (if the drift is in a
    low-importance feature), and vice versa."""
    per_column: dict[str, Any] = {}
    for col in columns:
        if col not in df.columns or col not in baseline.columns:
            per_column[col] = {"present_in_both": False}
            continue
        baseline_values = baseline[col].dropna().to_numpy(dtype="float64")
        current_values = df[col].dropna().to_numpy(dtype="float64")
        if len(baseline_values) == 0 or len(current_values) == 0:
            per_column[col] = {"present_in_both": True, "insufficient_data": True}
            continue
        try:
            psi_result = compute_psi(baseline_values, current_values, n_bins=n_bins)
        except ValueError as exc:
            per_column[col] = {"present_in_both": True, "insufficient_data": True, "reason": str(exc)}
            continue
        per_column[col] = {
            "present_in_both": True,
            "insufficient_data": False,
            "psi": psi_result["psi"],
            "verdict": psi_result["verdict"],
        }
    significant = [col for col, v in per_column.items() if v.get("verdict") == "significant_shift"]
    return {"per_column": per_column, "columns_with_significant_shift": significant}


def alert_volume_report(current_period_alert_count: int, baseline_period_alert_count: int) -> dict[str, Any]:
    """Real alert-volume ratio check -- see this module's docstring for why this is a RATIO
    to a baseline period, not an absolute count. `baseline_period_alert_count == 0` is a real,
    disclosed edge case (no baseline to compare against) rather than a division-by-zero
    crash or a silently fabricated ratio."""
    if baseline_period_alert_count == 0:
        return {
            "current_period_alert_count": current_period_alert_count,
            "baseline_period_alert_count": 0,
            "ratio": None,
            "verdict": "no_baseline",
        }
    ratio = current_period_alert_count / baseline_period_alert_count
    if ratio < ALERT_VOLUME_RATIO_LOW:
        verdict = "anomalously_low"
    elif ratio > ALERT_VOLUME_RATIO_HIGH:
        verdict = "anomalously_high"
    else:
        verdict = "normal_range"
    return {
        "current_period_alert_count": current_period_alert_count,
        "baseline_period_alert_count": baseline_period_alert_count,
        "ratio": ratio,
        "verdict": verdict,
    }


def recommend_retraining_review(
    *,
    schema_result: dict[str, Any] | None = None,
    missing_value_result: dict[str, Any] | None = None,
    out_of_range_result: dict[str, Any] | None = None,
    feature_drift_result: dict[str, Any] | None = None,
    score_psi_verdict: str | None = None,
    alert_volume_result: dict[str, Any] | None = None,
    missing_value_fraction_trigger: float = 0.10,
    out_of_range_fraction_trigger: float = 0.05,
) -> dict[str, Any]:
    """Documented retraining/revalidation TRIGGER logic (requirement: "documented retraining
    and revalidation triggers") -- a transparent, explainable rule combining whichever of
    this module's (and drift_monitor.py's) reports the caller has available. Every argument
    is optional so a caller with only some signals (e.g. no baseline for out-of-range
    checking) still gets a real recommendation from what it does have, with
    `missing_signals` disclosing exactly what was not considered -- never silently treated
    as "passing". This function makes a RECOMMENDATION, not an automated action: it never
    retrains or revalidates anything itself."""
    reasons: list[str] = []
    missing_signals: list[str] = []

    if schema_result is not None:
        if not schema_result.get("is_valid", True):
            reasons.append(
                "input schema invalid: missing_columns="
                f"{schema_result.get('missing_columns')}, "
                f"dtype_mismatches={schema_result.get('dtype_mismatches')}"
            )
    else:
        missing_signals.append("schema_result")

    if missing_value_result is not None:
        worst = missing_value_result.get("max_missing_fraction", 0.0)
        if worst > missing_value_fraction_trigger:
            reasons.append(
                f"missing-value rate {worst:.1%} exceeds trigger {missing_value_fraction_trigger:.1%}"
            )
    else:
        missing_signals.append("missing_value_result")

    if out_of_range_result is not None:
        worst = out_of_range_result.get("max_fraction_out_of_range", 0.0)
        if worst > out_of_range_fraction_trigger:
            reasons.append(
                f"out-of-range rate {worst:.1%} exceeds trigger {out_of_range_fraction_trigger:.1%}"
            )
    else:
        missing_signals.append("out_of_range_result")

    if feature_drift_result is not None:
        shifted = feature_drift_result.get("columns_with_significant_shift", [])
        if shifted:
            reasons.append(f"significant feature drift in columns: {shifted}")
    else:
        missing_signals.append("feature_drift_result")

    if score_psi_verdict is not None:
        if score_psi_verdict == "significant_shift":
            reasons.append("score-distribution PSI verdict is significant_shift")
    else:
        missing_signals.append("score_psi_verdict")

    if alert_volume_result is not None:
        verdict = alert_volume_result.get("verdict")
        if verdict in ("anomalously_low", "anomalously_high"):
            reasons.append(f"alert-volume ratio verdict is {verdict}")
    else:
        missing_signals.append("alert_volume_result")

    return {
        "recommend_review": len(reasons) > 0,
        "reasons": reasons,
        "missing_signals": missing_signals,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_input_quality_report(
    *,
    bp_id: str,
    schema_result: dict[str, Any],
    missing_value_result: dict[str, Any],
    out_of_range_result: dict[str, Any] | None = None,
    feature_drift_result: dict[str, Any] | None = None,
    baseline_is_synthetic: bool,
) -> dict[str, Any]:
    """Assembles a single, machine-readable + human-reportable input-quality record for one
    BP. `baseline_is_synthetic` is REQUIRED (no default) -- see this module's docstring: a
    caller must explicitly state whether the baseline being compared against is this
    platform's own synthetic-dataset baseline (true for every real use of this module in this
    repository today) or a genuine live-production baseline, so this report can never be
    silently mistaken for production monitoring evidence."""
    return {
        "bp_id": bp_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_is_synthetic": baseline_is_synthetic,
        "schema": schema_result,
        "missing_values": missing_value_result,
        "out_of_range": out_of_range_result,
        "feature_drift": feature_drift_result,
    }


__all__ = [
    "PSI_NO_SHIFT_MAX",
    "PSI_MODERATE_SHIFT_MAX",
    "ALERT_VOLUME_RATIO_LOW",
    "ALERT_VOLUME_RATIO_HIGH",
    "validate_input_schema",
    "missing_value_report",
    "out_of_range_report",
    "feature_drift_report",
    "alert_volume_report",
    "recommend_retraining_review",
    "build_input_quality_report",
]
