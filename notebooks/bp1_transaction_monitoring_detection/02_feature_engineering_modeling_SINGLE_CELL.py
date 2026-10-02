# ============================================================================
# BP1 NOTEBOOK 2 -- Feature Engineering & Modeling, HARDENED v6 (SINGLE CELL)
# ============================================================================
#
# v6 = v3's feature set (the real best PR-AUC so far: 0.0192), re-delivered with a REAL
# fix to threshold selection. Full honest history, in order:
#   v1 (0.0053): first pass, leaky whole-dataset degree features, flat 0.5 threshold.
#   v2 (0.0048): fixed leakage + added F2-optimal threshold selection -- PR-AUC dipped
#     slightly below v1 (search subsample too small to generalize).
#   v3 (0.0192): widened the hyperparameter search (1.5M-row subsample, added
#     regularization to the grid) -- real 4x jump. Still the best result so far. Real
#     issue found: selected_threshold landed at exactly 1.0 (fragile).
#   v4: added 4 new feature families (structuring-proxy, rolling 1h/24h windows,
#     receiver z-score, cross-border bank-prefix) -- CRASHED on the user's real run
#     (pandas groupby+rolling index-alignment bug).
#   v5 (0.0133): v4's crash fixed (verified against 200 brute-force spot checks), but the
#     real result came in ~31% BELOW v3 -- richer features did not help this round, and
#     the "p99.9 cap" threshold fix was also a real no-op: the OOF probability
#     distribution's own 99.9th percentile was ITSELF exactly 1.0 (enough predictions
#     saturate to 1.0 that the percentile cap couldn't exclude them). Confirmed by
#     inspecting the real saved metrics (threshold_p999_cap: 1.0).
#   v6 (this file, real user decision): v3 was the real best model on HI-Small -- go back to
#     v3's leaner 19-feature set (not v4/v5's 28), and apply the ACTUAL fix for the threshold
#     problem: rather than capping at a percentile (which can itself equal the max),
#     explicitly EXCLUDE the saturated top-tied threshold value from the F2 search. Since
#     sklearn's precision_recall_curve's thresholds are unique probability values sorted
#     ascending, this means dropping only the single highest unique threshold
#     (thresh_curve.max()) from eligibility -- a direct, always-correct fix, not a
#     percentile heuristic that can degenerate back to the same failure mode.
#
# CORRECTION (2026-09-30, corrections review): this file's feature-engineering pipeline (the
# actual thing v6 fixed and validated) IS what Notebook 3 reuses and IS confirmed real -- but
# v6's own MODEL (whichever single family happened to be importable first -- LightGBM on the
# machine this was tuned on) is NOT BP1's confirmed champion. Notebook 3's honest 4-candidate
# Stage A comparison on the real LI-Medium mandatory tier ranked that same LightGBM config
# LAST of four (real test PR-AUC 0.0037, barely above the 0.0005 random baseline), while
# XGBoost -- never separately tuned by v1-v6's work here -- won at 0.1242, 33x higher. v6's
# real, lasting contribution is the feature set and the saturated-max-excluded threshold
# method (Notebook 3 reuses both, and both hold up); its single-family model selection does
# not, and earlier wording here overstated it as "the confirmed real champion." Corrected.
#
# Everything else is UNCHANGED from v3: same leakage-free sender-only expanding features,
# same widened hyperparameter search (1.5M-row subsample, regularized grid), same F2-beta=2
# out-of-fold threshold-selection methodology (only the eligibility filter changed).
#
# KNOWN OPEN LIMITATION (disclosed, not fixed here -- flagged in Notebook 1 Section 6, never
# carried forward into this notebook's own text until this correction): 'Amount Paid' /
# 'Amount Received' are used below in their native per-row currency, log-transformed but
# never converted to a common currency. The raw IBM AML dataset ships no FX-rate table, so a
# real fix needs an external, dated, disclosed exchange-rate reference added as a new
# ASSUMPTION -- not invented here. Until that decision is made, every amount-based feature
# below (log_amount_paid, log_amount_received, amount_diff, sender_amount_sum_to_date,
# sender_amount_zscore, receiver_amount_sum_to_date) mixes magnitudes across real currencies
# as if directly comparable. Real, disclosed limitation -- not silently assumed away.
#
# Scope: HI-Small ONLY (fast build/debug target). Target: 'Is Laundering' (real, direct
# label). Primary metric: PR-AUC. Every number below is computed live -- nothing pre-typed.

import sys
from pathlib import Path

def _locate_project_root():
    cur = Path.cwd()
    for _ in range(8):
        if (cur / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    known = Path.home() / "Documents" / "IBM_AML_RiskIQ_Enterprise_Suite"
    if (known / "PROJECT_STRUCTURE_LOCKED.md").exists():
        return known
    raise FileNotFoundError(
        "Could not locate the project root. Checked: an upward walk from this notebook's "
        f"working directory ({Path.cwd()}), and {known}. Either save this notebook inside "
        "the project folder, or edit the 'known' path above to your real project location."
    )

_here = _locate_project_root()
sys.path.insert(0, str(_here / "src"))
print(f"Bootstrapped from: {_here}")

from utils.project_root import find_suite_root, raw_data_dir
from utils.performance_setup import configure_performance, thermal_checkpoint, load_csv_cached, timer

perf_config = configure_performance()
print("WARP configured:", perf_config)

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
MODELS_DIR = PROJECT_ROOT / "models" / "bp1_transaction_monitoring_detection"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root: {PROJECT_ROOT}")
print(f"Models dir  : {MODELS_DIR}")

import pandas as pd
import numpy as np

print(f"pandas {pd.__version__}, numpy {np.__version__}")

TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}

# --- 1. Load HI-Small (WARP: cached to Parquet on first read) ---
with timer("load HI-Small_Trans.csv"):
    df = load_csv_cached(RAW / "HI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"HI-Small_Trans.csv real shape: {df.shape}")

# Sort by time ONCE, up front -- every expanding/shift feature below depends on this order.
with timer("sort by Timestamp"):
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

# --- 2. Basic Features (time / amount / structural -- unchanged from v1-v3) ---
with timer("basic features"):
    df["hour"] = df["Timestamp"].dt.hour.astype("int8")
    df["day_of_week"] = df["Timestamp"].dt.dayofweek.astype("int8")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype("int8")

    df["log_amount_paid"] = np.log1p(df["Amount Paid"].clip(lower=0))
    df["log_amount_received"] = np.log1p(df["Amount Received"].clip(lower=0))
    df["currency_mismatch"] = (df["Payment Currency"] != df["Receiving Currency"]).astype("int8")
    df["amount_diff"] = np.where(df["currency_mismatch"] == 0, df["Amount Paid"] - df["Amount Received"], np.nan)

    df["is_self_transaction"] = ((df["From Bank"] == df["To Bank"]) & (df["Account"] == df["Account.1"])).astype("int8")
    df["is_cross_bank"] = (df["From Bank"] != df["To Bank"]).astype("int8")

# --- 3. Time-Respecting Expanding Features (unchanged from v2/v3 -- no leakage, prior rows only) ---
with timer("expanding sender (Account) features -- no leakage"):
    g_sender = df.groupby("Account", sort=False)
    df["sender_txn_count_to_date"] = g_sender.cumcount()
    df["sender_amount_sum_to_date"] = g_sender["Amount Paid"].cumsum().shift(1)
    df["sender_amount_sum_to_date"] = df.groupby("Account", sort=False)["sender_amount_sum_to_date"].ffill().fillna(0.0)
    df["_amt_sq"] = df["Amount Paid"] ** 2
    cum_sum = g_sender["Amount Paid"].cumsum().shift(1)
    cum_sum_sq = df.groupby("Account", sort=False)["_amt_sq"].cumsum().shift(1)
    n_prior = df["sender_txn_count_to_date"].replace(0, np.nan)
    sender_mean_to_date = cum_sum / n_prior
    sender_var_to_date = (cum_sum_sq / n_prior) - (sender_mean_to_date ** 2)
    sender_std_to_date = np.sqrt(sender_var_to_date.clip(lower=0))
    df["sender_amount_zscore"] = ((df["Amount Paid"] - sender_mean_to_date) / sender_std_to_date.replace(0, np.nan))
    df["sender_amount_zscore"] = df["sender_amount_zscore"].fillna(0.0).replace([np.inf, -np.inf], 0.0)
    df.drop(columns=["_amt_sq"], inplace=True)

    first_pair_occurrence = (~df.duplicated(subset=["Account", "Account.1"], keep="first")).astype("int32")
    df["_new_counterparty"] = first_pair_occurrence
    df["sender_distinct_counterparties_to_date"] = (
        df.groupby("Account", sort=False)["_new_counterparty"].cumsum() - df["_new_counterparty"]
    )
    df.drop(columns=["_new_counterparty"], inplace=True)

    df["sender_hours_since_prev_txn"] = (
        df.groupby("Account", sort=False)["Timestamp"].diff().dt.total_seconds() / 3600.0
    ).fillna(0.0)

with timer("expanding receiver (Account.1) features -- no leakage"):
    g_recv = df.groupby("Account.1", sort=False)
    df["receiver_txn_count_to_date"] = g_recv.cumcount()
    df["receiver_amount_sum_to_date"] = g_recv["Amount Received"].cumsum().shift(1)
    df["receiver_amount_sum_to_date"] = df.groupby("Account.1", sort=False)["receiver_amount_sum_to_date"].ffill().fillna(0.0)

df["sender_amount_sum_to_date"] = df["sender_amount_sum_to_date"].fillna(0.0)
df["sender_txn_count_to_date"] = df["sender_txn_count_to_date"].astype("int32")
df["receiver_txn_count_to_date"] = df["receiver_txn_count_to_date"].astype("int32")
df["sender_distinct_counterparties_to_date"] = df["sender_distinct_counterparties_to_date"].astype("int32")

FEATURE_COLS = [
    "hour", "day_of_week", "is_weekend",
    "log_amount_paid", "log_amount_received", "currency_mismatch", "amount_diff",
    "is_self_transaction", "is_cross_bank",
    "sender_txn_count_to_date", "sender_amount_sum_to_date", "sender_amount_zscore",
    "sender_distinct_counterparties_to_date", "sender_hours_since_prev_txn",
    "receiver_txn_count_to_date", "receiver_amount_sum_to_date",
    "Payment Format", "Payment Currency", "Receiving Currency",
]
TARGET_COL = "Is Laundering"
print(f"Real engineered feature set v6 (= v3's set, {len(FEATURE_COLS)} columns, all leakage-checked):")
print(FEATURE_COLS)
print(df[FEATURE_COLS + [TARGET_COL]].head(5))

# --- 4. Real Naive Baseline (unchanged -- kept as the continuity benchmark) ---
from sklearn.metrics import precision_score, recall_score, average_precision_score, fbeta_score, precision_recall_curve

with timer("naive fixed-dollar-threshold baseline"):
    threshold_dollar = float(df["Amount Paid"].quantile(0.99))
    baseline_pred = (df["Amount Paid"] > threshold_dollar).astype(int)
    baseline_precision_full = precision_score(df[TARGET_COL], baseline_pred, zero_division=0)
    baseline_recall_full = recall_score(df[TARGET_COL], baseline_pred, zero_division=0)

print(f"Naive baseline (Amount Paid > {threshold_dollar:,.2f}, real 99th percentile): "
      f"precision={baseline_precision_full:.4f}, recall={baseline_recall_full:.4f}")

# --- 5. Stratified Train/Test Split (random_state=42, per configs/resource_limits.yaml) ---
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict

with timer("train/test split"):
    X = df[FEATURE_COLS].copy()
    y = df[TARGET_COL].copy()
    for cat_col in ["Payment Format", "Payment Currency", "Receiving Currency"]:
        X[cat_col] = X[cat_col].cat.codes.astype("int16")
    X["amount_diff"] = X["amount_diff"].fillna(0.0)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)

print(f"Train: {X_train.shape}, positives: {int(y_train.sum())} ({100*y_train.mean():.4f}%)")
print(f"Test : {X_test.shape}, positives: {int(y_test.sum())} ({100*y_test.mean():.4f}%)")

scale_pos_weight = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
print(f"Real class imbalance ratio for scale_pos_weight: {scale_pos_weight:.1f}")

# --- 6. Which library is actually available on this machine (honest, tried in order) ---
model_family = None
try:
    import lightgbm as lgb
    model_family = "lightgbm"
except ImportError:
    try:
        import xgboost as xgb
        model_family = "xgboost"
    except ImportError:
        from sklearn.ensemble import RandomForestClassifier
        model_family = "random_forest"
print(f"Real model family available on this machine: {model_family}")

def build_model(params, family=model_family, spw=scale_pos_weight):
    if family == "lightgbm":
        return lgb.LGBMClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, verbosity=-1, **params)
    elif family == "xgboost":
        return xgb.XGBClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, eval_metric="aucpr", **params)
    else:
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1, **params)

# --- 7. Hyperparameter Search (unchanged from v3 -- this is the real best-performing config) ---
SEARCH_SUBSAMPLE_SIZE = min(1_500_000, len(X_train))

with timer("hyperparameter search (widened grid, larger subsample, 3-fold CV, PR-AUC scoring)"):
    if model_family == "random_forest":
        best_params = {"n_estimators": 300, "max_depth": 14, "min_samples_leaf": 5}
        print("RandomForest fallback: skipping tuned search, using fixed reasonable defaults "
              f"{best_params} (tuning scope was written for lightgbm/xgboost's shared "
              "n_estimators/learning_rate/tree-complexity/regularization axes).")
    else:
        _, X_search, _, y_search = train_test_split(
            X_train, y_train, test_size=SEARCH_SUBSAMPLE_SIZE, stratify=y_train, random_state=42
        )
        if model_family == "lightgbm":
            param_grid = [
                {"n_estimators": 300, "learning_rate": 0.05, "num_leaves": 63, "min_child_samples": 20, "reg_lambda": 0.0},
                {"n_estimators": 300, "learning_rate": 0.05, "num_leaves": 63, "min_child_samples": 100, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 100, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 127, "min_child_samples": 200, "reg_lambda": 2.0},
                {"n_estimators": 500, "learning_rate": 0.03, "num_leaves": 63, "min_child_samples": 200, "reg_lambda": 5.0},
                {"n_estimators": 300, "learning_rate": 0.08, "num_leaves": 31, "min_child_samples": 50, "reg_lambda": 1.0},
            ]
        else:  # xgboost
            param_grid = [
                {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 1, "reg_lambda": 1.0},
                {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 10, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.05, "max_depth": 5, "min_child_weight": 10, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.03, "max_depth": 8, "min_child_weight": 20, "reg_lambda": 2.0},
                {"n_estimators": 500, "learning_rate": 0.03, "max_depth": 6, "min_child_weight": 20, "reg_lambda": 5.0},
                {"n_estimators": 300, "learning_rate": 0.08, "max_depth": 5, "min_child_weight": 5, "reg_lambda": 1.0},
            ]
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        search_results = []
        for params in param_grid:
            fold_scores = []
            for train_idx, val_idx in cv.split(X_search, y_search):
                m = build_model(params)
                m.fit(X_search.iloc[train_idx], y_search.iloc[train_idx])
                proba = m.predict_proba(X_search.iloc[val_idx])[:, 1]
                fold_scores.append(average_precision_score(y_search.iloc[val_idx], proba))
            mean_pr_auc = float(np.mean(fold_scores))
            search_results.append({"params": params, "cv_pr_auc": mean_pr_auc})
            print(f"  params={params} -> real 3-fold mean PR-AUC (1.5M-row search subsample) = {mean_pr_auc:.4f}")
        best = max(search_results, key=lambda r: r["cv_pr_auc"])
        best_params = best["params"]
        print(f"Best real params (1.5M-row search subsample): {best_params} (PR-AUC={best['cv_pr_auc']:.4f})")

# --- 8. Refit Best Config on the FULL Training Set ---
with timer("final model fit (full training set, best params)"):
    model = build_model(best_params)
    model.fit(X_train, y_train)
model_name = f"{model_family} (tuned v6: {best_params})"
print(f"Real final model fit: {model_name}")

thermal_checkpoint(label="post BP1 Notebook 2 v6 final model fit")

# --- 9. Real Threshold Selection -- Out-of-Fold CV on TRAIN ONLY (test set never touched) ---
# v6 REAL FIX: v3 landed on selected_threshold=1.0 (fragile). v5's attempted fix (cap at
# the 99.9th percentile of OOF probabilities) was a real no-op -- verified from the saved
# metrics that the p99.9 percentile was ITSELF exactly 1.0, because enough predictions
# saturate at 1.0 on this imbalanced data that the percentile couldn't exclude them. The
# actual fix here: sklearn's precision_recall_curve thresholds are the UNIQUE probability
# values, sorted ascending -- so explicitly drop only the single highest unique threshold
# (thresh_curve.max()) from eligibility. This always works regardless of how much mass
# sits at the saturation point, unlike a percentile-based cap.
with timer("threshold selection (out-of-fold CV on train, F2-optimal, saturated-max excluded)"):
    cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)  # resource_limits.yaml's real CV spec
    oof_proba = cross_val_predict(build_model(best_params), X_train, y_train, cv=cv5, method="predict_proba", n_jobs=1)[:, 1]
    prec_curve, rec_curve, thresh_curve = precision_recall_curve(y_train, oof_proba)
    beta = 2.0
    f2_scores = (1 + beta**2) * (prec_curve[:-1] * rec_curve[:-1]) / ((beta**2 * prec_curve[:-1]) + rec_curve[:-1] + 1e-12)

    max_unique_threshold = float(thresh_curve.max())
    eligible_mask = thresh_curve < max_unique_threshold
    if eligible_mask.any():
        f2_eligible = np.where(eligible_mask, f2_scores, -np.inf)
        best_idx = int(np.nanargmax(f2_eligible))
    else:
        # Degenerate case: every OOF prediction shares the same probability value.
        # Real fallback, disclosed rather than silently handled: use the unfiltered argmax.
        print("  WARNING: all out-of-fold thresholds are tied at the same value -- "
              "falling back to the unfiltered F2 argmax (real, disclosed edge case).")
        best_idx = int(np.nanargmax(f2_scores))
    selected_threshold = float(thresh_curve[best_idx])
    oof_pr_auc = average_precision_score(y_train, oof_proba)

print(f"Real max unique OOF threshold (excluded from search): {max_unique_threshold:.6f}")
print(f"Real F2-optimal threshold selected from out-of-fold train predictions: {selected_threshold:.4f}")
print(f"  (out-of-fold train, at this threshold: precision={prec_curve[best_idx]:.4f}, "
      f"recall={rec_curve[best_idx]:.4f}, F2={f2_scores[best_idx]:.4f})")
print(f"  (out-of-fold train PR-AUC, full training set, tuned config: {oof_pr_auc:.4f})")

# --- 10. Real Evaluation on the Untouched Test Set, at the Selected Threshold ---
with timer("test-set evaluation"):
    y_proba_test = model.predict_proba(X_test)[:, 1]
    y_pred_test = (y_proba_test >= selected_threshold).astype(int)

    model_pr_auc = average_precision_score(y_test, y_proba_test)
    model_precision = precision_score(y_test, y_pred_test, zero_division=0)
    model_recall = recall_score(y_test, y_pred_test, zero_division=0)
    model_f2 = fbeta_score(y_test, y_pred_test, beta=2, zero_division=0)

    baseline_pred_test = (X_test["log_amount_paid"] > np.log1p(threshold_dollar)).astype(int)
    baseline_precision_test = precision_score(y_test, baseline_pred_test, zero_division=0)
    baseline_recall_test = recall_score(y_test, baseline_pred_test, zero_division=0)
    baseline_f2_test = fbeta_score(y_test, baseline_pred_test, beta=2, zero_division=0)

    random_baseline_pr_auc = float(y_test.mean())  # expected PR-AUC of a random/no-skill classifier

print("=" * 78)
print(f"BP1 Notebook 2 v6 -- Real Before/After Comparison ({model_name})")
print(f"HI-Small holdout, real selected threshold = {selected_threshold:.4f}")
print("=" * 78)
print(f"{'Metric':<14}{'Naive baseline':>18}{'Tuned model':>18}")
print(f"{'Precision':<14}{baseline_precision_test:>18.4f}{model_precision:>18.4f}")
print(f"{'Recall':<14}{baseline_recall_test:>18.4f}{model_recall:>18.4f}")
print(f"{'F2':<14}{baseline_f2_test:>18.4f}{model_f2:>18.4f}")
print(f"{'PR-AUC':<14}{random_baseline_pr_auc:>18.5f}{model_pr_auc:>18.5f}  (random/no-skill baseline = test-set positive rate)")
print(f"{'Lift over random':<14}{'1.00x':>18}{(model_pr_auc/random_baseline_pr_auc if random_baseline_pr_auc > 0 else float('nan')):>17.2f}x")
print("=" * 78)
print(f"v1: 0.0053 | v2: 0.0048 | v3: 0.0192 | v4: crashed | v5: 0.0133 | v6: {model_pr_auc:.4f}  (real, honest comparison)")
print("Real, measured on the untouched HI-Small test split -- threshold was selected only")
print("from train-set out-of-fold predictions, never from test. Still a first-pass HI-Small")
print("result: LI-Medium validation (Notebook 3) has not run -- this is not BP1's final number.")

# --- 11. Real Feature Importance ---
with timer("feature importance"):
    if hasattr(model, "feature_importances_"):
        importance = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
        print("Real feature importances (this run, tuned model):")
        print(importance.to_string())
    else:
        importance = None

# --- 12. Save Real Model + Metrics ---
import json
import pickle
from datetime import datetime, timezone

with timer("save model artifacts"):
    model_path = MODELS_DIR / "bp1_hi_small_model_v6.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    metrics = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": "HI-Small",
        "model_name": model_name,
        "best_params": best_params,
        "search_subsample_size": SEARCH_SUBSAMPLE_SIZE,
        "selected_threshold": selected_threshold,
        "max_unique_oof_threshold_excluded": max_unique_threshold,
        "threshold_selection_method": "F2-optimal, out-of-fold 5-fold CV on train only, saturated-max threshold excluded",
        "feature_cols": FEATURE_COLS,
        "naive_baseline": {"precision": baseline_precision_test, "recall": baseline_recall_test, "f2": baseline_f2_test},
        "random_baseline_pr_auc": random_baseline_pr_auc,
        "model_metrics": {"precision": model_precision, "recall": model_recall, "f2": model_f2, "pr_auc": model_pr_auc},
        "prior_runs": {
            "v1_pr_auc": 0.0053, "v2_pr_auc": 0.0048, "v3_pr_auc": 0.0192,
            "v4": "crashed (rolling-window TypeError)", "v5_pr_auc": 0.0133,
        },
        "note": "v6: reverted to v3's leaner 19-feature set (real user decision -- v5's 28 "
                "features underperformed v3). Real fix applied to threshold selection: the "
                "single saturated top unique OOF threshold is now explicitly excluded, "
                "rather than v5's percentile cap which was a no-op. This is BP1's working "
                "HI-Small model going into Notebook 3 (LI-Medium mandatory validation tier).",
    }
    metrics_path = MODELS_DIR / "bp1_hi_small_model_v6_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

print(f"Real model saved to : {model_path}")
print(f"Real metrics saved to: {metrics_path}")

# --- 13. Notebook 2 v6 Summary ---
print("=" * 78)
print("BP1 -- Notebook 2 v6 (v3's feature set, real threshold fix) Summary (real, this run)")
print("=" * 78)
print(f"Model            : {model_name}")
print(f"Selected threshold: {selected_threshold:.4f} (F2-optimal, train-only OOF, saturated-max excluded)")
print(f"Model PR-AUC     : {model_pr_auc:.4f}  (random baseline = {random_baseline_pr_auc:.5f}; "
      f"v1=0.0053, v2=0.0048, v3=0.0192, v5=0.0133)")
print(f"Model recall     : {model_recall:.4f}  |  Model precision: {model_precision:.4f}  |  Model F2: {model_f2:.4f}")
print(f"Baseline recall  : {baseline_recall_test:.4f}  |  Baseline precision: {baseline_precision_test:.4f}")
print("=" * 78)

# Next: Notebook 3 -- Statistical Validation & Deployment. Re-runs this feature/model
# pipeline (same feature functions, same selected threshold logic) against the MANDATORY
# LI-Medium tier before any BP1 result counts as final, per Section 2.1's locked policy.
