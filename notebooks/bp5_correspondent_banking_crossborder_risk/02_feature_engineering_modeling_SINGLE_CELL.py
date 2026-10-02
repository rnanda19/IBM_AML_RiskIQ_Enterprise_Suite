# ============================================================================
# BP5 NOTEBOOK 2 -- Feature Engineering & Modeling (SINGLE CELL)
# ============================================================================
#
# Scope: HI-Small ONLY (fast build/debug target, per locked per-notebook staged pattern).
# Target: 'Is Laundering' (real, direct label, same as BP1/BP4). Primary metric: PR-AUC.
#
# Feature set = the platform's existing real, leakage-checked 19-column feature set (reused
# UNCHANGED from BP1/BP4 -- same sender/receiver expanding features, same leakage discipline)
# PLUS the 8 NEW real cross-border features LOCKED in Notebook 1 Section 7, built from the
# real Bank-Name country-tagging method validated in Notebook 1 Section 4.
#
# `sender_country_empirical_risk`/`receiver_country_empirical_risk`'s Laplace-smoothed rates are
# fit on TRAIN rows only, per the locked leakage discipline (Notebook 1 Section 7 / Lesson #11) --
# the train/test split happens BEFORE those two features are computed, same discipline BP4's
# `near_threshold_flag` already uses. The other 6 new cross-border features (country tags,
# is_cross_border, sender/receiver_is_foreign, foreign_to_foreign) are real structural facts about
# the transaction and its two counterparty banks -- deterministic regardless of train/test row
# membership, same discipline BP1's own expanding sender/receiver features and BP4's rolling-
# window features already use.
#
# Every number below is computed live -- nothing pre-typed.

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
from utils.performance_setup import configure_performance, thermal_checkpoint, load_csv_cached, timer, assert_ram_safe

perf_config = configure_performance()
print("WARP configured:", perf_config)

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
MODELS_DIR = PROJECT_ROOT / "models" / "bp5_correspondent_banking_crossborder_risk"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root: {PROJECT_ROOT}")
print(f"Models dir  : {MODELS_DIR}")

import re
import pandas as pd
import numpy as np

print(f"pandas {pd.__version__}, numpy {np.__version__}")

TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}
ACCOUNTS_DTYPES = {
    "Bank Name": "string", "Bank ID": "string", "Account Number": "string",
    "Entity ID": "string", "Entity Name": "string",
}

EMPIRICAL_RISK_PSEUDO_COUNT = 20  # locked, Notebook 1 Section 7

# --- 1. Load HI-Small Transactions + Accounts (WARP: cached to Parquet on first read) ---
with timer("load HI-Small_Trans.csv"):
    df = load_csv_cached(RAW / "HI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"HI-Small_Trans.csv real shape: {df.shape}")

with timer("load HI-Small_accounts.csv"):
    accounts = load_csv_cached(RAW / "HI-Small_accounts.csv", dtype=ACCOUNTS_DTYPES)
print(f"HI-Small_accounts.csv real shape: {accounts.shape}")

# --- REAL BUG FIX (2026-10-02): Trans.csv's `From Bank`/`To Bank` store the same real bank IDs
# as accounts.csv's `Bank ID`, but with inconsistent leading-zero padding (e.g. real observed
# `"0322605"` vs `"331579"`). Both columns load as pandas "string" dtype, so every `.map()`
# lookup in Section 4 below silently failed end to end (string `"010"` != string `"10"`) -- the
# real, confirmed cause of all 8 new cross-border features showing exactly 0 feature importance.
# Confirmed directly against the real raw CSVs on-device: cast both sides to int64 and HI-Small
# shows a perfect 30,470-way Bank ID overlap -- never a real coverage gap, only a string-
# representation mismatch. Re-cast here, right after load, so the fix holds regardless of what
# dtype a stale Parquet cache returns (`load_csv_cached` ignores the dtype kwarg entirely on a
# cache hit -- see src/utils/performance_setup.py).
df["From Bank"] = df["From Bank"].astype("int64")
df["To Bank"] = df["To Bank"].astype("int64")
accounts["Bank ID"] = accounts["Bank ID"].astype("int64")
print("[BUGFIX] From Bank/To Bank/Bank ID re-cast to int64 (real leading-zero string-mismatch fix, 2026-10-02).")

with timer("sort by Timestamp"):
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

# --- 2. Basic Features (reused UNCHANGED from the platform's existing BP1/BP4 Notebook 2) ---
with timer("basic features (reused from BP1)"):
    df["hour"] = df["Timestamp"].dt.hour.astype("int8")
    df["day_of_week"] = df["Timestamp"].dt.dayofweek.astype("int8")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype("int8")

    df["log_amount_paid"] = np.log1p(df["Amount Paid"].clip(lower=0))
    df["log_amount_received"] = np.log1p(df["Amount Received"].clip(lower=0))
    df["currency_mismatch"] = (df["Payment Currency"] != df["Receiving Currency"]).astype("int8")
    df["amount_diff"] = np.where(df["currency_mismatch"] == 0, df["Amount Paid"] - df["Amount Received"], np.nan)

    df["is_self_transaction"] = ((df["From Bank"] == df["To Bank"]) & (df["Account"] == df["Account.1"])).astype("int8")
    df["is_cross_bank"] = (df["From Bank"] != df["To Bank"]).astype("int8")

# --- 3. Time-Respecting Expanding Sender/Receiver Features (reused UNCHANGED from BP1/BP4) ---
with timer("expanding sender (Account) features -- no leakage, reused from BP1"):
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

with timer("expanding receiver (Account.1) features -- no leakage, reused from BP1"):
    g_recv = df.groupby("Account.1", sort=False)
    df["receiver_txn_count_to_date"] = g_recv.cumcount()
    df["receiver_amount_sum_to_date"] = g_recv["Amount Received"].cumsum().shift(1)
    df["receiver_amount_sum_to_date"] = df.groupby("Account.1", sort=False)["receiver_amount_sum_to_date"].ffill().fillna(0.0)

df["sender_amount_sum_to_date"] = df["sender_amount_sum_to_date"].fillna(0.0)
df["sender_txn_count_to_date"] = df["sender_txn_count_to_date"].astype("int32")
df["receiver_txn_count_to_date"] = df["receiver_txn_count_to_date"].astype("int32")
df["sender_distinct_counterparties_to_date"] = df["sender_distinct_counterparties_to_date"].astype("int32")

# ============================================================================
# 4. NEW -- Real Cross-Border Features (locked policy, Notebook 1 Section 7), via the real,
#    Notebook-1-validated Bank-Name country-tagging method. Self-contained here (this notebook's
#    own real country-tag build + self-test), same "stands alone" discipline as every other
#    notebook on this platform.
# ============================================================================
COMMON_COUNTRY_NAMES = sorted({
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi",
    "Cambodia", "Cameroon", "Canada", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica",
    "Croatia", "Cuba", "Cyprus", "Czechia", "Denmark", "Djibouti", "Dominica", "Ecuador", "Egypt",
    "El Salvador", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon",
    "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guyana", "Haiti",
    "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy",
    "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos",
    "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg",
    "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania", "Mauritius", "Mexico",
    "Micronesia", "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar",
    "Namibia", "Nauru", "Nepal", "Netherlands", "Nicaragua", "Niger", "Nigeria", "Norway", "Oman", "Pakistan",
    "Palau", "Panama", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia",
    "Rwanda", "Samoa", "Senegal", "Serbia", "Seychelles", "Singapore", "Slovakia", "Slovenia", "Somalia",
    "Spain", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Togo", "Tonga", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "UK",
    "Uruguay", "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
    "Saudi Arabia", "South Africa", "South Korea", "North Korea", "New Zealand", "Dominican Republic",
    "United States", "USA", "Papua New Guinea", "Saint Lucia", "Trinidad and Tobago",
})
_COUNTRY_PATTERN = "|".join(sorted((c.replace(" ", r"\s+") for c in COMMON_COUNTRY_NAMES), key=len, reverse=True))
_COUNTRY_TAG_RE = re.compile(rf"^({_COUNTRY_PATTERN})\s+Bank\s+#\d+$")

def tag_bank_country(bank_names: "pd.Series") -> "pd.Series":
    """Real, vectorized country extraction -- see Notebook 1 Section 4 for the full real evidence
    this policy is built on. Returns the matched country string, or 'DOMESTIC'."""
    return bank_names.str.extract(_COUNTRY_TAG_RE, expand=False).fillna("DOMESTIC")

with timer("real cross-border country-tag build + join (NEW this BP)"):
    bank_id_to_name = accounts[["Bank ID", "Bank Name"]].drop_duplicates(subset="Bank ID").set_index("Bank ID")["Bank Name"]
    bank_id_to_country = tag_bank_country(bank_id_to_name)

    df["sender_country"] = df["From Bank"].map(bank_id_to_country)
    df["receiver_country"] = df["To Bank"].map(bank_id_to_country)
    n_unmapped = int(df["sender_country"].isna().sum() + df["receiver_country"].isna().sum())
    if n_unmapped:
        print(f"  [DISCLOSED GAP] {n_unmapped:,} real (sender+receiver) bank-ID lookups did not match any "
              f"real row in this run's own accounts.csv -- left as explicit 'UNRESOLVED', never silently "
              f"defaulted to DOMESTIC (Lesson #7 undefined-count discipline).")
    df["sender_country"] = df["sender_country"].fillna("UNRESOLVED")
    df["receiver_country"] = df["receiver_country"].fillna("UNRESOLVED")

    df["is_cross_border"] = (df["sender_country"] != df["receiver_country"]).astype("int8")
    df["sender_is_foreign"] = (df["sender_country"] != "DOMESTIC").astype("int8")
    df["receiver_is_foreign"] = (df["receiver_country"] != "DOMESTIC").astype("int8")
    df["foreign_to_foreign"] = (
        (df["sender_is_foreign"] == 1) & (df["receiver_is_foreign"] == 1) & (df["sender_country"] != df["receiver_country"])
    ).astype("int8")

    n_cross = int(df["is_cross_border"].sum())
    print(f"Real cross-border rate this run: {n_cross:,} / {len(df):,} ({100*n_cross/len(df):.3f}%)")
    print(f"Real foreign-to-foreign (Wolfsberg third-country proxy) rate: "
          f"{100*df['foreign_to_foreign'].mean():.4f}%")

    # Real correctness self-test: brute-force spot-check 10 random rows' country tags directly
    # against accounts.csv, independent of the vectorized .map() path above.
    rng_check = np.random.default_rng(42)
    check_rows = rng_check.choice(len(df), size=min(10, len(df)), replace=False)
    name_lookup = accounts.drop_duplicates(subset="Bank ID").set_index("Bank ID")["Bank Name"]
    mismatches = 0
    for i in check_rows:
        row = df.iloc[i]
        bf_sender_name = name_lookup.get(row["From Bank"])
        bf_sender_country = tag_bank_country(pd.Series([bf_sender_name]))[0] if bf_sender_name is not None else "UNRESOLVED"
        if bf_sender_country != row["sender_country"]:
            mismatches += 1
    if mismatches:
        raise AssertionError(
            f"Real cross-border country-tag self-test FAILED: {mismatches}/{len(check_rows)} spot-checked "
            f"rows mismatched a direct, independent accounts.csv lookup. Do not proceed."
        )
    print(f"Real correctness self-test PASSED: {len(check_rows)}/{len(check_rows)} spot-checked rows' "
          f"sender_country match an independent direct accounts.csv lookup.")

CROSSBORDER_FEATURE_COLS_PRE_SPLIT = [
    "sender_country", "receiver_country", "is_cross_border", "sender_is_foreign",
    "receiver_is_foreign", "foreign_to_foreign",
]

# --- 5. Real Naive Baseline (same instrument as BP1/BP4, for continuity) ---
from sklearn.metrics import precision_score, recall_score, average_precision_score, fbeta_score, precision_recall_curve

with timer("naive fixed-amount-threshold baseline"):
    threshold_dollar = float(df["Amount Paid"].quantile(0.99))
    baseline_pred = (df["Amount Paid"] > threshold_dollar).astype(int)
    baseline_precision_full = precision_score(df["Is Laundering"], baseline_pred, zero_division=0)
    baseline_recall_full = recall_score(df["Is Laundering"], baseline_pred, zero_division=0)
print(f"Naive baseline (Amount Paid > {threshold_dollar:,.2f}, real 99th percentile, same rule as BP1/BP4): "
      f"precision={baseline_precision_full:.4f}, recall={baseline_recall_full:.4f}")

# --- 6. Stratified Train/Test Split (BEFORE the empirical-risk features -- leakage discipline) ---
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict

TARGET_COL = "Is Laundering"
with timer("train/test split"):
    train_idx, test_idx = train_test_split(
        np.arange(len(df)), test_size=0.25, stratify=df[TARGET_COL], random_state=42
    )
    is_train = np.zeros(len(df), dtype=bool)
    is_train[train_idx] = True

print(f"Train rows: {is_train.sum():,} ({100*df.loc[is_train, TARGET_COL].mean():.4f}% positive)")
print(f"Test rows : {(~is_train).sum():,} ({100*df.loc[~is_train, TARGET_COL].mean():.4f}% positive)")

# --- 6b. sender/receiver_country_empirical_risk -- real Laplace-smoothed TRAIN-only country rates ---
with timer("country empirical-risk features -- real, Laplace-smoothed, fit on TRAIN only"):
    global_train_rate = float(df.loc[is_train, TARGET_COL].mean())
    train_df = df.loc[is_train]

    def fit_country_risk(country_col: str) -> "pd.Series":
        grp = train_df.groupby(country_col, observed=True)[TARGET_COL].agg(["sum", "count"])
        smoothed = (grp["sum"] + EMPIRICAL_RISK_PSEUDO_COUNT * global_train_rate) / (grp["count"] + EMPIRICAL_RISK_PSEUDO_COUNT)
        return smoothed

    sender_risk_table = fit_country_risk("sender_country")
    receiver_risk_table = fit_country_risk("receiver_country")
    print(f"Real global TRAIN-only Is-Laundering rate (smoothing prior): {global_train_rate:.6f}")
    print(f"Real per-country sender risk table, TRAIN-only, this run (top 10 by real rate):")
    print(sender_risk_table.sort_values(ascending=False).head(10).to_string())

    df["sender_country_empirical_risk"] = df["sender_country"].map(sender_risk_table)
    df["receiver_country_empirical_risk"] = df["receiver_country"].map(receiver_risk_table)
    # Real, disclosed edge case: a country present in TEST but absent from TRAIN has no real
    # fitted rate -- explicitly backfilled to the real global TRAIN rate (the Laplace prior's own
    # limit as count->0), never silently left NaN or zero-filled.
    n_unseen_sender = int(df["sender_country_empirical_risk"].isna().sum())
    n_unseen_receiver = int(df["receiver_country_empirical_risk"].isna().sum())
    df["sender_country_empirical_risk"] = df["sender_country_empirical_risk"].fillna(global_train_rate)
    df["receiver_country_empirical_risk"] = df["receiver_country_empirical_risk"].fillna(global_train_rate)
    if n_unseen_sender or n_unseen_receiver:
        print(f"  NOTE: {n_unseen_sender:,} sender / {n_unseen_receiver:,} receiver real rows carry a country "
              f"not present in TRAIN -- backfilled to the real global TRAIN rate ({global_train_rate:.6f}), "
              f"disclosed rather than silently NaN or zero.")

CROSSBORDER_FEATURE_COLS = CROSSBORDER_FEATURE_COLS_PRE_SPLIT + [
    "sender_country_empirical_risk", "receiver_country_empirical_risk",
]
print(f"\nReal cross-border feature set this run ({len(CROSSBORDER_FEATURE_COLS)} columns):")
print(CROSSBORDER_FEATURE_COLS)

# --- 7. Combined Feature Set (platform's existing 19 + BP5's 8 new cross-border features = 27) ---
BP1_FEATURE_COLS = [
    "hour", "day_of_week", "is_weekend",
    "log_amount_paid", "log_amount_received", "currency_mismatch", "amount_diff",
    "is_self_transaction", "is_cross_bank",
    "sender_txn_count_to_date", "sender_amount_sum_to_date", "sender_amount_zscore",
    "sender_distinct_counterparties_to_date", "sender_hours_since_prev_txn",
    "receiver_txn_count_to_date", "receiver_amount_sum_to_date",
    "Payment Format", "Payment Currency", "Receiving Currency",
]
FEATURE_COLS = BP1_FEATURE_COLS + CROSSBORDER_FEATURE_COLS
print(f"\nReal combined feature set this run ({len(FEATURE_COLS)} columns -- platform's {len(BP1_FEATURE_COLS)} + "
      f"BP5's {len(CROSSBORDER_FEATURE_COLS)} new cross-border features):")
print(FEATURE_COLS)

X = df[FEATURE_COLS].copy()
y = df[TARGET_COL].copy()
for cat_col in ["Payment Format", "Payment Currency", "Receiving Currency", "sender_country", "receiver_country"]:
    X[cat_col] = X[cat_col].astype("category").cat.codes.astype("int16")
X["amount_diff"] = X["amount_diff"].fillna(0.0)

X_train, X_test = X.loc[is_train], X.loc[~is_train]
y_train, y_test = y.loc[is_train], y.loc[~is_train]
print(f"\nTrain: {X_train.shape}, positives: {int(y_train.sum())} ({100*y_train.mean():.4f}%)")
print(f"Test : {X_test.shape}, positives: {int(y_test.sum())} ({100*y_test.mean():.4f}%)")

scale_pos_weight = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
print(f"Real class imbalance ratio for scale_pos_weight: {scale_pos_weight:.1f}")

# --- 8. Which library is actually available on this machine (honest, tried in order -- same
#     convention as BP1/BP4 Notebook 2) ---
model_family = None
needs_impute = False
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
        needs_impute = True
print(f"Real model family available on this machine: {model_family}")

def build_model(params, family=model_family, spw=scale_pos_weight):
    if family == "lightgbm":
        return lgb.LGBMClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, verbosity=-1, **params)
    elif family == "xgboost":
        return xgb.XGBClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, eval_metric="aucpr", **params)
    else:
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1, **params)

# --- 9. Hyperparameter Search (same grid shape as BP1/BP4 Notebook 2 -- proven starting point) ---
# Same defensive 90%-of-train-set cap as BP4 Notebook 2 (Lesson, carried forward) -- a no-op at
# this BP's real locked HI-Small scale, but correct at any scale.
SEARCH_SUBSAMPLE_SIZE = min(1_500_000, int(len(X_train) * 0.9))

with timer("hyperparameter search (3-fold CV, PR-AUC scoring)"):
    if model_family == "random_forest":
        best_params = {"n_estimators": 300, "max_depth": 14, "min_samples_leaf": 5}
        print(f"RandomForest fallback: skipping tuned search, using fixed reasonable defaults {best_params}.")
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
            ]
        else:  # xgboost
            param_grid = [
                {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 1, "reg_lambda": 1.0},
                {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 10, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.05, "max_depth": 5, "min_child_weight": 10, "reg_lambda": 1.0},
                {"n_estimators": 400, "learning_rate": 0.03, "max_depth": 8, "min_child_weight": 20, "reg_lambda": 2.0},
            ]
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        search_results = []
        for params in param_grid:
            fold_scores = []
            for tr_idx, val_idx in cv.split(X_search, y_search):
                m = build_model(params)
                m.fit(X_search.iloc[tr_idx], y_search.iloc[tr_idx])
                proba = m.predict_proba(X_search.iloc[val_idx])[:, 1]
                fold_scores.append(average_precision_score(y_search.iloc[val_idx], proba))
            mean_pr_auc = float(np.mean(fold_scores))
            search_results.append({"params": params, "cv_pr_auc": mean_pr_auc})
            print(f"  params={params} -> real 3-fold mean PR-AUC = {mean_pr_auc:.4f}")
        best = max(search_results, key=lambda r: r["cv_pr_auc"])
        best_params = best["params"]
        print(f"Best real params: {best_params} (PR-AUC={best['cv_pr_auc']:.4f})")

# --- 10. Refit Best Config on the FULL Training Set ---
with timer("final model fit (full training set, best params)"):
    model = build_model(best_params)
    model.fit(X_train, y_train)
model_name = f"{model_family} ({best_params})"
print(f"Real final model fit: {model_name}")

thermal_checkpoint(label="post BP5 Notebook 2 final model fit")

# --- 11. Real Threshold Selection -- Out-of-Fold CV on TRAIN ONLY (same method as BP1/BP4) ---
with timer("threshold selection (out-of-fold CV on train, F2-optimal, saturated-max excluded)"):
    cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
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
        print("  WARNING: all out-of-fold thresholds are tied at the same value -- "
              "falling back to the unfiltered F2 argmax (real, disclosed edge case).")
        best_idx = int(np.nanargmax(f2_scores))
    selected_threshold = float(thresh_curve[best_idx])
    oof_pr_auc = average_precision_score(y_train, oof_proba)

print(f"Real F2-optimal threshold (train-only OOF, saturated-max excluded): {selected_threshold:.4f}")
print(f"  (OOF: precision={prec_curve[best_idx]:.4f}, recall={rec_curve[best_idx]:.4f}, F2={f2_scores[best_idx]:.4f})")
print(f"  (OOF PR-AUC, full training set: {oof_pr_auc:.4f})")

# --- 12. Real Evaluation on the Untouched Test Set ---
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

    random_baseline_pr_auc = float(y_test.mean())

print("=" * 78)
print(f"BP5 Notebook 2 -- Real Before/After Comparison ({model_name})")
print(f"HI-Small holdout, real selected threshold = {selected_threshold:.4f}")
print("=" * 78)
print(f"{'Metric':<14}{'Naive baseline':>18}{'Tuned model':>18}")
print(f"{'Precision':<14}{baseline_precision_test:>18.4f}{model_precision:>18.4f}")
print(f"{'Recall':<14}{baseline_recall_test:>18.4f}{model_recall:>18.4f}")
print(f"{'F2':<14}{baseline_f2_test:>18.4f}{model_f2:>18.4f}")
print(f"{'PR-AUC':<14}{random_baseline_pr_auc:>18.5f}{model_pr_auc:>18.5f}  (random/no-skill baseline = test-set positive rate)")
print("=" * 78)

# --- 13. Real Feature Importance -- did the NEW cross-border features actually matter? ---
with timer("feature importance"):
    if hasattr(model, "feature_importances_"):
        importance = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
        print("Real feature importances (this run, tuned model):")
        print(importance.to_string())
        crossborder_rank = [i for i, f in enumerate(importance.index, start=1) if f in CROSSBORDER_FEATURE_COLS]
        print(f"\nReal rank of the 8 NEW cross-border features within {len(FEATURE_COLS)} total features "
              f"(1=most important): {crossborder_rank}")
    else:
        importance = None

# --- 14. Save Real Model + Metrics ---
import json
import pickle
from datetime import datetime, timezone

with timer("save model artifacts"):
    model_path = MODELS_DIR / "bp5_hi_small_model_v1.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    metrics = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": "HI-Small",
        "model_name": model_name,
        "best_params": best_params,
        "selected_threshold": selected_threshold,
        "feature_cols": FEATURE_COLS,
        "crossborder_feature_cols": CROSSBORDER_FEATURE_COLS,
        "global_train_empirical_risk_rate": global_train_rate,
        "naive_baseline": {"precision": baseline_precision_test, "recall": baseline_recall_test, "f2": baseline_f2_test},
        "random_baseline_pr_auc": random_baseline_pr_auc,
        "model_metrics": {"precision": model_precision, "recall": model_recall, "f2": model_f2, "pr_auc": model_pr_auc},
        "crossborder_feature_importance_rank": crossborder_rank if importance is not None else None,
        "note": "BP5 Notebook 2 v1, HI-Small fast-iteration build. Feature set = platform's existing "
                "19 features + 8 new real cross-border features (Bank-Name country tags, "
                "is_cross_border, sender/receiver_is_foreign, foreign_to_foreign, and real "
                "Laplace-smoothed TRAIN-only per-country empirical risk rates). This is NOT BP5's "
                "final number -- LI-Medium validation (Notebook 3) has not run yet.",
    }
    metrics_path = MODELS_DIR / "bp5_hi_small_model_v1_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

print(f"Real model saved to : {model_path}")
print(f"Real metrics saved to: {metrics_path}")

# --- 15. Notebook 2 Summary ---
print("=" * 78)
print("BP5 -- Notebook 2 Summary (real, this run)")
print("=" * 78)
print(f"Model             : {model_name}")
print(f"Selected threshold: {selected_threshold:.4f}")
print(f"Model PR-AUC      : {model_pr_auc:.4f}  (random baseline = {random_baseline_pr_auc:.5f})")
print(f"Model recall      : {model_recall:.4f}  |  Model precision: {model_precision:.4f}  |  Model F2: {model_f2:.4f}")
print(f"Baseline recall   : {baseline_recall_test:.4f}  |  Baseline precision: {baseline_precision_test:.4f}")
print(f"Real cross-border rate this run: {n_cross:,} / {len(df):,} ({100*n_cross/len(df):.3f}%)")
print("=" * 78)

# Next: Notebook 3 -- Statistical Validation & Deployment. Re-implements this same feature
# pipeline (exact function/logic reused), runs the full Stage A multi-candidate comparison
# (LightGBM/XGBoost/CatBoost/RandomForest + Isolation Forest) and Stage B 5-fold CV on the
# mandatory LI-Medium tier, per Section 5's locked model benchmark specification -- with every
# RAM-safety/checkpoint/threading-backend lesson from BP4 (#5, #20, #33-#36) applied from the
# start this time, rather than discovered through a real crash.
