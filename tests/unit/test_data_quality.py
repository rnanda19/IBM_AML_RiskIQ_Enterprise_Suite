"""Unit tests for src/aml_riskiq/monitoring/data_quality.py -- the new input-schema,
data-quality, feature-drift, alert-volume, and retraining-trigger module added 2026-10-12
(Improvement 3, production-readiness pass). All synthetic fixtures, per this project's
standing execution-boundary rule."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC_PATH = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from monitoring.data_quality import (  # noqa: E402
    alert_volume_report,
    build_input_quality_report,
    feature_drift_report,
    missing_value_report,
    out_of_range_report,
    recommend_retraining_review,
    validate_input_schema,
)

# -- validate_input_schema ---------------------------------------------------------------


def test_schema_valid_when_all_expected_columns_present():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = validate_input_schema(df, expected_columns=["a", "b"])
    assert result["is_valid"] is True
    assert result["missing_columns"] == []


def test_schema_reports_missing_columns():
    df = pd.DataFrame({"a": [1, 2]})
    result = validate_input_schema(df, expected_columns=["a", "b", "c"])
    assert result["is_valid"] is False
    assert result["missing_columns"] == ["b", "c"]


def test_schema_reports_extra_columns_without_failing():
    df = pd.DataFrame({"a": [1], "b": [2], "unexpected": [3]})
    result = validate_input_schema(df, expected_columns=["a", "b"])
    assert result["is_valid"] is True
    assert result["extra_columns"] == ["unexpected"]


def test_schema_detects_dtype_mismatch():
    df = pd.DataFrame({"a": ["not", "numbers"]})
    result = validate_input_schema(df, expected_columns=["a"], expected_dtypes={"a": "float64"})
    assert result["is_valid"] is False
    assert "a" in result["dtype_mismatches"]
    assert result["dtype_mismatches"]["a"]["actual"] == "object"


def test_schema_dtype_match_passes():
    df = pd.DataFrame({"a": np.array([1.0, 2.0], dtype="float64")})
    result = validate_input_schema(df, expected_columns=["a"], expected_dtypes={"a": "float64"})
    assert result["is_valid"] is True


# -- missing_value_report ------------------------------------------------------------------


def test_missing_value_report_counts_real_nans():
    df = pd.DataFrame({"a": [1.0, np.nan, 3.0, np.nan]})
    result = missing_value_report(df)
    assert result["per_column"]["a"]["n_missing"] == 2
    assert result["per_column"]["a"]["missing_fraction"] == 0.5
    assert result["max_missing_fraction"] == 0.5


def test_missing_value_report_zero_when_complete():
    df = pd.DataFrame({"a": [1, 2, 3]})
    result = missing_value_report(df)
    assert result["per_column"]["a"]["missing_fraction"] == 0.0


def test_missing_value_report_raises_on_empty_dataframe():
    with pytest.raises(ValueError, match="non-empty"):
        missing_value_report(pd.DataFrame({"a": []}))


def test_missing_value_report_flags_absent_column():
    df = pd.DataFrame({"a": [1, 2]})
    result = missing_value_report(df, columns=["a", "nonexistent"])
    assert result["per_column"]["nonexistent"]["present"] is False


# -- out_of_range_report --------------------------------------------------------------------


def test_out_of_range_report_flags_real_outliers():
    baseline = pd.DataFrame({"amount": np.linspace(0, 100, 1000)})
    current = pd.DataFrame({"amount": [50.0, 99999.0, 60.0, -99999.0]})
    result = out_of_range_report(current, baseline, columns=["amount"], baseline_quantile=0.01)
    assert result["per_column"]["amount"]["fraction_out_of_range"] == 0.5  # 2 of 4 rows


def test_out_of_range_report_zero_when_within_bounds():
    baseline = pd.DataFrame({"amount": np.linspace(0, 100, 1000)})
    current = pd.DataFrame({"amount": [10.0, 20.0, 30.0]})
    result = out_of_range_report(current, baseline, columns=["amount"])
    assert result["per_column"]["amount"]["fraction_out_of_range"] == 0.0


def test_out_of_range_report_handles_degenerate_baseline():
    baseline = pd.DataFrame({"flag": [1.0] * 100})
    current = pd.DataFrame({"flag": [1.0, 0.0]})
    result = out_of_range_report(current, baseline, columns=["flag"])
    assert result["per_column"]["flag"]["bounds_degenerate"] is True


def test_out_of_range_report_handles_missing_column():
    baseline = pd.DataFrame({"a": [1.0, 2.0]})
    current = pd.DataFrame({"b": [1.0, 2.0]})
    result = out_of_range_report(current, baseline, columns=["a"])
    assert result["per_column"]["a"]["present_in_both"] is False


# -- feature_drift_report (reuses drift_monitor.compute_psi) -------------------------------


def test_feature_drift_report_detects_shift():
    rng = np.random.RandomState(7)
    baseline = pd.DataFrame({"x": rng.normal(0.2, 0.05, size=5000)})
    current = pd.DataFrame({"x": rng.normal(0.8, 0.05, size=5000)})
    result = feature_drift_report(current, baseline, columns=["x"])
    assert result["per_column"]["x"]["verdict"] == "significant_shift"
    assert "x" in result["columns_with_significant_shift"]


def test_feature_drift_report_no_shift_for_identical_distribution():
    rng = np.random.RandomState(8)
    values = rng.uniform(0, 1, size=3000)
    baseline = pd.DataFrame({"x": values})
    current = pd.DataFrame({"x": values.copy()})
    result = feature_drift_report(current, baseline, columns=["x"])
    assert result["per_column"]["x"]["verdict"] == "no_shift"
    assert result["columns_with_significant_shift"] == []


def test_feature_drift_report_handles_insufficient_data():
    baseline = pd.DataFrame({"x": [np.nan, np.nan]})
    current = pd.DataFrame({"x": [1.0, 2.0]})
    result = feature_drift_report(current, baseline, columns=["x"])
    assert result["per_column"]["x"]["insufficient_data"] is True


# -- alert_volume_report --------------------------------------------------------------------


def test_alert_volume_normal_range():
    result = alert_volume_report(current_period_alert_count=100, baseline_period_alert_count=100)
    assert result["verdict"] == "normal_range"
    assert result["ratio"] == 1.0


def test_alert_volume_anomalously_high():
    result = alert_volume_report(current_period_alert_count=300, baseline_period_alert_count=100)
    assert result["verdict"] == "anomalously_high"


def test_alert_volume_anomalously_low():
    result = alert_volume_report(current_period_alert_count=10, baseline_period_alert_count=100)
    assert result["verdict"] == "anomalously_low"


def test_alert_volume_no_baseline():
    result = alert_volume_report(current_period_alert_count=5, baseline_period_alert_count=0)
    assert result["verdict"] == "no_baseline"
    assert result["ratio"] is None


# -- recommend_retraining_review ------------------------------------------------------------


def test_recommend_retraining_review_no_signals_at_all_recommends_nothing():
    result = recommend_retraining_review()
    assert result["recommend_review"] is False
    assert set(result["missing_signals"]) == {
        "schema_result",
        "missing_value_result",
        "out_of_range_result",
        "feature_drift_result",
        "score_psi_verdict",
        "alert_volume_result",
    }


def test_recommend_retraining_review_flags_invalid_schema():
    result = recommend_retraining_review(schema_result={"is_valid": False, "missing_columns": ["x"]})
    assert result["recommend_review"] is True
    assert "schema" in result["reasons"][0]


def test_recommend_retraining_review_flags_high_missing_rate():
    result = recommend_retraining_review(
        missing_value_result={"max_missing_fraction": 0.5}, missing_value_fraction_trigger=0.10
    )
    assert result["recommend_review"] is True


def test_recommend_retraining_review_does_not_flag_low_missing_rate():
    result = recommend_retraining_review(
        missing_value_result={"max_missing_fraction": 0.01}, missing_value_fraction_trigger=0.10
    )
    assert result["recommend_review"] is False


def test_recommend_retraining_review_flags_significant_score_drift():
    result = recommend_retraining_review(score_psi_verdict="significant_shift")
    assert result["recommend_review"] is True


def test_recommend_retraining_review_flags_alert_volume_anomaly():
    result = recommend_retraining_review(alert_volume_result={"verdict": "anomalously_high"})
    assert result["recommend_review"] is True


def test_recommend_retraining_review_combines_multiple_reasons():
    result = recommend_retraining_review(
        score_psi_verdict="significant_shift",
        alert_volume_result={"verdict": "anomalously_low"},
    )
    assert len(result["reasons"]) == 2


# -- build_input_quality_report --------------------------------------------------------------


def test_build_input_quality_report_requires_explicit_synthetic_flag():
    report = build_input_quality_report(
        bp_id="BP1",
        schema_result={"is_valid": True},
        missing_value_result={"max_missing_fraction": 0.0},
        baseline_is_synthetic=True,
    )
    assert report["baseline_is_synthetic"] is True
    assert report["bp_id"] == "BP1"


def test_build_input_quality_report_marks_real_baseline_when_told_to():
    report = build_input_quality_report(
        bp_id="BP1",
        schema_result={"is_valid": True},
        missing_value_result={"max_missing_fraction": 0.0},
        baseline_is_synthetic=False,
    )
    assert report["baseline_is_synthetic"] is False
