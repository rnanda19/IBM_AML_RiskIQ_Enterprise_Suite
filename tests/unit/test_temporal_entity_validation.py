"""Tests for src/aml_riskiq/validation/temporal_entity_validation.py -- the reusable
chronological/entity-aware re-validation helpers added 2026-10-12 in response to
docs/data/LEAKAGE_AUDIT.md's Findings L-1/L-2. Every test here uses small, synthetic,
in-memory fixtures (never the real IBM AML dataset) -- this validates the LIBRARY code's
own correctness, which is independent of what the real dataset would show when a real
notebook imports and runs it."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from validation.temporal_entity_validation import (  # noqa: E402
    SYNTHETIC_DATA_DISCLAIMER,
    binary_threshold_metrics,
    build_temporal_entity_validation_report,
    calibration_report,
    chronological_split,
    cross_entity_overlap,
    dataset_fingerprint,
    duplicate_overlap_across_split,
    duplicate_record_check,
    entity_aware_split,
    environment_fingerprint,
    logistic_regression_baseline,
    majority_class_baseline,
    pr_auc,
    prevalence_baseline_pr_auc,
    random_stratified_baseline,
    render_markdown_report,
    roc_auc,
    threshold_tradeoff_table,
)

# ----------------------------------------------------------------------------------------
# chronological_split
# ----------------------------------------------------------------------------------------


def test_chronological_split_train_is_earliest_regardless_of_row_order():
    # 20 timestamps, deliberately shuffled in the input Series -- the split must still
    # put the 15 earliest (by actual time) in train, not the first 15 rows as given.
    rng = np.random.RandomState(0)
    base = pd.date_range("2026-01-01", periods=20, freq="h")
    shuffle = rng.permutation(20)
    shuffled_ts = pd.Series(base[shuffle])

    train_idx, test_idx = chronological_split(shuffled_ts, train_frac=0.75)

    assert len(train_idx) == 15
    assert len(test_idx) == 5
    assert set(train_idx.tolist()) | set(test_idx.tolist()) == set(range(20))
    train_times = shuffled_ts.iloc[train_idx]
    test_times = shuffled_ts.iloc[test_idx]
    assert train_times.max() <= test_times.min()


def test_chronological_split_ties_keep_original_order():
    ts = pd.Series(pd.to_datetime(["2026-01-01"] * 4))
    train_idx, test_idx = chronological_split(ts, train_frac=0.5)
    # All timestamps tied -- stable sort means train gets positions [0, 1], test [2, 3].
    assert train_idx.tolist() == [0, 1]
    assert test_idx.tolist() == [2, 3]


@pytest.mark.parametrize("bad_frac", [0.0, 1.0, -0.1, 1.5])
def test_chronological_split_rejects_bad_train_frac(bad_frac):
    ts = pd.Series(pd.date_range("2026-01-01", periods=5, freq="D"))
    with pytest.raises(ValueError):
        chronological_split(ts, train_frac=bad_frac)


def test_chronological_split_requires_at_least_two_rows():
    with pytest.raises(ValueError):
        chronological_split(pd.Series(pd.to_datetime(["2026-01-01"])), train_frac=0.5)


# ----------------------------------------------------------------------------------------
# entity_aware_split / cross_entity_overlap
# ----------------------------------------------------------------------------------------


def test_entity_aware_split_has_no_overlapping_entities():
    # 10 accounts, each with several transactions -- total 60 rows.
    rng = np.random.RandomState(1)
    accounts = [f"acct-{i}" for i in range(10)]
    entity_ids = pd.Series(rng.choice(accounts, size=60))

    train_idx, test_idx = entity_aware_split(entity_ids, test_frac=0.3, random_state=1)

    train_entities = set(entity_ids.iloc[train_idx].unique())
    test_entities = set(entity_ids.iloc[test_idx].unique())
    assert train_entities.isdisjoint(test_entities)
    assert len(train_idx) + len(test_idx) == 60


def test_cross_entity_overlap_detects_a_known_overlap():
    train_entities = [pd.Series(["a", "b", "c"]), pd.Series(["x", "y"])]
    # "c" (a sender in train) reappears as a receiver in test -- real cross-side leakage.
    test_entities = [pd.Series(["c", "d"]), pd.Series(["y", "z"])]

    result = cross_entity_overlap(train_entities, test_entities)

    assert result["n_train_unique_entities"] == 5  # a, b, c, x, y
    assert result["n_test_unique_entities"] == 4  # c, d, y, z
    assert result["n_overlapping_entities"] == 2  # c, y
    assert result["overlap_fraction_of_test_entities"] == pytest.approx(0.5)


def test_cross_entity_overlap_zero_when_disjoint():
    result = cross_entity_overlap([pd.Series(["a", "b"])], [pd.Series(["c", "d"])])
    assert result["n_overlapping_entities"] == 0
    assert result["overlap_fraction_of_test_entities"] == 0.0


# ----------------------------------------------------------------------------------------
# Baselines
# ----------------------------------------------------------------------------------------


def test_majority_class_baseline_binary_imbalanced():
    y_train = [0] * 90 + [1] * 10
    y_test = [0] * 18 + [1] * 2  # same 90/10 imbalance held out

    result = majority_class_baseline(y_train, y_test)

    assert result["majority_class"] == 0
    assert result["accuracy"] == pytest.approx(0.9)
    # Always predicting 0 means zero recall on the positive (minority) class -- by
    # construction, not a bug -- which drags macro recall down to 0.5 (perfect on class 0,
    # zero on class 1).
    assert result["macro_recall"] == pytest.approx(0.5)


def test_majority_class_baseline_is_multiclass_safe():
    y_train = [0, 0, 0, 1, 2]
    y_test = [0, 0, 1, 2]

    result = majority_class_baseline(y_train, y_test)

    assert result["majority_class"] == 0
    assert 0.0 <= result["accuracy"] <= 1.0


def test_random_stratified_baseline_is_reproducible_and_shaped_correctly():
    y_train = [0] * 70 + [1] * 30
    y_test = [0] * 20 + [1] * 10

    r1 = random_stratified_baseline(y_train, y_test, random_state=7)
    r2 = random_stratified_baseline(y_train, y_test, random_state=7)

    assert r1 == r2  # same random_state -> identical result
    assert set(r1.keys()) == {"accuracy", "macro_precision", "macro_recall", "macro_f1"}


def test_prevalence_baseline_pr_auc_matches_positive_rate():
    y_test = [0] * 80 + [1] * 20
    assert prevalence_baseline_pr_auc(y_test) == pytest.approx(0.2)


def test_prevalence_baseline_pr_auc_rejects_non_binary_labels():
    with pytest.raises(ValueError):
        prevalence_baseline_pr_auc([0, 1, 2])


def test_logistic_regression_baseline_binary_includes_pr_auc():
    rng = np.random.RandomState(2)
    X_train = rng.normal(size=(200, 3))
    y_train = (X_train[:, 0] > 0).astype(int)
    X_test = rng.normal(size=(50, 3))
    y_test = (X_test[:, 0] > 0).astype(int)

    result = logistic_regression_baseline(X_train, y_train, X_test, y_test, random_state=2)

    assert "pr_auc" in result
    # A feature that's literally the decision rule should let logistic regression do
    # much better than chance.
    assert result["pr_auc"] > 0.8


def test_logistic_regression_baseline_multiclass_has_no_pr_auc_key():
    rng = np.random.RandomState(3)
    X_train = rng.normal(size=(60, 2))
    y_train = rng.randint(0, 3, size=60)
    X_test = rng.normal(size=(20, 2))
    y_test = rng.randint(0, 3, size=20)

    result = logistic_regression_baseline(X_train, y_train, X_test, y_test, random_state=3)

    assert "pr_auc" not in result
    assert "accuracy" in result


# ----------------------------------------------------------------------------------------
# Binary metrics
# ----------------------------------------------------------------------------------------


def test_pr_auc_is_one_for_perfect_separation():
    y_true = [0, 0, 0, 1, 1, 1]
    y_prob = [0.1, 0.2, 0.3, 0.8, 0.9, 0.95]
    assert pr_auc(y_true, y_prob) == pytest.approx(1.0)


def test_binary_threshold_metrics_known_confusion_counts():
    y_true = [0, 0, 1, 1, 1]
    y_prob = [0.1, 0.6, 0.4, 0.7, 0.9]
    # threshold 0.5 -> predicted = [0, 1, 0, 1, 1]
    result = binary_threshold_metrics(y_true, y_prob, threshold=0.5)

    assert result["tp"] == 2  # indices 3, 4
    assert result["fp"] == 1  # index 1
    assert result["tn"] == 1  # index 0
    assert result["fn"] == 1  # index 2
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["alert_rate"] == pytest.approx(0.6)


def test_binary_threshold_metrics_handles_zero_predicted_positive():
    result = binary_threshold_metrics([0, 1], [0.1, 0.2], threshold=0.9)
    assert result["tp"] == 0 and result["fp"] == 0
    assert result["precision"] == 0.0  # no fabricated division result
    assert result["recall"] == 0.0


def test_calibration_report_low_brier_for_well_calibrated_probabilities():
    rng = np.random.RandomState(4)
    y_prob = rng.uniform(0, 1, size=2000)
    y_true = (rng.uniform(0, 1, size=2000) < y_prob).astype(int)

    report = calibration_report(y_true, y_prob, n_bins=10)

    assert report["brier_score"] < 0.2
    assert len(report["bin_mean_predicted"]) == report["n_bins"]
    assert len(report["bin_fraction_positive"]) == report["n_bins"]


def test_calibration_report_higher_brier_for_badly_miscalibrated_probabilities():
    y_true = [0] * 100 + [1] * 100
    well_calibrated = [0.05] * 100 + [0.95] * 100
    badly_calibrated = [0.95] * 100 + [0.05] * 100  # confidently wrong on everything

    good = calibration_report(y_true, well_calibrated)
    bad = calibration_report(y_true, badly_calibrated)

    assert bad["brier_score"] > good["brier_score"]


def test_threshold_tradeoff_table_flags_production_threshold_row():
    y_true = [0] * 50 + [1] * 50
    rng = np.random.RandomState(5)
    y_prob = np.concatenate([rng.uniform(0, 0.4, 50), rng.uniform(0.6, 1.0, 50)])

    table = threshold_tradeoff_table(y_true, y_prob, production_threshold=0.5)

    assert "is_production_threshold" in table.columns
    assert table["is_production_threshold"].sum() == 1
    flagged_row = table[table["is_production_threshold"]].iloc[0]
    assert flagged_row["threshold"] == pytest.approx(0.5)


def test_threshold_tradeoff_table_recall_is_non_increasing_in_threshold():
    rng = np.random.RandomState(6)
    y_true = rng.randint(0, 2, size=300)
    y_prob = rng.uniform(0, 1, size=300)

    table = threshold_tradeoff_table(y_true, y_prob).sort_values("threshold")

    recalls = table["recall"].to_numpy()
    assert np.all(np.diff(recalls) <= 1e-9)  # monotonically non-increasing


# ----------------------------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------------------------


def test_build_report_always_carries_the_disclaimer():
    report = build_temporal_entity_validation_report(
        business_problem="BP1",
        dataset_variant="LI-Medium",
        split_kind="chronological",
        y_test=[0, 1, 0, 1],
    )
    assert report["disclaimer"] == SYNTHETIC_DATA_DISCLAIMER


def test_build_report_includes_binary_metrics_only_when_y_prob_given():
    base_kwargs = dict(business_problem="BP1", dataset_variant="LI-Medium", split_kind="chronological")

    without_prob = build_temporal_entity_validation_report(y_test=[0, 1, 0, 1], **base_kwargs)
    assert "pr_auc" not in without_prob
    assert "calibration" not in without_prob

    with_prob = build_temporal_entity_validation_report(
        y_test=[0, 1, 0, 1], y_prob=[0.1, 0.9, 0.2, 0.8], production_threshold=0.5, **base_kwargs
    )
    assert "pr_auc" in with_prob
    assert "calibration" in with_prob
    assert "production_threshold_metrics" in with_prob
    assert "prevalence_baseline_pr_auc" in with_prob


def test_build_report_passes_through_baselines_and_entity_overlap():
    report = build_temporal_entity_validation_report(
        business_problem="BP3",
        dataset_variant="LI-Medium",
        split_kind="entity-aware",
        y_test=[0, 1],
        baselines={"majority_class": {"accuracy": 0.9}},
        entity_overlap={"n_overlapping_entities": 0},
        notes=["BP3 is a deterministic rule, not a probabilistic classifier."],
    )
    assert report["baselines"]["majority_class"]["accuracy"] == 0.9
    assert report["entity_overlap"]["n_overlapping_entities"] == 0
    assert report["notes"]


def test_render_markdown_report_includes_disclaimer_and_does_not_crash_on_minimal_report():
    minimal_report = {
        "business_problem": "BP3",
        "dataset_variant": "LI-Medium",
        "split_kind": "entity-aware",
        "n_test": 10,
        "disclaimer": SYNTHETIC_DATA_DISCLAIMER,
    }
    rendered = render_markdown_report(minimal_report)
    assert SYNTHETIC_DATA_DISCLAIMER in rendered
    assert "BP3" in rendered


def test_render_markdown_report_full_report_includes_all_sections():
    full_report = build_temporal_entity_validation_report(
        business_problem="BP1",
        dataset_variant="LI-Medium",
        split_kind="chronological",
        y_test=[0, 1, 0, 1, 0, 1, 0, 1],
        y_prob=[0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.05, 0.95],
        production_threshold=0.5,
        baselines={"majority_class": majority_class_baseline([0, 0, 1], [0, 1, 0, 1, 0, 1, 0, 1])},
        entity_overlap=cross_entity_overlap([pd.Series(["a"])], [pd.Series(["b"])]),
        notes=["example note"],
    )
    rendered = render_markdown_report(full_report)
    assert "## Baselines" in rendered
    assert "## Entity overlap" in rendered
    assert "## Threshold trade-off table" in rendered
    assert "## Notes" in rendered


# ----------------------------------------------------------------------------------------
# roc_auc
# ----------------------------------------------------------------------------------------


def test_roc_auc_is_one_for_perfect_separation():
    y_true = [0, 0, 0, 1, 1, 1]
    y_prob = [0.0, 0.1, 0.2, 0.8, 0.9, 1.0]
    assert roc_auc(y_true, y_prob) == pytest.approx(1.0)


def test_roc_auc_is_none_when_only_one_class_present():
    assert roc_auc([0, 0, 0, 0], [0.1, 0.2, 0.3, 0.4]) is None


# ----------------------------------------------------------------------------------------
# binary_threshold_metrics -- fpr / alert_volume
# ----------------------------------------------------------------------------------------


def test_binary_threshold_metrics_reports_fpr_and_alert_volume():
    y_true = [0, 0, 0, 0, 1, 1]
    y_prob = [0.1, 0.2, 0.6, 0.9, 0.3, 0.8]
    m = binary_threshold_metrics(y_true, y_prob, threshold=0.5)
    # predicted positive at >=0.5: indices 2 (fp), 3 (fp), 5 (tp) -> tp=1, fp=2, tn=2, fn=1
    assert m["tp"] == 1 and m["fp"] == 2 and m["tn"] == 2 and m["fn"] == 1
    assert m["fpr"] == pytest.approx(2 / 4)
    assert m["alert_volume"] == 3


# ----------------------------------------------------------------------------------------
# duplicate_record_check / duplicate_overlap_across_split
# ----------------------------------------------------------------------------------------


def test_duplicate_record_check_counts_exact_and_key_column_duplicates():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "amount": [10.0, 10.0, 20.0, 30.0],
            "account": ["A", "A", "B", "C"],
        }
    )
    # rows 0/1 share amount+account but differ on id -- not an exact duplicate, but a
    # key-column duplicate when id is excluded from the key.
    result = duplicate_record_check(df, key_columns=["amount", "account"])
    assert result["n_rows"] == 4
    assert result["n_exact_duplicate_rows"] == 0
    assert result["n_key_duplicate_rows"] == 2
    assert result["key_duplicate_fraction"] == pytest.approx(0.5)


def test_duplicate_record_check_exact_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [9, 9, 8]})
    result = duplicate_record_check(df)
    assert result["n_exact_duplicate_rows"] == 2
    assert result["exact_duplicate_fraction"] == pytest.approx(2 / 3)


def test_duplicate_overlap_across_split_detects_straddling_key():
    df = pd.DataFrame(
        {
            "amount": [10.0, 10.0, 20.0, 30.0],
            "account": ["A", "A", "B", "C"],
        }
    )
    # rows 0 and 1 are key-duplicates of each other; put one in train, one in test.
    overlap = duplicate_overlap_across_split(
        df, train_idx=[0, 2], test_idx=[1, 3], key_columns=["amount", "account"]
    )
    assert overlap["n_unique_keys_straddling_split"] == 1
    assert overlap["straddling_fraction_of_test_keys"] == pytest.approx(1 / 2)


def test_duplicate_overlap_across_split_zero_when_no_straddling():
    df = pd.DataFrame({"amount": [10.0, 20.0, 30.0, 40.0], "account": ["A", "B", "C", "D"]})
    overlap = duplicate_overlap_across_split(
        df, train_idx=[0, 1], test_idx=[2, 3], key_columns=["amount", "account"]
    )
    assert overlap["n_unique_keys_straddling_split"] == 0
    assert overlap["straddling_fraction_of_test_keys"] == 0.0


# ----------------------------------------------------------------------------------------
# dataset_fingerprint / environment_fingerprint
# ----------------------------------------------------------------------------------------


def test_dataset_fingerprint_is_deterministic_and_detects_content_changes():
    df1 = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df2 = df1.copy()
    df3 = pd.DataFrame({"a": [1, 2, 4], "b": ["x", "y", "z"]})  # one value changed

    fp1 = dataset_fingerprint(df1, label="run1")
    fp2 = dataset_fingerprint(df2, label="run1")
    fp3 = dataset_fingerprint(df3, label="run1")

    assert fp1["n_rows"] == 3 and fp1["n_columns"] == 2
    assert fp1["columns"] == ["a", "b"]
    assert fp1["content_hash_hex"] == fp2["content_hash_hex"]  # same content -> same hash
    assert fp1["content_hash_hex"] != fp3["content_hash_hex"]  # changed content -> different hash


def test_environment_fingerprint_reports_real_versions():
    env = environment_fingerprint()
    assert env["python_version"]
    assert env["numpy_version"]
    assert env["pandas_version"]
    assert env["scikit_learn_version"]
    # git_commit is either a real 40-char hex string or None -- never fabricated.
    assert env["git_commit"] is None or (isinstance(env["git_commit"], str) and len(env["git_commit"]) == 40)


# ----------------------------------------------------------------------------------------
# build_temporal_entity_validation_report -- new optional fields
# ----------------------------------------------------------------------------------------


def test_build_report_includes_roc_auc_and_environment_and_seed():
    y_test = [0, 0, 0, 1, 1, 1]
    y_prob = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
    report = build_temporal_entity_validation_report(
        business_problem="BP1",
        dataset_variant="unit-test",
        split_kind="chronological",
        y_test=y_test,
        y_prob=y_prob,
        random_seed=42,
    )
    assert report["roc_auc"] == pytest.approx(1.0)
    assert report["random_seed"] == 42
    assert "environment" in report and report["environment"]["python_version"]


def test_build_report_includes_dataset_fingerprints_and_duplicate_check_when_given():
    df = pd.DataFrame({"a": [1, 2, 3]})
    fp = dataset_fingerprint(df, label="full_df")
    dup = duplicate_record_check(df)
    report = build_temporal_entity_validation_report(
        business_problem="BP1",
        dataset_variant="unit-test",
        split_kind="entity-aware",
        y_test=[0, 1],
        dataset_fingerprints={"full_df": fp},
        duplicate_check=dup,
    )
    assert report["dataset_fingerprints"]["full_df"]["n_rows"] == 3
    assert report["duplicate_check"]["n_rows"] == 3


def test_render_markdown_report_includes_roc_auc_and_environment_lines():
    report = build_temporal_entity_validation_report(
        business_problem="BP1",
        dataset_variant="unit-test",
        split_kind="chronological",
        y_test=[0, 0, 1, 1],
        y_prob=[0.1, 0.4, 0.6, 0.9],
        random_seed=7,
    )
    md = render_markdown_report(report)
    assert "ROC-AUC" in md
    assert "Environment" in md
    assert "Random seed: 7" in md
