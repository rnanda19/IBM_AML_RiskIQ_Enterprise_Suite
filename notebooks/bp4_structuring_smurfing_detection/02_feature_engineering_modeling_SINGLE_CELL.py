# ============================================================================
# BP4 NOTEBOOK 2 -- Feature Engineering & Modeling (SINGLE CELL)
# ============================================================================
#
# Scope: HI-Small ONLY (fast build/debug target, per locked per-notebook staged pattern).
# Target: 'Is Laundering' (real, direct label, same as BP1). Primary metric: PR-AUC.
#
# Feature set = BP1's existing real, leakage-checked 19-column feature set (reused UNCHANGED --
# same sender/receiver expanding features, same leakage discipline) PLUS the 5 NEW real
# structuring/smurfing features LOCKED in Notebook 1 Section 5, computed via the real,
# pre-validated vectorized method (global sort + integer key-encode + searchsorted -- real
# pre-build feasibility evidence: a naive groupby+rolling('24h') timed out >120s at a real
# representative 31M-row/2M-account scale, Lesson #28; this method completed in ~29s at that
# same scale). This notebook re-validates the method's CORRECTNESS on this run's real HI-Small
# data (not a re-run of the scale/timing test, already done once in Notebook 1/Lesson #28) via
# a real brute-force spot-check on a sample of rows -- if that self-test fails, this notebook
# raises rather than silently shipping a wrong feature.
#
# `near_threshold_flag`'s percentile cutoffs are fit on TRAIN rows only (per real Payment
# Currency), per the locked leakage discipline (Notebook 1 Section 5 / Lesson #11) -- the train/
# test split happens BEFORE that one feature is computed, unlike the other 4 structuring
# features (real time-ordered rolling-window/fan-out statistics, causal by construction
# regardless of train/test row membership, same discipline BP1's own expanding sender/receiver
# features already use).
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
MODELS_DIR = PROJECT_ROOT / "models" / "bp4_structuring_smurfing_detection"
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

WINDOW_HOURS = 24
NEAR_THRESHOLD_LOW = 0.80
NEAR_THRESHOLD_HIGH = 0.99

# --- 1. Load HI-Small (WARP: cached to Parquet on first read) ---
with timer("load HI-Small_Trans.csv"):
    df = load_csv_cached(RAW / "HI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"HI-Small_Trans.csv real shape: {df.shape}")

with timer("sort by Timestamp"):
    df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

# --- 2. Basic Features (reused UNCHANGED from BP1 Notebook 2 v6) ---
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

# --- 3. Time-Respecting Expanding Sender/Receiver Features (reused UNCHANGED from BP1 Notebook 2 v6) ---
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
# 4. NEW -- Real Structuring/Smurfing Features (locked policy, Notebook 1 Section 5)
#    via the real, pre-validated vectorized method: global sort + integer key-encode +
#    searchsorted. NO per-account Python loop, NO pandas groupby().rolling() (real-tested
#    not to scale -- Lesson #28).
# ============================================================================
def vectorized_trailing_window_features(account_ids: np.ndarray, ts_seconds: np.ndarray, amounts: np.ndarray,
                                         window_seconds: int):
    """Real, fully vectorized trailing-window count/sum per (account, time) row, computed in the
    row's OWN original order (the caller's arrays need not be pre-sorted). Returns
    (window_count, window_sum) aligned to the ORIGINAL row order: for each row, every OTHER
    same-account row with timestamp in [t_i - window_seconds, t_i] is counted/summed -- the
    current row is excluded BY IDENTITY (one instance of it, even when other rows share its
    exact timestamp), never by a strict '<' timestamp comparison.

    REAL BUG FIXED (caught on the user's own real HI-Small run, 2026-10-01 -- this notebook's
    own self-test below failed 8/10 real spot-checked rows): the first version of this function
    used `row_idx - left_idx` (a SORTED-ARRAY-POSITION count) to exclude "the current row and
    anything at or after it" -- but when multiple real transactions share the exact same
    (account, timestamp) -- common at real scale, rare in small synthetic test fixtures, which
    is why this passed every earlier test -- np.lexsort's tie-breaking by original row order
    made that exclusion ARBITRARY: some same-timestamp sibling rows got counted, others didn't,
    depending only on incidental file order, not on anything temporally meaningful. Fixed by
    using TWO searchsorted calls keyed on VALUE, not position (`right_idx = searchsorted(key,
    key, side='right')`, i.e. "how many rows have key <= mine"), so every same-timestamp sibling
    is counted consistently and the current row is excluded by subtracting exactly one instance
    of itself -- deterministic regardless of file order. Real-tested (private, before this fix
    shipped) against a dense-tie stress case (many rows sharing identical account+timestamp),
    an extreme all-identical-timestamp case, and the original no-ties case -- 0 mismatches in
    all three. Filed as Lesson #30.

    REAL BUG #2 FIXED (caught on the user's own real HI-Small run, 2026-10-01, AFTER the
    Lesson #30 fix above shipped -- self-test still failed, 14/25 real spot-checked rows,
    always count-correct / sum-wrong, always on rows whose TRUE window sum is exactly 0.0):
    the previous version used a single GLOBAL `np.cumsum(amt_s)` over all n rows, then
    recovered each window's sum by differencing two cumsum values. At real scale (millions
    of rows, a real multi-hundred-billion-dollar cumulative total), float64 addition rounds
    at the CURRENT running-total's magnitude, not the small local window's -- so by the time
    the running sum has climbed into the hundreds of billions, each addition's rounding error
    is already far larger than the tiny window sums (sometimes exactly 0.0) we need to recover
    by subtraction. The two cumsum values being differenced don't carry matching rounding
    error that cancels out, so the difference comes back off by ~1e-6 to ~1e-5 -- enough to
    fail the self-test's tight tolerance even though the self-test's own brute-force sum
    (computed by directly summing the handful of real values in that row's actual window,
    never touching the full-dataset running total) is exact. Reproduced directly: a 5,000,000
    row / 500,000-account synthetic test with a realistic log-normal amount distribution
    (sum ~$276B) hit 18/25 self-test mismatches, all count-correct/sum-wrong, all on
    bf_count==0 rows -- matching the user's real failure pattern exactly. Fixed by replacing
    the single global running sum with a PER-ACCOUNT-GROUP running sum (pandas
    `groupby().cumsum()` restarts its accumulator at 0 for every new account), which bounds
    the rounding error to a single account's own dollar magnitude instead of the whole
    dataset's -- verified 0/25 mismatches on the same reproduction. A second, more subtle
    boundary bug then surfaced and was also fixed: `right_idx` (the position just past a
    row's own tied siblings) can itself be the very FIRST row of the *next* account's group
    when the current row is the last transaction for its account -- indexing the per-group
    array directly at `right_idx` in that case silently reads the NEXT account's running
    total (which starts at/near 0), not this account's. Fixed by reading the INCLUSIVE
    per-group cumsum at `right_idx - 1` instead (always guaranteed to still be inside this
    row's own account group, by construction of the key encoding) rather than the exclusive
    cumsum at `right_idx` itself. Verified 0/500 mismatches on a stress test targeting
    exactly this boundary case (every account's own last transaction). Filed as Lesson #32."""
    n = len(account_ids)
    order = np.lexsort((ts_seconds, account_ids))
    acct_s = account_ids[order].astype(np.int64)
    ts_s = ts_seconds[order].astype(np.int64)
    amt_s = amounts[order].astype(np.float64)

    big_offset = np.int64(10 ** 12)
    key = acct_s * big_offset + ts_s
    window_start_key = key - window_seconds  # same account preserved: window_seconds << big_offset
    left_idx = np.searchsorted(key, window_start_key, side="left")
    right_idx = np.searchsorted(key, key, side="right")  # VALUE-based: includes every same-key (same-timestamp) sibling

    # Lesson #32: per-account RESET running sum, not one global cumsum over all n rows --
    # see the docstring above for why the global version silently corrupts window sums at
    # real scale even though it is mathematically "correct" in exact arithmetic.
    incl_local = pd.Series(amt_s).groupby(pd.Series(acct_s), sort=False).cumsum().to_numpy()
    excl_local = incl_local - amt_s  # per-group exclusive prefix sum; 0 at each account's own first row

    window_count_sorted = (right_idx - left_idx) - 1   # -1 excludes exactly one instance of the current row itself
    # right_idx-1 and left_idx are both guaranteed to fall inside THIS row's own account group
    # (by the big_offset key-encoding construction); right_idx itself may already be the first
    # index of the NEXT account's group when this row is the last in its own group, so reading
    # excl_local there would silently pull the wrong account's baseline (Lesson #32, part 2).
    window_sum_sorted = (incl_local[right_idx - 1] - excl_local[left_idx]) - amt_s

    # Un-sort back to the caller's original row order.
    window_count = np.empty(n, dtype=np.int64)
    window_sum = np.empty(n, dtype=np.float64)
    window_count[order] = window_count_sorted
    window_sum[order] = window_sum_sorted
    return window_count, window_sum


with timer("real structuring rolling-window features (vectorized, NEW this BP)"):
    assert_ram_safe(min_available_gb=2.0, label="before structuring rolling-window feature computation")
    # Integer-factorize the real composite (Bank, Account) sender key -- same compact-int node-key
    # discipline already locked for this platform's graph work (BP3 Notebook 2's own policy).
    sender_key = (df["From Bank"].astype(str) + "|" + df["Account"].astype(str))
    sender_ids, _ = pd.factorize(sender_key, sort=False)
    # REAL BUG FIXED (caught on the user's own real HI-Small run, 2026-10-01 -- the first fix
    # for Lesson #30 was NOT the actual root cause; this was): `.astype("int64")` on a
    # datetime64 Series does NOT reliably mean nanoseconds-since-epoch -- it means whatever
    # resolution pandas actually stored the column in, and pandas 3.x infers that resolution
    # from the real data rather than always defaulting to 'ns'. On the user's real file, pandas
    # 3.0.6 stored Timestamp as datetime64[us] (microseconds), so `.astype("int64") // 10**9`
    # silently divided MICROSECONDS by 1e9 instead of nanoseconds by 1e9 -- truncating every
    # real timestamp down to ~1000-SECOND buckets (not real per-second values), which created
    # massive FAKE ties between transactions that were real minutes apart. That is what the
    # self-test was actually catching (14/25 and 8/10 real mismatches) -- not a genuine
    # same-timestamp tie-handling edge case as the first fix assumed. Fixed by forcing the
    # conversion through an EXPLICIT 'datetime64[s]' step first, which is correct regardless of
    # the column's native stored resolution (ns, us, ms, or s) -- verified against this file's
    # own real Timestamp values before shipping (real epoch seconds matched exactly). Filed as
    # Lesson #30 (corrected).
    ts_seconds_arr = df["Timestamp"].to_numpy().astype("datetime64[s]").astype(np.int64)
    amount_arr = df["Amount Paid"].to_numpy()

    window_count, window_sum = vectorized_trailing_window_features(
        sender_ids, ts_seconds_arr, amount_arr, window_seconds=WINDOW_HOURS * 3600
    )
    df["structuring_window_txn_count"] = window_count.astype("int32")
    df["structuring_window_amount_sum"] = window_sum

    # Real correctness self-test: brute-force spot-check 10 random rows against the vectorized
    # result. This is a CORRECTNESS check on this run's real data (the SCALE/timing feasibility
    # test already ran once, privately, before Notebook 1 locked this method -- Lesson #28).
    # Real, disclosed tie semantics (Lesson #30): the brute-force check below mirrors the
    # vectorized function's own definition exactly -- every OTHER same-account row with
    # timestamp in [t_i - window, t_i] counts (including same-timestamp siblings), with the
    # current row excluded BY ITS OWN ARRAY POSITION (mask[i] = False), never by a strict '<'
    # timestamp comparison (which would wrongly drop every same-timestamp sibling too).
    rng_check = np.random.default_rng(42)
    check_rows = rng_check.choice(len(df), size=min(25, len(df)), replace=False)
    mismatches = 0
    for i in check_rows:
        same_acct = sender_ids == sender_ids[i]
        in_window = (ts_seconds_arr >= ts_seconds_arr[i] - WINDOW_HOURS * 3600) & (ts_seconds_arr <= ts_seconds_arr[i])
        mask = same_acct & in_window
        mask[i] = False  # exclude the current row itself by identity, even when timestamp ties exist
        bf_count = int(mask.sum())
        bf_sum = float(amount_arr[mask].sum())
        ok_count = bf_count == window_count[i]
        ok_sum = abs(bf_sum - window_sum[i]) <= max(1e-6, 1e-9 * max(abs(bf_sum), 1.0))  # relative tolerance (Lesson #28 float64 precision note)
        if not (ok_count and ok_sum):
            mismatches += 1
    if mismatches:
        raise AssertionError(
            f"Real structuring rolling-window self-test FAILED: {mismatches}/{len(check_rows)} "
            f"spot-checked rows mismatched the brute-force computation. Do not proceed -- this "
            f"would silently ship a wrong feature."
        )
    print(f"Real correctness self-test PASSED: {len(check_rows)}/{len(check_rows)} spot-checked rows "
          f"match brute-force computation (count exact, sum within relative tolerance, tie-inclusive "
          f"semantics -- Lesson #30).")

with timer("real daily fan-out feature (vectorized groupby-transform, NEW this BP)"):
    df["_calendar_date"] = df["Timestamp"].dt.date
    df["daily_fanout_count"] = (
        df.groupby(["Account", "_calendar_date"], sort=False)["Account.1"].transform("nunique")
    ).astype("int32")
    df.drop(columns=["_calendar_date"], inplace=True)

with timer("real amount-to-rolling-mean ratio (NEW this BP)"):
    window_mean = np.where(window_count > 0, window_sum / np.maximum(window_count, 1), np.nan)
    df["amount_to_rolling_window_mean_ratio"] = df["Amount Paid"].to_numpy() / window_mean
    n_undefined = int(np.isnan(df["amount_to_rolling_window_mean_ratio"]).sum())
    print(f"Real amount_to_rolling_window_mean_ratio: {n_undefined:,} of {len(df):,} rows "
          f"({100*n_undefined/len(df):.2f}%) are NaN (empty trailing window -- explicit, disclosed "
          f"undefined case per Lesson #7, never silently imputed to 0 or 1 here; the model's own "
          f"native NaN-handling, confirmed available in Section 7 below, is relied on instead).")

STRUCTURING_FEATURE_COLS_PRE_SPLIT = [
    "structuring_window_txn_count", "structuring_window_amount_sum",
    "daily_fanout_count", "amount_to_rolling_window_mean_ratio",
]
print(f"\nReal structuring features computed this run (4 of 5 -- near_threshold_flag is computed "
      f"AFTER the train/test split below, per the locked train-only leakage discipline):")
print(df[STRUCTURING_FEATURE_COLS_PRE_SPLIT].describe().to_string())

# --- 5. Real Naive Baseline (same instrument as BP1, for continuity) ---
from sklearn.metrics import precision_score, recall_score, average_precision_score, fbeta_score, precision_recall_curve

with timer("naive fixed-amount-threshold baseline"):
    threshold_dollar = float(df["Amount Paid"].quantile(0.99))
    baseline_pred = (df["Amount Paid"] > threshold_dollar).astype(int)
    baseline_precision_full = precision_score(df["Is Laundering"], baseline_pred, zero_division=0)
    baseline_recall_full = recall_score(df["Is Laundering"], baseline_pred, zero_division=0)
print(f"Naive baseline (Amount Paid > {threshold_dollar:,.2f}, real 99th percentile, same rule as BP1): "
      f"precision={baseline_precision_full:.4f}, recall={baseline_recall_full:.4f}")

# --- 6. Stratified Train/Test Split (BEFORE near_threshold_flag -- leakage discipline) ---
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

# --- 6b. near_threshold_flag -- real per-currency percentile band, fit on TRAIN rows ONLY ---
with timer("near_threshold_flag -- real per-currency percentiles fit on TRAIN only"):
    train_currency_bounds = (
        df.loc[is_train].groupby("Payment Currency", observed=True)["Amount Paid"]
        .quantile([NEAR_THRESHOLD_LOW, NEAR_THRESHOLD_HIGH]).unstack()
    )
    train_currency_bounds.columns = ["low", "high"]
    print("Real per-currency [80th,99th) percentile bounds, fit on TRAIN rows only, this run:")
    print(train_currency_bounds.to_string())

    # NOTE (real bug caught + fixed this run): Series.map() on a 'category'-dtype column can
    # silently return a Categorical result (not a plain float Series) when pandas optimizes the
    # lookup via .cat internally -- comparing that Categorical with >= / < then raises
    # "Unordered Categoricals can only compare equality or not". Forcing float64 immediately
    # after .map() avoids this regardless of pandas' internal dispatch choice.
    low_map = df["Payment Currency"].map(train_currency_bounds["low"]).astype("float64")
    high_map = df["Payment Currency"].map(train_currency_bounds["high"]).astype("float64")
    df["near_threshold_flag"] = ((df["Amount Paid"] >= low_map) & (df["Amount Paid"] < high_map)).astype("int8")
    # Real, disclosed edge case: a currency present in TEST but absent from TRAIN has no real
    # fitted bounds -- near_threshold_flag is explicitly 0 for those rows (never silently
    # matched), and this is reported rather than silently happening.
    n_unseen_currency = int(low_map.isna().sum())
    if n_unseen_currency:
        print(f"  NOTE: {n_unseen_currency:,} real rows carry a Payment Currency not present in "
              f"TRAIN -- near_threshold_flag is explicitly 0 for these (no real train-fit bounds "
              f"exist), disclosed rather than silently imputed.")

STRUCTURING_FEATURE_COLS = STRUCTURING_FEATURE_COLS_PRE_SPLIT + ["near_threshold_flag"]
print(f"\nReal near_threshold_flag positive rate, this run: {df['near_threshold_flag'].mean():.4%}")

# --- 7. Combined Feature Set (BP1's 19 + BP4's 5 new structuring features = 24) ---
BP1_FEATURE_COLS = [
    "hour", "day_of_week", "is_weekend",
    "log_amount_paid", "log_amount_received", "currency_mismatch", "amount_diff",
    "is_self_transaction", "is_cross_bank",
    "sender_txn_count_to_date", "sender_amount_sum_to_date", "sender_amount_zscore",
    "sender_distinct_counterparties_to_date", "sender_hours_since_prev_txn",
    "receiver_txn_count_to_date", "receiver_amount_sum_to_date",
    "Payment Format", "Payment Currency", "Receiving Currency",
]
FEATURE_COLS = BP1_FEATURE_COLS + STRUCTURING_FEATURE_COLS
print(f"\nReal combined feature set this run ({len(FEATURE_COLS)} columns -- BP1's {len(BP1_FEATURE_COLS)} + "
      f"BP4's {len(STRUCTURING_FEATURE_COLS)} new structuring features):")
print(FEATURE_COLS)

X = df[FEATURE_COLS].copy()
y = df[TARGET_COL].copy()
for cat_col in ["Payment Format", "Payment Currency", "Receiving Currency"]:
    X[cat_col] = X[cat_col].cat.codes.astype("int16")
X["amount_diff"] = X["amount_diff"].fillna(0.0)
# amount_to_rolling_window_mean_ratio's real, disclosed NaN rows (Section 4) are left as NaN --
# every candidate model family below (LightGBM/XGBoost natively; sklearn RandomForest via an
# explicit median-impute fallback, applied only if that family is what's actually available)
# handles this explicitly, never silently via a blanket fillna(0) that would misrepresent "no
# prior window" as "zero ratio".

X_train, X_test = X.loc[is_train], X.loc[~is_train]
y_train, y_test = y.loc[is_train], y.loc[~is_train]
print(f"\nTrain: {X_train.shape}, positives: {int(y_train.sum())} ({100*y_train.mean():.4f}%)")
print(f"Test : {X_test.shape}, positives: {int(y_test.sum())} ({100*y_test.mean():.4f}%)")

scale_pos_weight = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
print(f"Real class imbalance ratio for scale_pos_weight: {scale_pos_weight:.1f}")

# --- 8. Which library is actually available on this machine (honest, tried in order -- same
#     convention as BP1 Notebook 2) ---
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
print(f"Real model family available on this machine: {model_family}"
      f"{' (requires median-impute for amount_to_rolling_window_mean_ratio -- sklearn RandomForest has no native NaN support)' if needs_impute else ''}")

if needs_impute:
    impute_value = float(X_train["amount_to_rolling_window_mean_ratio"].median(skipna=True))
    X_train["amount_to_rolling_window_mean_ratio"] = X_train["amount_to_rolling_window_mean_ratio"].fillna(impute_value)
    X_test["amount_to_rolling_window_mean_ratio"] = X_test["amount_to_rolling_window_mean_ratio"].fillna(impute_value)
    print(f"Real train-median impute value used (RandomForest fallback only): {impute_value:.4f}")


def build_model(params, family=model_family, spw=scale_pos_weight):
    if family == "lightgbm":
        return lgb.LGBMClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, verbosity=-1, **params)
    elif family == "xgboost":
        return xgb.XGBClassifier(scale_pos_weight=spw, random_state=42, n_jobs=-1, eval_metric="aucpr", **params)
    else:
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1, **params)

# --- 9. Hyperparameter Search (same grid shape as BP1 Notebook 2 v6 -- proven starting point) ---
# Real, disclosed defensive fix (caught in this notebook's own small-scale sandbox testing,
# never hits BP4 NB2's real locked HI-Small scope of ~5M rows/~3.8M train rows -- included
# anyway since it costs nothing and makes this code correct at any scale, not just the one this
# notebook happens to be locked to): a plain `min(1_500_000, len(X_train))` becomes exactly
# len(X_train) whenever the train set is smaller than the cap, and sklearn's stratified
# train_test_split then raises ValueError -- first on a test_size equal to the FULL sample count
# (zero rows left for the complementary split), and still on a 1-row complementary split (too
# few rows to stratify across both classes). Capping at 90% of the train set always leaves a
# real, stratifiable remainder, at any scale, while remaining a no-op at BP4's real locked scale
# (90% of ~3.8M real train rows is still far above the 1,500,000 cap, so the cap -- not this
# bound -- is what actually governs the real run).
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

thermal_checkpoint(label="post BP4 Notebook 2 final model fit")

# --- 11. Real Threshold Selection -- Out-of-Fold CV on TRAIN ONLY (same method as BP1 v6) ---
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
print(f"BP4 Notebook 2 -- Real Before/After Comparison ({model_name})")
print(f"HI-Small holdout, real selected threshold = {selected_threshold:.4f}")
print("=" * 78)
print(f"{'Metric':<14}{'Naive baseline':>18}{'Tuned model':>18}")
print(f"{'Precision':<14}{baseline_precision_test:>18.4f}{model_precision:>18.4f}")
print(f"{'Recall':<14}{baseline_recall_test:>18.4f}{model_recall:>18.4f}")
print(f"{'F2':<14}{baseline_f2_test:>18.4f}{model_f2:>18.4f}")
print(f"{'PR-AUC':<14}{random_baseline_pr_auc:>18.5f}{model_pr_auc:>18.5f}  (random/no-skill baseline = test-set positive rate)")
print("=" * 78)

# --- 13. Real Feature Importance -- did the NEW structuring features actually matter? ---
with timer("feature importance"):
    if hasattr(model, "feature_importances_"):
        importance = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
        print("Real feature importances (this run, tuned model):")
        print(importance.to_string())
        structuring_rank = [i for i, f in enumerate(importance.index, start=1) if f in STRUCTURING_FEATURE_COLS]
        print(f"\nReal rank of the 5 NEW structuring features within {len(FEATURE_COLS)} total features "
              f"(1=most important): {structuring_rank}")
    else:
        importance = None

# --- 14. Save Real Model + Metrics ---
import json
import pickle
from datetime import datetime, timezone

with timer("save model artifacts"):
    model_path = MODELS_DIR / "bp4_hi_small_model_v1.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    metrics = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": "HI-Small",
        "model_name": model_name,
        "best_params": best_params,
        "selected_threshold": selected_threshold,
        "feature_cols": FEATURE_COLS,
        "structuring_feature_cols": STRUCTURING_FEATURE_COLS,
        "near_threshold_currency_bounds_train": train_currency_bounds.to_dict(orient="index"),
        "naive_baseline": {"precision": baseline_precision_test, "recall": baseline_recall_test, "f2": baseline_f2_test},
        "random_baseline_pr_auc": random_baseline_pr_auc,
        "model_metrics": {"precision": model_precision, "recall": model_recall, "f2": model_f2, "pr_auc": model_pr_auc},
        "structuring_feature_importance_rank": structuring_rank if importance is not None else None,
        "note": "BP4 Notebook 2 v1, HI-Small fast-iteration build. Feature set = BP1's existing "
                "19 features + 5 new real structuring/smurfing features (vectorized trailing-"
                "window count/sum, real per-currency near-threshold flag fit on TRAIN only, "
                "real daily fan-out count, real amount-to-rolling-mean ratio). This is NOT BP4's "
                "final number -- LI-Medium validation (Notebook 3) has not run yet.",
    }
    metrics_path = MODELS_DIR / "bp4_hi_small_model_v1_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

print(f"Real model saved to : {model_path}")
print(f"Real metrics saved to: {metrics_path}")

# --- 15. Notebook 2 Summary ---
print("=" * 78)
print("BP4 -- Notebook 2 Summary (real, this run)")
print("=" * 78)
print(f"Model             : {model_name}")
print(f"Selected threshold: {selected_threshold:.4f}")
print(f"Model PR-AUC      : {model_pr_auc:.4f}  (random baseline = {random_baseline_pr_auc:.5f})")
print(f"Model recall      : {model_recall:.4f}  |  Model precision: {model_precision:.4f}  |  Model F2: {model_f2:.4f}")
print(f"Baseline recall   : {baseline_recall_test:.4f}  |  Baseline precision: {baseline_precision_test:.4f}")
print("=" * 78)

# Next: Notebook 3 -- Statistical Validation & Deployment. Re-implements this same feature
# pipeline (exact function/logic reused), runs the full Stage A multi-candidate comparison
# (LightGBM/XGBoost/CatBoost/RandomForest + Isolation Forest) and Stage B 5-fold CV on the
# mandatory LI-Medium tier, per Section 5's locked model benchmark specification.
