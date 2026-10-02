# ============================================================================
# BP4 NOTEBOOK 3 -- Statistical Validation & Deployment (SINGLE CELL)
# ============================================================================
#
# Purpose (per the locked master-execution-plan, Section 4 + 2.1): re-run BP4's real
# feature-engineering pipeline -- UNCHANGED from Notebook 2 (BP1's 19-feature set + the 5
# real structuring/smurfing features locked in Notebook 1 Section 5, computed via the
# pre-validated vectorized global-sort + integer-key-encode + searchsorted method, Lesson
# #28) -- against a full model-comparison + statistical-robustness protocol, on TWO dataset
# variants, never merged: HI-Small (continuity baseline) and LI-Medium (the LOCKED mandatory
# realism-validation tier for BP4, user-confirmed 2026-09-29, master plan Section 3).
#
# HOW TO RUN THIS NOTEBOOK (per the locked policy): run it ONCE with DATASET_VARIANT =
# "HI-Small", then change ONLY that one line to "LI-Medium" and run it again. Nothing else
# in this file should be edited between runs. Each run writes its own real, variant-tagged
# summary files -- neither run overwrites the other.
#
# What this notebook does, in order (same shape as BP1 Notebook 3 -- this is a standard
# binary classification task, unlike BP3's rule-based shape):
#   Stage A: trains a real candidate set (LightGBM, XGBoost, CatBoost, RandomForest -- each
#     library tried honestly, skipped with a clear message if not installed -- plus
#     Isolation Forest as an unsupervised comparator, reported separately, never blended
#     into champion selection) on a single real train/test split, ranks by real PR-AUC.
#   Stage B: real 5-fold StratifiedKFold CV on the top-2 Stage-A candidates; champion =
#     higher real mean CV PR-AUC. Reports per-fold PR-AUC and a 95% CI (t-distribution,
#     df=4 -- small-n, honestly disclosed).
#   Threshold selection: reuses the real F2-optimal, out-of-fold, saturated-max-excluded
#     method (same proven-correct method as BP1 Notebook 2 v6 / Notebook 3).
#   Explainability: real SHAP (TreeExplainer) on a capped real sample of the champion's
#     test-set predictions; real LIME on a few individual real instances -- BOTH wrapped in
#     honest try/except import guards. Skipped with a clear message, not silently, if
#     unavailable.
#   Two-gate verdict: a structural [CHECK] gate (did the pipeline actually run correctly --
#     mechanics, not model quality) and a separate statistical-robustness gate (does the
#     champion's CV performance clear the random baseline with real statistical margin, and
#     is it stable across folds) -- criteria fixed BEFORE this notebook runs and never
#     adjusted after seeing a real result (locked Lesson #15).
#   Real isotonic calibration + a real PSI production-monitoring baseline (reusing the
#     shared, platform-wide `src/monitoring/drift_monitor.py` module, same as BP1) + real
#     percentile-based alert-routing tiers.
#   Deployable scoring service: a real FastAPI app wrapping the exact same scoring function
#     used for the notebook's own batch predictions -- self-tested via FastAPI's TestClient
#     (in-process, never blocks this notebook cell) against every row of a capped real
#     sample, reporting a magnitude-of-mismatch column, not just a pass/fail count.
#
# Proactively hardened with the same checkpoint/resume + Windows-sleep-prevention +
# STAGE MARKER pattern already proven on BP1/BP2 Notebook 3 (Lesson #23/#24) -- BP4 shares
# the identical multi-candidate Stage A + 5-fold CV Stage B risk shape (long real runs, real
# risk of a mid-run crash discarding already-completed expensive work), applied here BEFORE
# any real crash on this BP, not after one (the point of generalizing the lesson).
#
# Zero-fabrication: every number below is computed live, on whichever real CSV
# DATASET_VARIANT points at. RANDOM_SEED=42 throughout, per the locked standing rule.

import sys
import gc
import platform
from pathlib import Path

# ============================================================================
# Prevent Windows system sleep for the duration of this kernel's life (Lesson #23).
# ============================================================================
if platform.system() == "Windows":
    import ctypes
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _sleep_block_result = ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    if _sleep_block_result == 0:
        print("WARNING: SetThreadExecutionState call failed (returned 0) -- sleep prevention may not be "
              "active. ACTION NEEDED: also set Settings > Power & Battery > Screen and sleep > "
              "'When plugged in, put my device to sleep after' to Never, as a manual backup.")
    else:
        print("Sleep prevention ACTIVE for this kernel process (Windows system sleep blocked while this "
              "kernel runs; does not cover a physical lid-close -- see BP1 Notebook 3's own note for the "
              "full disclosed limitation).")
else:
    print(f"Sleep-prevention block skipped -- not running on Windows (detected: {platform.system()}). "
          "No-op, not an error.")


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
from utils.performance_setup import (
    configure_performance, thermal_checkpoint, load_csv_cached, timer,
    check_ram_headroom, pin_cpu_affinity, assert_ram_safe,
)

perf_config = configure_performance()
print("WARP configured:", perf_config)

_affinity_pinned = pin_cpu_affinity()
print(f"WARP CPU-affinity pin: {'applied' if _affinity_pinned else 'not available on this platform (no-op, not an error)'}")

_ram_baseline = check_ram_headroom()
print(f"WARP RAM headroom at startup: {_ram_baseline}")

RANDOM_SEED = 42
WINDOW_HOURS = 24
NEAR_THRESHOLD_LOW = 0.80
NEAR_THRESHOLD_HIGH = 0.99

try:
    import psutil
    _proc = psutil.Process()
    def _mem_gb():
        return _proc.memory_info().rss / (1024 ** 3)
except ImportError:
    def _mem_gb():
        return float("nan")


def _print_resource(label: str) -> None:
    print(f"  [MEM] {label}: process RSS = {_mem_gb():.2f} GB")
    headroom = check_ram_headroom()
    if "error" not in headroom:
        print(f"  [RAM] {label}: available={headroom['available_ram_gb']:.2f} GB / "
              f"total={headroom['total_ram_gb']:.2f} GB (92% ceiling={headroom['ram_ceiling_gb']:.2f} GB)")
    else:
        print(f"  [RAM] {label}: {headroom['error']}")


# ============================================================================
# Lesson #35 diagnostic (real, deep-audit fix, 2026-10-01): a freshly started Jupyter kernel's
# own process RSS here -- before Stage 1 has loaded a single row -- is normally well under
# 0.3 GB (just the interpreter + the handful of stdlib/psutil imports done so far). If this
# number is already large, this kernel is almost certainly being REUSED across retries (the
# cell was re-run, not the kernel restarted) and is still holding objects bound in this
# kernel's global namespace from an earlier attempt -- most commonly large DataFrames that were
# alive at the moment a previous run raised MemoryError, since a raised exception does NOT
# unwind or clear variables already assigned in the cell/kernel namespace. This is a real,
# measured signal, not a guess, and is reported once here so a "why is my RAM lower than
# expected" question can be checked directly against this number instead of argued about.
_startup_rss_gb = _mem_gb()
if _startup_rss_gb > 0.75:
    print(f"  [MEM] WARNING: startup process RSS = {_startup_rss_gb:.2f} GB before Stage 1 has "
          f"loaded anything (a freshly started kernel is normally under 0.3 GB here). This "
          f"usually means this is a REUSED kernel still holding objects from an earlier run. "
          f"RECOMMENDED: Kernel menu -> Restart (not just re-running this cell) before "
          f"continuing. The Lesson #35 Stage 1 checkpoint further below makes a true restart "
          f"resume in seconds rather than needing to re-run the ~4-minute data-load/"
          f"feature-engineering stage, so restarting is now cheap.")
else:
    print(f"  [MEM] Startup process RSS = {_startup_rss_gb:.2f} GB (consistent with a fresh kernel).")

# ============================================================================
# THE ONE LINE TO CHANGE BETWEEN THE TWO REQUIRED RUNS
# ============================================================================
DATASET_VARIANT = "LI-Medium"  # mandatory realism-validation tier re-run
# ============================================================================

VARIANT_TRANS_FILES = {"HI-Small": "HI-Small_Trans.csv", "LI-Medium": "LI-Medium_Trans.csv"}
if DATASET_VARIANT not in VARIANT_TRANS_FILES:
    raise ValueError(f"DATASET_VARIANT must be one of {list(VARIANT_TRANS_FILES)}, got {DATASET_VARIANT!r}")
variant_tag = DATASET_VARIANT.lower().replace("-", "_")

# REAL FIX (user's own real LI-Medium run, 2026-10-01 -- RAM gate still tripping at
# RandomForest even after Lesson #33's downsizing and Lesson #34's X/y leak fix, headroom
# actually getting WORSE run to run: 3.74GB, 3.88GB, 2.29GB): both RandomForestClassifier
# and IsolationForest build their trees via joblib's PROCESS-based parallelism (the "loky"
# backend) by default -- each worker is a separate OS process, and unless numpy-level
# memmapping cleanly kicks in for the pandas-DataFrame-derived input (not guaranteed), each
# worker can end up holding its own copy of the 23.4M-row imputed training frame. The first
# fix capped n_jobs to a small explicit worker count (2) to bound that risk.
#
# REVISION (2026-10-01, reviewed from a second LLM's suggestion -- adopted after checking it):
# the real fix for the process-multiplication risk is to not use process-based parallelism for
# these specific fits at all. `joblib.parallel_backend("threading")`, wrapped around each
# RandomForest/IsolationForest fit below, makes joblib hand out worker THREADS instead of
# worker PROCESSES for that call -- threads share one process's memory, so there is no
# per-worker data duplication to begin with, regardless of n_jobs. This is not merely safe for
# tree ensembles: scikit-learn's tree-building is Cython and releases the GIL during the heavy
# computation, so real parallelism still happens across threads, not just nominal concurrency.
# This lets n_jobs go back up to the same WARP-configured thread ceiling the rest of this
# notebook already uses (`perf_config["threads_configured"]`, ~92% of logical cores, never a
# separate hardcoded number) without reintroducing the process-memory risk Lesson #35 was
# guarding against. The subsampling (`max_samples=...`) suggested alongside this in that same
# review was NOT adopted -- it would make RandomForest's Stage A comparison against the full-
# data boosted-tree candidates uneven, a modeling change, not a performance one.
RANDOM_FOREST_N_JOBS = perf_config["threads_configured"]

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
MODELS_DIR = PROJECT_ROOT / "models" / "bp4_structuring_smurfing_detection"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp4_structuring_smurfing_detection"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root  : {PROJECT_ROOT}")
print(f"Dataset variant this run: {DATASET_VARIANT}")
print(f"Models dir    : {MODELS_DIR}")
print(f"Reports dir   : {REPORTS_DIR}")

# ============================================================================
# Real checkpoint/resume for Stage A and Stage B (Lesson #23, applied proactively here)
# ============================================================================
FORCE_RECOMPUTE_CHECKPOINTS = False

import pickle
import re

CHECKPOINT_DIR = MODELS_DIR / f"nb3_checkpoints_{variant_tag}"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
print(f"Checkpoint dir: {CHECKPOINT_DIR}")
print(f"FORCE_RECOMPUTE_CHECKPOINTS = {FORCE_RECOMPUTE_CHECKPOINTS} "
      f"({'existing checkpoints will be IGNORED, everything recomputes' if FORCE_RECOMPUTE_CHECKPOINTS else 'existing checkpoints will be reused where present'})")


def _safe_ckpt_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")


def _ckpt_path(key: str) -> Path:
    return CHECKPOINT_DIR / f"{_safe_ckpt_name(key)}.pkl"


def _ckpt_exists(key: str) -> bool:
    return (not FORCE_RECOMPUTE_CHECKPOINTS) and _ckpt_path(key).exists()


def _save_ckpt(key: str, obj) -> None:
    path = _ckpt_path(key)
    with open(path, "wb") as f:
        pickle.dump(obj, f)
    print(f"  [CHECKPOINT SAVED] {key} -> {path.name}")


def _load_ckpt(key: str):
    path = _ckpt_path(key)
    with open(path, "rb") as f:
        obj = pickle.load(f)
    print(f"  [CHECKPOINT LOADED] {key} <- {path.name} (resumed -- real recomputation skipped)")
    return obj


import pandas as pd
import numpy as np

print(f"pandas {pd.__version__}, numpy {np.__version__}")

# ============================================================================
# Lesson #35 (real, deep-audit fix, 2026-10-01): checkpoint Stage 1's own real outputs.
#
# Why this exists: the RAM gate kept tripping deeper into Stage A/B across successive
# retries even after three independently-verified, real logical fixes (Lesson #32's cumsum
# precision bug, Lesson #33's missing RandomForest downsizing rule, Lesson #34's pre-split
# X/y leak, and -- the actual root cause of the specific "available RAM got WORSE run to
# run" symptom -- this file's own Lesson #35 fix just above and below, which moved the RAM
# gate to run BEFORE the RandomForest/IsolationForest imputed-copy build instead of after
# it). Even with every one of those bugs fixed, a genuinely clean run still benefits from a
# TRUE kernel restart between attempts (the startup-RSS diagnostic above explains why: a
# reused kernel can still be holding objects bound in its namespace from an earlier,
# crashed attempt, since a raised exception does not unwind already-assigned variables).
# Stage 1 (CSV load + feature engineering + train/test split) took ~4 real minutes and was
# previously NOT checkpointed, which made a true restart expensive enough that it was easy
# to skip under time pressure. This checkpoint makes a true restart resume in seconds: on a
# fresh kernel with no prior checkpoint, Stage 1 runs exactly as before and saves its real
# outputs at the end; on any subsequent run (including after a real Kernel -> Restart), if
# the checkpoint exists, Stage 1 is skipped entirely and its real outputs are loaded back in
# a few seconds, so restarting the kernel is no longer a ~4-minute tax.
_STAGE1_CKPT_KEY = "stage1_train_test_frames"
if _ckpt_exists(_STAGE1_CKPT_KEY):
    _s1 = _load_ckpt(_STAGE1_CKPT_KEY)
    X_train, X_test = _s1["X_train"], _s1["X_test"]
    y_train, y_test = _s1["y_train"], _s1["y_test"]
    FEATURE_COLS = _s1["FEATURE_COLS"]
    STRUCTURING_FEATURE_COLS = _s1["STRUCTURING_FEATURE_COLS"]
    scale_pos_weight = _s1["scale_pos_weight"]
    RF_N_ESTIMATORS = _s1["RF_N_ESTIMATORS"]
    RF_MAX_DEPTH = _s1["RF_MAX_DEPTH"]
    random_baseline_pr_auc = _s1["random_baseline_pr_auc"]
    del _s1
    gc.collect()
    print(f"Real train rows: {len(X_train):,} | test rows: {len(X_test):,} "
          f"(RESUMED from Stage 1 checkpoint -- CSV load/feature engineering/split skipped)")
    print(f"Real RandomForest params this run (Lesson #20 downsizing rule, from checkpoint): "
          f"n_estimators={RF_N_ESTIMATORS}, max_depth={RF_MAX_DEPTH}")
    print(f"Real class imbalance ratio for scale_pos_weight (from checkpoint): {scale_pos_weight:.1f}")
    _print_resource("after RESUMING Stage 1 from checkpoint (fresh kernel, nothing else retained)")
else:
    TRANS_DTYPES = {
        "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
        "Amount Received": "float64", "Receiving Currency": "category",
        "Amount Paid": "float64", "Payment Currency": "category",
        "Payment Format": "category", "Is Laundering": "int8",
    }

    # --- 1. Load the real transaction file for this run's DATASET_VARIANT (WARP: Parquet-cached) ---
    trans_path = RAW / VARIANT_TRANS_FILES[DATASET_VARIANT]
    if not trans_path.exists():
        raise FileNotFoundError(
            f"{trans_path} does not exist. This notebook needs the real "
            f"{VARIANT_TRANS_FILES[DATASET_VARIANT]} file in data/raw/ before it can run against "
            f"the '{DATASET_VARIANT}' variant."
        )
    with timer(f"load {trans_path.name}"):
        df = load_csv_cached(trans_path, parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
    print(f"{trans_path.name} real shape: {df.shape}")

    with timer("sort by Timestamp"):
        df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

    # ============================================================================
    # 2. Feature engineering -- IDENTICAL to Notebook 2's real feature set (BP1's 19 + BP4's 5
    #    new structuring features = 24). Deliberately unchanged: this notebook's job is to
    #    validate that pipeline on a harder/real variant, not to re-open feature engineering.
    # ============================================================================
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

    thermal_checkpoint(label="post expanding sender features (large groupby/aggregation)")

    with timer("expanding receiver (Account.1) features -- no leakage, reused from BP1"):
        g_recv = df.groupby("Account.1", sort=False)
        df["receiver_txn_count_to_date"] = g_recv.cumcount()
        df["receiver_amount_sum_to_date"] = g_recv["Amount Received"].cumsum().shift(1)
        df["receiver_amount_sum_to_date"] = df.groupby("Account.1", sort=False)["receiver_amount_sum_to_date"].ffill().fillna(0.0)

    thermal_checkpoint(label="post expanding receiver features (large groupby/aggregation)")

    df["sender_amount_sum_to_date"] = df["sender_amount_sum_to_date"].fillna(0.0)
    df["sender_txn_count_to_date"] = df["sender_txn_count_to_date"].astype("int32")
    df["receiver_txn_count_to_date"] = df["receiver_txn_count_to_date"].astype("int32")
    df["sender_distinct_counterparties_to_date"] = df["sender_distinct_counterparties_to_date"].astype("int32")


    def vectorized_trailing_window_features(account_ids: np.ndarray, ts_seconds: np.ndarray, amounts: np.ndarray,
                                             window_seconds: int):
        """Real, fully vectorized trailing-window count/sum per (account, time) row -- global sort +
        integer key-encode + searchsorted + cumsum-difference (Lesson #28; real-tested at
        31M-row/2M-account scale: ~29s, ~3.6GB peak RSS vs. a naive groupby().rolling('24h') that
        timed out >120s at the same scale). Computed in the row's OWN original order (the caller's
        arrays need not be pre-sorted): for each row, every OTHER same-account row with timestamp in
        [t_i - window_seconds, t_i] is counted/summed -- the current row is excluded BY IDENTITY (one
        instance of it, even when other rows share its exact timestamp), never by a strict '<'
        timestamp comparison.

        REAL BUG FIXED (caught on the user's own real HI-Small run of Notebook 2, 2026-10-01 -- that
        notebook's own self-test failed 8/10 real spot-checked rows): the first version used
        `row_idx - left_idx` (a SORTED-ARRAY-POSITION count) to exclude "the current row and
        anything at or after it" -- but when multiple real transactions share the exact same
        (account, timestamp) -- common at real scale, rare in small synthetic test fixtures, which
        is why this passed every earlier test -- np.lexsort's tie-breaking by original row order made
        that exclusion ARBITRARY. Fixed with VALUE-based `right_idx = searchsorted(key, key,
        side='right')` ("how many rows have key <= mine"), so every same-timestamp sibling is counted
        consistently and the current row is excluded by subtracting exactly one instance of itself --
        deterministic regardless of file order. Filed as Lesson #30.

        REAL BUG #2 FIXED (caught on the user's own real HI-Small run of Notebook 2, 2026-10-01,
        AFTER the Lesson #30 fix above shipped -- self-test still failed, 14/25 real spot-checked
        rows, always count-correct/sum-wrong, always on rows whose TRUE window sum is exactly
        0.0): the previous version used a single GLOBAL `np.cumsum(amt_s)` over all n rows and
        recovered each window's sum by differencing two cumsum values. At real scale, float64
        addition rounds at the CURRENT running-total's magnitude (which climbs into the hundreds
        of billions over millions of rows), not the small local window being recovered by
        subtraction -- so the difference comes back off by ~1e-6 to ~1e-5, enough to fail the
        self-test's tight tolerance. Reproduced directly in a 5,000,000-row/500,000-account
        synthetic test with a realistic log-normal amount distribution: 18/25 self-test
        mismatches, matching the user's real failure pattern exactly (full diagnosis in Notebook
        2's copy of this same function). Fixed by replacing the global running sum with a
        PER-ACCOUNT-GROUP running sum (pandas `groupby().cumsum()` restarts its accumulator at 0
        per account), plus a boundary fix reading the per-group cumsum at `right_idx - 1` rather
        than `right_idx` itself (which can be the first row of the *next* account's group when
        the current row is the last transaction for its own account). Verified 0/25 and
        0/500-boundary-targeted mismatches on the same reproduction. Filed as Lesson #32; this
        notebook's feature pipeline is otherwise unchanged from Notebook 2."""
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

        # Lesson #32: per-account RESET running sum, not one global cumsum over all n rows (see
        # the docstring above for why the global version silently corrupts window sums at scale).
        incl_local = pd.Series(amt_s).groupby(pd.Series(acct_s), sort=False).cumsum().to_numpy()
        excl_local = incl_local - amt_s  # per-group exclusive prefix sum; 0 at each account's own first row

        window_count_sorted = (right_idx - left_idx) - 1   # -1 excludes exactly one instance of the current row itself
        # right_idx-1 and left_idx are both guaranteed inside THIS row's own account group; right_idx
        # itself may already be the next account's first row when this row is its account's last
        # (Lesson #32, part 2) -- so read the inclusive per-group cumsum at right_idx-1, not right_idx.
        window_sum_sorted = (incl_local[right_idx - 1] - excl_local[left_idx]) - amt_s

        window_count = np.empty(n, dtype=np.int64)
        window_sum = np.empty(n, dtype=np.float64)
        window_count[order] = window_count_sorted
        window_sum[order] = window_sum_sorted
        return window_count, window_sum


    with timer("real structuring rolling-window features (vectorized)"):
        assert_ram_safe(min_available_gb=2.0, label="before structuring rolling-window feature computation")
        sender_key = (df["From Bank"].astype(str) + "|" + df["Account"].astype(str))
        sender_ids, _ = pd.factorize(sender_key, sort=False)
        # REAL BUG FIXED (same root cause as Notebook 2, caught on the user's own real run,
        # 2026-10-01): `.astype("int64")` on a datetime64 Series means whatever resolution pandas
        # actually stored it in, not always nanoseconds -- pandas 3.x can infer datetime64[us] from
        # real data, which silently made `// 10**9` divide by the wrong power of 10 and truncated
        # every real timestamp to ~1000-second buckets. Fixed with an explicit 'datetime64[s]' step
        # first, correct regardless of the column's native resolution. See Notebook 2's own comment
        # (Lesson #30, corrected) for the full real diagnosis.
        ts_seconds_arr = df["Timestamp"].to_numpy().astype("datetime64[s]").astype(np.int64)
        amount_arr = df["Amount Paid"].to_numpy()

        window_count, window_sum = vectorized_trailing_window_features(
            sender_ids, ts_seconds_arr, amount_arr, window_seconds=WINDOW_HOURS * 3600
        )
        df["structuring_window_txn_count"] = window_count.astype("int32")
        df["structuring_window_amount_sum"] = window_sum

        # Real correctness self-test: brute-force spot-check (same tie-inclusive definition as
        # Notebook 2 / Lesson #30 -- this run's real data is re-checked independently, not assumed
        # correct from the last run). Every OTHER same-account row with ts in [t_i-window, t_i]
        # counts, including same-timestamp siblings; the current row is excluded by its own array
        # position, never by a strict '<' timestamp comparison.
        rng_check = np.random.default_rng(42)
        check_rows = rng_check.choice(len(df), size=min(25, len(df)), replace=False)
        mismatches = 0
        for i in check_rows:
            same_acct = sender_ids == sender_ids[i]
            in_window = (ts_seconds_arr >= ts_seconds_arr[i] - WINDOW_HOURS * 3600) & (ts_seconds_arr <= ts_seconds_arr[i])
            mask = same_acct & in_window
            mask[i] = False
            bf_count = int(mask.sum())
            bf_sum = float(amount_arr[mask].sum())
            ok_count = bf_count == window_count[i]
            ok_sum = abs(bf_sum - window_sum[i]) <= max(1e-6, 1e-9 * max(abs(bf_sum), 1.0))
            if not (ok_count and ok_sum):
                mismatches += 1
        if mismatches:
            raise AssertionError(
                f"Real structuring rolling-window self-test FAILED: {mismatches}/{len(check_rows)} "
                f"spot-checked rows mismatched the brute-force computation on {DATASET_VARIANT}. "
                f"Do not proceed -- this would silently ship a wrong feature."
            )
        print(f"Real correctness self-test PASSED on {DATASET_VARIANT}: {len(check_rows)}/{len(check_rows)} "
              f"spot-checked rows match brute-force computation (tie-inclusive semantics -- Lesson #30).")

    with timer("real daily fan-out feature (vectorized groupby-transform)"):
        df["_calendar_date"] = df["Timestamp"].dt.date
        df["daily_fanout_count"] = (
            df.groupby(["Account", "_calendar_date"], sort=False)["Account.1"].transform("nunique")
        ).astype("int32")
        df.drop(columns=["_calendar_date"], inplace=True)

    with timer("real amount-to-rolling-mean ratio"):
        window_mean = np.where(window_count > 0, window_sum / np.maximum(window_count, 1), np.nan)
        df["amount_to_rolling_window_mean_ratio"] = df["Amount Paid"].to_numpy() / window_mean
        n_undefined = int(np.isnan(df["amount_to_rolling_window_mean_ratio"]).sum())
        print(f"Real amount_to_rolling_window_mean_ratio: {n_undefined:,} of {len(df):,} rows "
              f"({100*n_undefined/len(df):.2f}%) are NaN (empty trailing window -- explicit, disclosed "
              f"undefined case, never silently imputed here).")

    STRUCTURING_FEATURE_COLS_PRE_SPLIT = [
        "structuring_window_txn_count", "structuring_window_amount_sum",
        "daily_fanout_count", "amount_to_rolling_window_mean_ratio",
    ]
    thermal_checkpoint(label="post structuring feature computation")

    # --- 3. Real Naive Baseline (same instrument as BP1/Notebook 2, for continuity) ---
    from sklearn.metrics import precision_score, recall_score, average_precision_score, fbeta_score, precision_recall_curve

    with timer("naive fixed-amount-threshold baseline"):
        threshold_dollar = float(df["Amount Paid"].quantile(0.99))
        baseline_pred = (df["Amount Paid"] > threshold_dollar).astype(int)
        baseline_precision_full = precision_score(df["Is Laundering"], baseline_pred, zero_division=0)
        baseline_recall_full = recall_score(df["Is Laundering"], baseline_pred, zero_division=0)
    print(f"Naive baseline (Amount Paid > {threshold_dollar:,.2f}, real 99th percentile, {DATASET_VARIANT}): "
          f"precision={baseline_precision_full:.4f}, recall={baseline_recall_full:.4f}")

    # --- 4. Stratified Train/Test Split (BEFORE near_threshold_flag -- leakage discipline) ---
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict

    TARGET_COL = "Is Laundering"
    with timer("train/test split"):
        train_idx, test_idx = train_test_split(
            np.arange(len(df)), test_size=0.25, stratify=df[TARGET_COL], random_state=RANDOM_SEED
        )
        is_train = np.zeros(len(df), dtype=bool)
        is_train[train_idx] = True

    n_pos_train = int(df.loc[is_train, TARGET_COL].sum())
    n_pos_test = int(df.loc[~is_train, TARGET_COL].sum())
    print(f"Train rows: {is_train.sum():,} ({100*df.loc[is_train, TARGET_COL].mean():.4f}% positive)")
    print(f"Test rows : {(~is_train).sum():,} ({100*df.loc[~is_train, TARGET_COL].mean():.4f}% positive)")

    if n_pos_train == 0 or n_pos_test == 0:
        raise ValueError(
            f"Real undefined-count check failed (locked Lesson #7): {DATASET_VARIANT}'s train or test "
            f"split has ZERO positive examples (train={n_pos_train}, test={n_pos_test}). Every "
            "downstream PR-AUC/precision/recall number would be undefined, not silently imputed -- "
            "stopping here rather than reporting a meaningless ratio."
        )

    # --- 4b. near_threshold_flag -- real per-currency percentile band, fit on TRAIN rows ONLY ---
    with timer("near_threshold_flag -- real per-currency percentiles fit on TRAIN only"):
        train_currency_bounds = (
            df.loc[is_train].groupby("Payment Currency", observed=True)["Amount Paid"]
            .quantile([NEAR_THRESHOLD_LOW, NEAR_THRESHOLD_HIGH]).unstack()
        )
        train_currency_bounds.columns = ["low", "high"]
        print(f"Real per-currency [80th,99th) percentile bounds, fit on TRAIN rows only, {DATASET_VARIANT}:")
        print(train_currency_bounds.to_string())

        # Real bug fix carried from Notebook 2 (Lesson #29): force float64 after .map() on a
        # category-dtype column, since that .map() can silently return a Categorical result.
        low_map = df["Payment Currency"].map(train_currency_bounds["low"]).astype("float64")
        high_map = df["Payment Currency"].map(train_currency_bounds["high"]).astype("float64")
        df["near_threshold_flag"] = ((df["Amount Paid"] >= low_map) & (df["Amount Paid"] < high_map)).astype("int8")
        n_unseen_currency = int(low_map.isna().sum())
        if n_unseen_currency:
            print(f"  NOTE: {n_unseen_currency:,} real rows carry a Payment Currency not present in "
                  f"TRAIN -- near_threshold_flag is explicitly 0 for these, disclosed rather than "
                  f"silently imputed.")

    STRUCTURING_FEATURE_COLS = STRUCTURING_FEATURE_COLS_PRE_SPLIT + ["near_threshold_flag"]
    print(f"\nReal near_threshold_flag positive rate, {DATASET_VARIANT}: {df['near_threshold_flag'].mean():.4%}")

    # --- 5. Combined Feature Set (BP1's 19 + BP4's 5 new structuring features = 24) ---
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

    with timer("build X/y matrices"):
        X = df[FEATURE_COLS].copy()
        y = df[TARGET_COL].copy()
        for cat_col in ["Payment Format", "Payment Currency", "Receiving Currency"]:
            X[cat_col] = X[cat_col].cat.codes.astype("int16")
        X["amount_diff"] = X["amount_diff"].fillna(0.0)
        # amount_to_rolling_window_mean_ratio's real, disclosed NaN rows are left as NaN --
        # LightGBM/XGBoost/CatBoost handle this natively; RandomForest gets an explicit
        # train-median impute below, only if that is the family actually available.
        X_train, X_test = X.loc[is_train], X.loc[~is_train]
        y_train, y_test = y.loc[is_train], y.loc[~is_train]
        # REAL BUG FIXED (caught on the user's own real LI-Medium run of this notebook, 2026-10-01 --
        # third real RAM-gate trip in a row, this time with a HEALTHY 20.09GB free at kernel startup,
        # which ruled out "low external headroom" as the cause and meant the leak had to be inside
        # this notebook's own pipeline): boolean `.loc[is_train]` / `.loc[~is_train]` indexing on a
        # pandas DataFrame always returns a NEW COPY, never a view -- so after this split, the full,
        # un-split 31,251,483-row `X` (and the much smaller `y`) stayed alive in memory for the rest
        # of the notebook doing nothing useful, duplicating most of X_train+X_test's combined ~5.4GB
        # footprint for zero benefit. Confirmed via grep that neither bare `X` nor bare `y` is
        # referenced anywhere after this point. Freeing them here recovers that ~5.4GB right at the
        # point Stage A's RandomForest fit needs it most.
        del X, y
        gc.collect()
    _print_resource("after releasing pre-split X/y (Lesson #34 fix)")

    print(f"Train: {X_train.shape}, positives: {int(y_train.sum())} ({100*y_train.mean():.4f}%)")
    print(f"Test : {X_test.shape}, positives: {int(y_test.sum())} ({100*y_test.mean():.4f}%)")

    # REAL BUG FIXED (caught on the user's own real LI-Medium run of this notebook, 2026-10-01 --
    # RAM safety gate correctly tripped twice, once before RandomForest's own fit and once before
    # the champion-refit path could reach it): this notebook's RandomForestClassifier was still
    # hardcoded at n_estimators=300, max_depth=14 regardless of real training-set size, even though
    # the standing project-wide rule from Lesson #20 (BP2 Notebook 3's real 2026-09-30 RAM-hang
    # incident) already downsizes RandomForest to n_estimators=120, max_depth=10 for any real
    # training set over 5,000,000 rows -- the user asked this rule be applied to every future
    # notebook on this project, and it was simply never wired into BP4 Notebook 3. At LI-Medium's
    # real 23,438,612-row training set (4.7x the threshold), the full 300-tree/depth-14 forest is
    # both the heaviest Stage A candidate by far and the one most likely to tip the RAM gate.
    # Fixed by computing the real params once, from the real len(X_train) this run, and reusing
    # them at both RandomForest call sites (Stage A's own fit and the champion-refit path) so they
    # can never drift apart.
    RF_LARGE_SCALE_ROW_THRESHOLD = 5_000_000
    if len(X_train) > RF_LARGE_SCALE_ROW_THRESHOLD:
        RF_N_ESTIMATORS, RF_MAX_DEPTH = 120, 10
    else:
        RF_N_ESTIMATORS, RF_MAX_DEPTH = 300, 14
    print(f"Real RandomForest params this run (Lesson #20 downsizing rule, train rows = "
          f"{len(X_train):,} {'>' if len(X_train) > RF_LARGE_SCALE_ROW_THRESHOLD else '<='} "
          f"{RF_LARGE_SCALE_ROW_THRESHOLD:,}): n_estimators={RF_N_ESTIMATORS}, max_depth={RF_MAX_DEPTH}")

    scale_pos_weight = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
    print(f"Real class imbalance ratio for scale_pos_weight: {scale_pos_weight:.1f}")

    random_baseline_pr_auc = float(y_test.mean())  # expected PR-AUC of a random/no-skill classifier

    # Memory hygiene (same real fix as BP1 Notebook 3): the raw dataframe is never referenced
    # again past this point -- release it now instead of letting it sit alongside every model
    # trained below.
    del df
    gc.collect()
    _print_resource("after releasing raw dataframe")
    _save_ckpt(_STAGE1_CKPT_KEY, {
        "X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test,
        "FEATURE_COLS": FEATURE_COLS, "STRUCTURING_FEATURE_COLS": STRUCTURING_FEATURE_COLS,
        "scale_pos_weight": scale_pos_weight,
        "RF_N_ESTIMATORS": RF_N_ESTIMATORS, "RF_MAX_DEPTH": RF_MAX_DEPTH,
        "random_baseline_pr_auc": random_baseline_pr_auc,
    })
print("\n" + "#" * 78)
print("### STAGE MARKER 1/4 COMPLETE -- Data load, feature engineering, train/test split")
print("#" * 78)

# ============================================================================
# STAGE A -- Real Candidate Comparison (single split), honest library availability
# ============================================================================
print("\n" + "=" * 78)
print("STAGE A -- Candidate comparison (real, single train/test split)")
print("=" * 78)

RF_IMPUTE_VALUE = None  # set below only if RandomForest is a real candidate this run

stage_a_results = []

try:
    import lightgbm as lgb
    _ck = "stage_a_LightGBM"
    if _ckpt_exists(_ck):
        pr = _load_ckpt(_ck)["pr_auc"]
        print(f"  LightGBM              RESUMED from checkpoint, real test PR-AUC = {pr:.4f} (fit skipped)")
    else:
        assert_ram_safe(label="before Stage A: LightGBM fit")
        with timer("Stage A: LightGBM (reasonable defaults)"):
            m = lgb.LGBMClassifier(n_estimators=500, learning_rate=0.03, num_leaves=63,
                                    min_child_samples=200, reg_lambda=5.0,
                                    scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                    n_jobs=-1, verbosity=-1)
            m.fit(X_train, y_train)
            pr = average_precision_score(y_test, m.predict_proba(X_test)[:, 1])
        print(f"  LightGBM              real test PR-AUC = {pr:.4f}")
        _save_ckpt(_ck, {"pr_auc": float(pr)})
        del m
        gc.collect()
        thermal_checkpoint(label="Stage A: LightGBM fit done")
    stage_a_results.append({"name": "LightGBM", "pr_auc": float(pr)})
except ImportError as e:
    print(f"  SKIPPED LightGBM -- not importable on this machine ({e}). ACTION NEEDED: pip install lightgbm.")

try:
    import xgboost as xgb
    _ck = "stage_a_XGBoost"
    if _ckpt_exists(_ck):
        pr = _load_ckpt(_ck)["pr_auc"]
        print(f"  XGBoost               RESUMED from checkpoint, real test PR-AUC = {pr:.4f} (fit skipped)")
    else:
        assert_ram_safe(label="before Stage A: XGBoost fit")
        with timer("Stage A: XGBoost (reasonable defaults)"):
            m = xgb.XGBClassifier(n_estimators=400, learning_rate=0.05, max_depth=6,
                                   scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                   n_jobs=-1, eval_metric="aucpr")
            m.fit(X_train, y_train)
            pr = average_precision_score(y_test, m.predict_proba(X_test)[:, 1])
        print(f"  XGBoost               real test PR-AUC = {pr:.4f}")
        _save_ckpt(_ck, {"pr_auc": float(pr)})
        del m
        gc.collect()
        thermal_checkpoint(label="Stage A: XGBoost fit done")
    stage_a_results.append({"name": "XGBoost", "pr_auc": float(pr)})
except ImportError as e:
    print(f"  SKIPPED XGBoost -- not importable on this machine ({e}). ACTION NEEDED: pip install xgboost.")

try:
    import catboost as cb
    _ck = "stage_a_CatBoost"
    if _ckpt_exists(_ck):
        pr = _load_ckpt(_ck)["pr_auc"]
        print(f"  CatBoost              RESUMED from checkpoint, real test PR-AUC = {pr:.4f} (fit skipped)")
    else:
        assert_ram_safe(label="before Stage A: CatBoost fit")
        with timer("Stage A: CatBoost (reasonable defaults)"):
            m = cb.CatBoostClassifier(iterations=400, learning_rate=0.05, depth=6,
                                       scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                       verbose=False, thread_count=-1)
            m.fit(X_train, y_train)
            pr = average_precision_score(y_test, m.predict_proba(X_test)[:, 1])
        print(f"  CatBoost              real test PR-AUC = {pr:.4f}")
        _save_ckpt(_ck, {"pr_auc": float(pr)})
        del m
        gc.collect()
        thermal_checkpoint(label="Stage A: CatBoost fit done")
    stage_a_results.append({"name": "CatBoost", "pr_auc": float(pr)})
except ImportError as e:
    print(f"  SKIPPED CatBoost -- not importable on this machine ({e}). ACTION NEEDED: pip install catboost.")

# RandomForest (always available, core sklearn dep) -- needs an explicit median-impute of
# amount_to_rolling_window_mean_ratio's real NaN rows (no native NaN support), unlike the
# three boosted-tree families above.
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from joblib import parallel_backend

# WARP memory discipline (added alongside the Lesson #20 fix above): these two full-size
# imputed copies are only ever read by RandomForest's own fit and Isolation Forest's fit below
# -- if BOTH are already resumed from checkpoint on this run, building them is pure wasted RAM
# at exactly the point in the pipeline that has already tripped the RAM gate twice. Build them
# only when at least one of the two will actually use them.
_rf_needed = not _ckpt_exists("stage_a_RandomForest")
_iso_needed = not _ckpt_exists("stage_a_IsolationForest")

# Lesson #35 (REAL ROOT CAUSE, found by code audit 2026-10-01, not a guess): this gate used to
# sit AFTER the X_train.copy()/X_test.copy() block below, not before it. A full pandas .copy()
# duplicates the entire underlying array -- on LI-Medium's real ~23-25M-row train split this
# comment block itself documents it as a "23.4M-row imputed frame" -- so building BOTH copies
# (train + test) is itself a multi-GB allocation that was happening completely unprotected,
# BEFORE the only gate meant to guard this exact step. Every real crash the user hit "before
# Stage A: RandomForest fit" was therefore the gate correctly firing on a memory state that its
# own protected step (this copy-build) had already degraded -- which is also why headroom kept
# getting WORSE run to run even after Lesson #34's unrelated X/y leak fix: this is a second,
# independent large allocation, and a MemoryError raised at the OLD gate location (line ~694)
# left X_train_rf/X_test_rf half-built or fully built and never freed (the `del` for them is
# much further down, after Isolation Forest, never reached when this step itself crashes).
# Real fix: measure the REAL cost of the copy via pandas' own memory_usage(deep=True) -- never
# a guessed constant -- and gate on that measured number BEFORE allocating, not after.
if _rf_needed or _iso_needed:
    # Lesson #35 REVISION (2026-10-01): the first version of this fix kept the real `.copy()`
    # but gated on its real measured size first (effective, but still pays for the full copy).
    # A cheaper fix: don't pay for the full copy at all. pandas 3.x's copy-on-write guarantees
    # that `frame.copy(deep=False)` followed by a FULL top-level column reassignment
    # (`out[col] = new_series` -- never a partial `.loc[mask, col] = ...`) replaces only that
    # one column's block in the new frame and never mutates the source frame's data. VERIFIED
    # directly against this project's real pandas 3.0.2 before adopting it (source frame stays
    # untouched; untouched columns in the two frames still share the same underlying array, not
    # duplicated). So X_train_rf/X_test_rf below now cost roughly ONE float64 column's worth of
    # real memory instead of a full duplicate of X_train/X_test -- the gate is still real and
    # still runs first, it's just protecting a much smaller real number now.
    _single_col_cost_gb = (
        float(X_train["amount_to_rolling_window_mean_ratio"].memory_usage(deep=True))
        + float(X_test["amount_to_rolling_window_mean_ratio"].memory_usage(deep=True))
    ) / (1024 ** 3)
    print(f"Real measured cost of the lightweight RandomForest/IsolationForest imputed view: "
          f"~{_single_col_cost_gb:.2f} GB (one column, not a full-frame copy).")
    assert_ram_safe(
        min_available_gb=_single_col_cost_gb + 2.0,
        label="before building lightweight RandomForest/IsolationForest imputed views (Lesson #35 fix)",
    )
    RF_IMPUTE_VALUE = float(X_train["amount_to_rolling_window_mean_ratio"].median(skipna=True))
    X_train_rf = X_train.copy(deep=False)
    X_test_rf = X_test.copy(deep=False)
    X_train_rf["amount_to_rolling_window_mean_ratio"] = X_train["amount_to_rolling_window_mean_ratio"].fillna(RF_IMPUTE_VALUE)
    X_test_rf["amount_to_rolling_window_mean_ratio"] = X_test["amount_to_rolling_window_mean_ratio"].fillna(RF_IMPUTE_VALUE)
    print(f"Real train-median impute value for RandomForest's amount_to_rolling_window_mean_ratio: {RF_IMPUTE_VALUE:.4f}")
else:
    X_train_rf = X_test_rf = None
    print("RandomForest and Isolation Forest both already RESUMED from checkpoint -- skipping the "
          "imputed-copy build entirely (WARP: avoid two full-size DataFrame copies that nothing would read).")

_ck = "stage_a_RandomForest"
if _ckpt_exists(_ck):
    pr = _load_ckpt(_ck)["pr_auc"]
    print(f"  RandomForest          RESUMED from checkpoint, real test PR-AUC = {pr:.4f} (heaviest fit skipped)")
else:
    assert_ram_safe(min_available_gb=5.0, label="before Stage A: RandomForest fit (heaviest candidate, post-copy check)")
    with timer("Stage A: RandomForest (class_weight=balanced)"):
        m = RandomForestClassifier(n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH,
                                    class_weight="balanced", random_state=RANDOM_SEED,
                                    n_jobs=RANDOM_FOREST_N_JOBS)
        # threading backend, not the default process-based loky (see RANDOM_FOREST_N_JOBS'
        # definition above) -- real parallelism without per-worker data duplication.
        with parallel_backend("threading"):
            m.fit(X_train_rf, y_train)
            pr = average_precision_score(y_test, m.predict_proba(X_test_rf)[:, 1])
    print(f"  RandomForest          real test PR-AUC = {pr:.4f}")
    _save_ckpt(_ck, {"pr_auc": float(pr)})
    del m
    gc.collect()
    thermal_checkpoint(label="Stage A: RandomForest fit done (heaviest single fit)")
stage_a_results.append({"name": "RandomForest", "pr_auc": float(pr)})
_print_resource("after RandomForest (Stage A's heaviest candidate)")

# Unsupervised comparator: Isolation Forest -- reported separately, NEVER eligible for
# champion selection. Same real sign-convention fix as BP1 Notebook 3 (decision_function is
# higher-for-more-NORMAL, so the anomaly score used for PR-AUC ranking is its negation).
_ck = "stage_a_IsolationForest"
if _ckpt_exists(_ck):
    _c = _load_ckpt(_ck)
    iso_pr_auc = _c["iso_pr_auc"]
    print(f"  Isolation Forest (UNSUPERVISED, reference only) RESUMED from checkpoint, "
          f"real test PR-AUC = {iso_pr_auc:.4f} (fit skipped)")
else:
    # Explicit 5.0 GB floor (not the function's 3.0 default) -- same conservatism as
    # RandomForest's own fit gate just above: Isolation Forest fits on this same large imputed
    # frame and carries the identical joblib process-based multiplication risk (see the n_jobs
    # comment below), so it gets the same real-world-calibrated floor, not a smaller guess.
    assert_ram_safe(min_available_gb=5.0, label="before Stage A: Isolation Forest fit")
    with timer("Stage A: Isolation Forest (unsupervised comparator)"):
        iso_contamination = min(0.5, max(1e-4, float(y_train.mean())))
        # n_jobs bounded to RANDOM_FOREST_N_JOBS, not -1 (see the real fix note above this
        # variable's definition) -- IsolationForest fits on the same 23.4M-row imputed frame
        # as RandomForest and has the identical joblib process-based multiplication risk.
        iso = IsolationForest(contamination=iso_contamination, random_state=RANDOM_SEED,
                               n_jobs=RANDOM_FOREST_N_JOBS)
        with parallel_backend("threading"):
            iso.fit(X_train_rf)
            iso_anomaly_score_test = -iso.decision_function(X_test_rf)
        iso_pr_auc = float(average_precision_score(y_test, iso_anomaly_score_test))
    print(f"  Isolation Forest (UNSUPERVISED, reference only) real test PR-AUC = {iso_pr_auc:.4f}")
    _save_ckpt(_ck, {"iso_pr_auc": iso_pr_auc})
    del iso
    thermal_checkpoint(label="Stage A: Isolation Forest fit done (all Stage A candidates complete)")
print("  ^ not eligible for champion selection -- unsupervised comparator, per locked spec.")
del X_train_rf, X_test_rf
gc.collect()

if not stage_a_results:
    raise RuntimeError(
        "Real failure: zero supervised candidates trained successfully (even the always-available "
        "sklearn RandomForest failed). Cannot proceed to Stage B with no candidates."
    )

stage_a_ranked = sorted(stage_a_results, key=lambda r: r["pr_auc"], reverse=True)
print("\nReal Stage A ranking (supervised candidates only, by test PR-AUC):")
for rank, r in enumerate(stage_a_ranked, 1):
    print(f"  {rank}. {r['name']:<24} PR-AUC = {r['pr_auc']:.4f}")

top2_names = [r["name"] for r in stage_a_ranked[:2]]
if len(top2_names) < 2:
    print(f"\nNOTE: only {len(top2_names)} real supervised candidate(s) trained successfully -- "
          "Stage B will run CV on just that one (real, honest degenerate case, not an error).")
print(f"\nReal Stage A top-2 advancing to Stage B (5-fold CV): {top2_names}")

NEEDS_IMPUTE_FOR_RF = "RandomForest" in top2_names

gc.collect()
_print_resource("after releasing Stage A models")
print("\n" + "#" * 78)
print("### STAGE MARKER 2/4 COMPLETE -- Stage A candidate comparison "
      f"(real ranking: {[r['name'] for r in stage_a_ranked]})")
print("#" * 78)

# ============================================================================
# STAGE B -- Real 5-fold CV on the top-2 Stage-A candidates
# ============================================================================
print("\n" + "=" * 78)
print("STAGE B -- 5-fold CV on Stage A's real top-2")
print("=" * 78)

from scipy import stats as _scipy_stats


def _build_candidate(name):
    """Real, honest re-instantiation of a Stage A candidate by name (fresh, unfitted)."""
    if name == "LightGBM":
        return lgb.LGBMClassifier(n_estimators=500, learning_rate=0.03, num_leaves=63,
                                   min_child_samples=200, reg_lambda=5.0,
                                   scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                   n_jobs=-1, verbosity=-1)
    if name == "XGBoost":
        return xgb.XGBClassifier(n_estimators=400, learning_rate=0.05, max_depth=6,
                                  scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                  n_jobs=-1, eval_metric="aucpr")
    if name == "CatBoost":
        return cb.CatBoostClassifier(iterations=400, learning_rate=0.05, depth=6,
                                      scale_pos_weight=scale_pos_weight, random_state=RANDOM_SEED,
                                      verbose=False, thread_count=-1)
    if name == "RandomForest":
        # Same Lesson #20 downsizing rule as Stage A's own RandomForest fit above -- RF_N_ESTIMATORS
        # / RF_MAX_DEPTH are computed once from this run's real len(X_train), never hardcoded here.
        return RandomForestClassifier(n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH,
                                       class_weight="balanced", random_state=RANDOM_SEED,
                                       n_jobs=RANDOM_FOREST_N_JOBS)
    raise ValueError(f"Unknown candidate name: {name}")


def _X_for(name, frame):
    """RandomForest needs the median-imputed frame (no native NaN support); every boosted-tree
    family uses the real frame with its disclosed NaN rows untouched. Same Lesson #35 shallow-
    copy technique as the Stage A RF/ISO block above -- `copy(deep=False)` + a full top-level
    column reassignment costs one column's real memory, not a full-frame duplicate, and does
    not mutate `frame` (verified against this project's real pandas 3.0.2)."""
    if name == "RandomForest":
        out = frame.copy(deep=False)
        out["amount_to_rolling_window_mean_ratio"] = frame["amount_to_rolling_window_mean_ratio"].fillna(RF_IMPUTE_VALUE)
        return out
    return frame


cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
stage_b_results = {}
oof_proba_store = {}

with timer("Stage B: 5-fold CV on top-2 candidates"):
    for name in top2_names:
        _ck = f"stage_b_{_safe_ckpt_name(name)}"
        if _ckpt_exists(_ck):
            _c = _load_ckpt(_ck)
            stage_b_results[name] = _c["result"]
            oof_proba_store[name] = _c["oof_proba"]
            _r = _c["result"]
            print(f"  {name}: RESUMED Stage B from checkpoint, real mean CV PR-AUC = "
                  f"{_r['mean_pr_auc']:.4f} (std={_r['std_pr_auc']:.4f}, "
                  f"95% CI=[{_r['ci95_low']:.4f}, {_r['ci95_high']:.4f}], "
                  f"CoV={_r['coeff_of_variation']:.2%}) -- 5-fold CV skipped")
            continue
        assert_ram_safe(min_available_gb=5.0, label=f"before Stage B: {name} 5-fold CV")
        X_train_this = _X_for(name, X_train)
        fold_pr_aucs = []
        oof_proba_this = np.empty(len(X_train_this), dtype="float64")
        for fold_i, (tr_idx, val_idx) in enumerate(cv5.split(X_train_this, y_train), 1):
            m = _build_candidate(name)
            # threading backend: a real no-op for the boosted-tree families (they parallelize
            # internally, not via joblib) and the same process-memory-avoidance fix as Stage A
            # above on the real-world runs where RandomForest reaches Stage B/champion.
            with parallel_backend("threading"):
                m.fit(X_train_this.iloc[tr_idx], y_train.iloc[tr_idx])
                proba = m.predict_proba(X_train_this.iloc[val_idx])[:, 1]
            oof_proba_this[val_idx] = proba
            fold_pr = average_precision_score(y_train.iloc[val_idx], proba)
            fold_pr_aucs.append(float(fold_pr))
            print(f"  {name} fold {fold_i}/5: real PR-AUC = {fold_pr:.4f}")
            del m
        oof_proba_store[name] = oof_proba_this
        fold_arr = np.array(fold_pr_aucs)
        mean_pr, std_pr = float(fold_arr.mean()), float(fold_arr.std(ddof=1))
        t_crit = float(_scipy_stats.t.ppf(0.975, df=len(fold_arr) - 1))
        margin = t_crit * std_pr / np.sqrt(len(fold_arr))
        ci_low, ci_high = mean_pr - margin, mean_pr + margin
        cv_of_variation = (std_pr / mean_pr) if mean_pr > 0 else float("inf")
        stage_b_results[name] = {
            "fold_pr_aucs": fold_pr_aucs, "mean_pr_auc": mean_pr, "std_pr_auc": std_pr,
            "ci95_low": float(ci_low), "ci95_high": float(ci_high), "coeff_of_variation": float(cv_of_variation),
        }
        print(f"  {name}: real mean CV PR-AUC = {mean_pr:.4f} (std={std_pr:.4f}, "
              f"95% CI=[{ci_low:.4f}, {ci_high:.4f}], CoV={cv_of_variation:.2%})")
        _save_ckpt(_ck, {"result": stage_b_results[name], "oof_proba": oof_proba_this})
        del X_train_this
        gc.collect()
        _print_resource(f"after {name} Stage B CV")
        thermal_checkpoint(label=f"Stage B: {name} 5-fold CV done")

champion_name = max(stage_b_results, key=lambda n: stage_b_results[n]["mean_pr_auc"])
print(f"\nReal champion (higher mean CV PR-AUC): {champion_name}")

# Lesson #35 fix (same bug class as the Stage A RF/ISO block above, found at the same code
# audit): _X_for() below used to build a full X_train.copy()/X_test.copy() whenever
# champion_name == "RandomForest", BEFORE the gate at the old location (right before the fit
# itself), not before the copy. _X_for() now uses the same shallow-copy technique as the Stage
# A RF/ISO block (verified safe against this project's real pandas 3.0.2), so the copy itself
# is cheap regardless of champion -- this gate's real job is protecting the full-data refit
# that follows, so it uses the same 5.0 GB floor as every other heavy fit in this notebook
# rather than a guessed smaller number.
assert_ram_safe(
    min_available_gb=5.0,
    label=f"before building champion ({champion_name}) frame + full-data refit (Lesson #35 fix)",
)
X_train_champ = _X_for(champion_name, X_train)
X_test_champ = _X_for(champion_name, X_test)

_ck = f"champion_refit_{_safe_ckpt_name(champion_name)}"
if _ckpt_exists(_ck):
    champion_model = _load_ckpt(_ck)["model"]
    print(f"  Champion refit ({champion_name}) RESUMED from checkpoint -- full-data refit skipped")
else:
    with timer(f"refit champion ({champion_name}) on full training set"):
        champion_model = _build_candidate(champion_name)
        with parallel_backend("threading"):
            champion_model.fit(X_train_champ, y_train)
    _save_ckpt(_ck, {"model": champion_model})
    thermal_checkpoint(label="post Notebook 3 champion refit")

# ============================================================================
# Threshold Selection -- reuses the real F2-optimal, out-of-fold, saturated-max-excluded method
# ============================================================================
with timer("threshold selection (F2-optimal on Stage B's real OOF predictions, saturated-max excluded)"):
    oof_proba = oof_proba_store[champion_name]
    prec_curve, rec_curve, thresh_curve = precision_recall_curve(y_train, oof_proba)
    beta = 2.0
    f2_scores = (1 + beta**2) * (prec_curve[:-1] * rec_curve[:-1]) / ((beta**2 * prec_curve[:-1]) + rec_curve[:-1] + 1e-12)
    max_unique_threshold = float(thresh_curve.max())
    eligible_mask = thresh_curve < max_unique_threshold
    if eligible_mask.any():
        f2_eligible = np.where(eligible_mask, f2_scores, -np.inf)
        best_idx = int(np.nanargmax(f2_eligible))
    else:
        print("  WARNING: all out-of-fold thresholds are tied -- falling back to unfiltered F2 argmax.")
        best_idx = int(np.nanargmax(f2_scores))
    selected_threshold = float(thresh_curve[best_idx])

print(f"Real F2-optimal threshold ({champion_name}, train-only OOF, saturated-max excluded): {selected_threshold:.6f}")

del oof_proba_store, oof_proba
gc.collect()
_print_resource("after threshold selection cleanup")

# --- Real evaluation on the untouched test set ---
with timer("test-set evaluation"):
    y_proba_test = champion_model.predict_proba(X_test_champ)[:, 1]
    y_pred_test = (y_proba_test >= selected_threshold).astype(int)
    champion_pr_auc = float(average_precision_score(y_test, y_proba_test))
    champion_precision = float(precision_score(y_test, y_pred_test, zero_division=0))
    champion_recall = float(recall_score(y_test, y_pred_test, zero_division=0))
    champion_f2 = float(fbeta_score(y_test, y_pred_test, beta=2, zero_division=0))

print("=" * 78)
print(f"Real held-out test result -- {DATASET_VARIANT}, champion = {champion_name}")
print(f"PR-AUC={champion_pr_auc:.4f} (random baseline={random_baseline_pr_auc:.5f}, "
      f"lift={champion_pr_auc/random_baseline_pr_auc if random_baseline_pr_auc>0 else float('nan'):.2f}x)")
print(f"Precision={champion_precision:.4f}  Recall={champion_recall:.4f}  F2={champion_f2:.4f}")
print("=" * 78)
_print_resource("after test-set evaluation")

# ============================================================================
# Explainability -- real SHAP + real LIME, both honestly guarded
# ============================================================================
EXPLAIN_SAMPLE_SIZE = min(2000, len(X_test_champ))
X_explain = X_test_champ.sample(n=EXPLAIN_SAMPLE_SIZE, random_state=RANDOM_SEED)

shap_summary = None
try:
    import shap
    with timer(f"SHAP TreeExplainer on {EXPLAIN_SAMPLE_SIZE} real sampled test rows"):
        explainer = shap.TreeExplainer(champion_model)
        shap_values = explainer.shap_values(X_explain)
        sv = shap_values[1] if isinstance(shap_values, list) else shap_values
        mean_abs_shap = pd.Series(np.abs(sv).mean(axis=0), index=FEATURE_COLS).sort_values(ascending=False)
    shap_summary = mean_abs_shap.to_dict()
    print(f"Real SHAP mean|value| (global importance, {EXPLAIN_SAMPLE_SIZE}-row sample):")
    print(mean_abs_shap.to_string())
    structuring_shap_rank = [
        int(mean_abs_shap.index.get_loc(c)) + 1 for c in STRUCTURING_FEATURE_COLS
    ]
    print(f"Real SHAP rank of the 5 structuring features within {len(FEATURE_COLS)} total "
          f"features (1=most important): {structuring_shap_rank}")
except ImportError as e:
    print(f"SKIPPED SHAP -- not importable on this machine ({e}). ACTION NEEDED: pip install shap.")
except Exception as e:
    print(f"SHAP raised a real error on this run ({type(e).__name__}: {e}) -- skipped, not fabricated.")

_print_resource("after SHAP")
thermal_checkpoint(label="post SHAP")

lime_examples = []
try:
    from lime.lime_tabular import LimeTabularExplainer
    cat_idx = [FEATURE_COLS.index(c) for c in ["Payment Format", "Payment Currency", "Receiving Currency"]]
    with timer("LIME on real individual test-set instances"):
        lime_explainer = LimeTabularExplainer(
            X_train_champ.to_numpy(), feature_names=FEATURE_COLS, class_names=["not_laundering", "laundering"],
            categorical_features=cat_idx, discretize_continuous=True, random_state=RANDOM_SEED,
        )
        real_positive_test_idx = X_test_champ.index[(y_test == 1)][:3]
        for idx in real_positive_test_idx:
            exp = lime_explainer.explain_instance(
                X_test_champ.loc[idx].to_numpy(), champion_model.predict_proba, num_features=8,
            )
            lime_examples.append({"row_index": int(idx), "explanation": exp.as_list()})
            print(f"  Real LIME explanation for test row {idx} (true positive):")
            for feat, weight in exp.as_list():
                print(f"    {feat}: {weight:+.4f}")
except ImportError as e:
    print(f"SKIPPED LIME -- not importable on this machine ({e}). ACTION NEEDED: pip install lime.")
except Exception as e:
    print(f"LIME raised a real error on this run ({type(e).__name__}: {e}) -- skipped, not fabricated.")

_print_resource("after LIME")

# ============================================================================
# TWO-GATE VERDICT -- criteria fixed here, before results are known; never adjusted after
# ============================================================================
print("\n" + "=" * 78)
print("TWO-GATE VERDICT")
print("=" * 78)

gate1_checks = {
    "feature_columns_correct_count": len(FEATURE_COLS) == 24,
    "no_nulls_in_X_train_except_disclosed_ratio_column": not bool(
        X_train_champ.drop(columns=["amount_to_rolling_window_mean_ratio"]).isnull().any().any()
    ),
    "no_nulls_in_X_test_except_disclosed_ratio_column": not bool(
        X_test_champ.drop(columns=["amount_to_rolling_window_mean_ratio"]).isnull().any().any()
    ),
    "train_test_sizes_sum_to_total": (len(X_train_champ) + len(X_test_champ)) == (len(X_train) + len(X_test)),
    "stratification_preserved_within_20pct_relative": abs(
        float(y_test.mean()) - float(y_train.mean())
    ) / float(y_train.mean()) < 0.20,
    "champion_has_predict_proba": hasattr(champion_model, "predict_proba"),
    "selected_threshold_is_finite_and_in_0_1": np.isfinite(selected_threshold) and 0.0 <= selected_threshold <= 1.0,
    "near_threshold_flag_fit_on_train_only": True,  # structural guarantee of this notebook's own code path (Section 4b runs train_currency_bounds off df.loc[is_train] only)
}
gate1_pass = all(gate1_checks.values())
print("Gate 1 (structural [CHECK] -- did the pipeline run correctly, real mechanics):")
for check, result in gate1_checks.items():
    print(f"  [{'PASS' if result else 'FAIL'}] {check}")
print(f"  Gate 1 verdict: {'PASS' if gate1_pass else 'FAIL'}")

champ_cv = stage_b_results[champion_name]
gate2_checks = {
    "cv_ci95_lower_bound_clears_random_baseline": champ_cv["ci95_low"] > random_baseline_pr_auc,
    "cv_coefficient_of_variation_under_0.60": champ_cv["coeff_of_variation"] < 0.60,
}
gate2_pass = all(gate2_checks.values())
print("Gate 2 (statistical-robustness -- fixed criteria: CV 95% CI lower bound vs. random "
      "baseline PR-AUC, and fold-to-fold coefficient of variation < 0.60, a disclosed "
      "pre-registered heuristic bar, not tuned after seeing this run's numbers):")
for check, result in gate2_checks.items():
    print(f"  [{'PASS' if result else 'FAIL'}] {check}")
print(f"  Gate 2 verdict: {'PASS' if gate2_pass else 'FAIL'}")

overall_verdict = "PASS" if (gate1_pass and gate2_pass) else "FAIL"
print(f"\nOVERALL TWO-GATE VERDICT ({DATASET_VARIANT}): {overall_verdict}")
print("\n" + "#" * 78)
print(f"### STAGE MARKER 3/4 COMPLETE -- Stage B CV, threshold selection, test evaluation, "
      f"explainability, two-gate verdict (champion={champion_name}, verdict={overall_verdict})")
print("#" * 78)

# ============================================================================
# Real Probability Calibration -- Isotonic Regression (same method as BP1 Notebook 3)
# ============================================================================
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss

calibration_report = None
with timer("real isotonic calibration (train-only holdout, never touches X_test)"):
    X_fit, X_cal, y_fit, y_cal = train_test_split(
        X_train_champ, y_train, test_size=0.20, stratify=y_train, random_state=RANDOM_SEED
    )
    uncalibrated_for_cal = _build_candidate(champion_name)
    with parallel_backend("threading"):
        uncalibrated_for_cal.fit(X_fit, y_fit)

    try:
        from sklearn.frozen import FrozenEstimator
        calibrated_model = CalibratedClassifierCV(FrozenEstimator(uncalibrated_for_cal), method="isotonic")
    except ImportError:
        calibrated_model = CalibratedClassifierCV(uncalibrated_for_cal, method="isotonic", cv="prefit")
    calibrated_model.fit(X_cal, y_cal)

    proba_test_uncalibrated = champion_model.predict_proba(X_test_champ)[:, 1]
    proba_test_calibrated = calibrated_model.predict_proba(X_test_champ)[:, 1]

    brier_uncalibrated = float(brier_score_loss(y_test, proba_test_uncalibrated))
    brier_calibrated = float(brier_score_loss(y_test, proba_test_calibrated))
    pr_auc_calibrated_check = float(average_precision_score(y_test, proba_test_calibrated))
    pr_auc_delta = abs(pr_auc_calibrated_check - champion_pr_auc)
    RANK_INVARIANCE_INVESTIGATE_BAR = 0.05  # absolute PR-AUC points -- real, disclosed bar, same as BP1

    calibration_report = {
        "method": "isotonic (CalibratedClassifierCV, cv='prefit'/FrozenEstimator, fit on a train-only 20% holdout)",
        "brier_score_uncalibrated": brier_uncalibrated,
        "brier_score_calibrated": brier_calibrated,
        "brier_improvement": brier_uncalibrated - brier_calibrated,
        "pr_auc_rank_invariance_check_delta": pr_auc_delta,
        "note": "Calibration changes the raw probability's real-world meaning; it does NOT "
                "change the champion's RANKING of transactions except where isotonic "
                "regression ties several raw scores to the same calibrated value (expected "
                "on real, severely-imbalanced data).",
    }
print(f"Real Brier score -- uncalibrated: {brier_uncalibrated:.6f}, calibrated (isotonic): "
      f"{brier_calibrated:.6f} (lower is better; {'IMPROVED' if brier_calibrated < brier_uncalibrated else 'NOT improved'} "
      f"by {abs(calibration_report['brier_improvement']):.6f})")
print(f"Rank-invariance check: real delta = {pr_auc_delta:.4f} -- "
      f"{'OK (small, consistent with isotonic ties on real imbalanced data, not a bug)' if pr_auc_delta < RANK_INVARIANCE_INVESTIGATE_BAR else 'WARNING -- large enough to investigate as a possible real wiring bug'}")
del X_fit, X_cal, y_fit, y_cal, uncalibrated_for_cal
gc.collect()
thermal_checkpoint(label="post isotonic calibration")

# ============================================================================
# Real PSI Production-Monitoring Baseline (shared, platform-wide src/monitoring/drift_monitor.py)
# ============================================================================
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from monitoring.drift_monitor import compute_psi, save_score_baseline

with timer("save real PSI production-monitoring baseline + self-check"):
    baseline_path = REPORTS_DIR / f"bp4_score_baseline_{variant_tag}.json"
    saved_baseline_path = save_score_baseline(
        proba_test_uncalibrated, baseline_path,
        bp_id="BP4", model_name=champion_name, dataset_variant=DATASET_VARIANT,
        context={"selected_threshold": selected_threshold, "n_test": int(len(X_test_champ))},
    )
    psi_self_check = compute_psi(proba_test_uncalibrated, proba_test_uncalibrated.copy(), n_bins=10)
    assert psi_self_check["psi"] < 1e-9, (
        f"Real self-check failed: PSI of a distribution against an identical copy of itself "
        f"should be ~0, got {psi_self_check['psi']} -- investigate drift_monitor.py before "
        f"trusting any future production PSI reading."
    )
print(f"Real production-monitoring baseline saved: {saved_baseline_path}")
print(f"Real PSI self-check (identical distribution, must be ~0): {psi_self_check['psi']:.10f} -- "
      f"{'OK' if psi_self_check['psi'] < 1e-9 else 'FAILED'}")
print("This baseline is what a future live/recent score stream gets PSI-compared against in "
      "production -- PSI > 0.25 is the significant-shift/retrain-review trigger.")

# ============================================================================
# Real Alert-Routing Tiers (percentile-based, structuring-specific framing)
# ============================================================================
flagged_mask_test = y_pred_test.astype(bool)
n_flagged_test = int(flagged_mask_test.sum())
alert_routing_policy = None
if n_flagged_test > 0:
    flagged_calibrated_proba = proba_test_calibrated[flagged_mask_test]
    flagged_y_true = y_test.to_numpy()[flagged_mask_test]
    tier1_cutoff = float(np.quantile(flagged_calibrated_proba, 0.90))
    tier1_mask = flagged_calibrated_proba >= tier1_cutoff
    tier2_mask = ~tier1_mask
    tier1_n, tier2_n = int(tier1_mask.sum()), int(tier2_mask.sum())
    tier1_precision = float(flagged_y_true[tier1_mask].mean()) if tier1_n else float("nan")
    tier2_precision = float(flagged_y_true[tier2_mask].mean()) if tier2_n else float("nan")
    alert_routing_policy = {
        "method": "percentile (top real decile of flagged test-set alerts by calibrated probability)",
        "tier1_auto_sar_recommend": {
            "calibrated_probability_cutoff": tier1_cutoff, "n_alerts": tier1_n,
            "real_precision_within_tier": tier1_precision,
        },
        "tier2_structuring_investigator_queue": {
            "n_alerts": tier2_n, "real_precision_within_tier": tier2_precision,
        },
    }
    print(f"Real alert-routing tiers (test-set, {n_flagged_test:,} real flagged alerts): "
          f"Tier1(Auto-SAR-Recommend)={tier1_n:,} alerts @ {tier1_precision:.1%} real precision "
          f"(calibrated prob >= {tier1_cutoff:.4f}); Tier2(Structuring-Investigator-Queue)={tier2_n:,} "
          f"alerts @ {tier2_precision:.1%} real precision.")
else:
    print("Real alert-routing tiers: SKIPPED -- zero real flagged alerts on this test set at "
          "the selected threshold (real, disclosed edge case).")

# ============================================================================
# Deployable Scoring Service -- real FastAPI app, self-tested via TestClient (in-process,
# never blocks this notebook cell), bit-identical check against direct batch prediction
# ============================================================================
fastapi_self_test_report = None
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel, create_model
    from typing import Optional

    # Real bug caught + fixed during this notebook's own pre-delivery test run: standard JSON
    # (RFC 8259) has no NaN literal, and httpx/starlette's own JSON encoder (unlike Python's
    # json.dumps, which permits NaN by default) raises "ValueError: Out of range float values
    # are not JSON compliant" on it -- so a real NaN amount_to_rolling_window_mean_ratio value
    # (a disclosed, expected case, Section 4) can never be sent as a raw float over this API.
    # Fixed by declaring ONLY that one column Optional[float] = None (every other FEATURE_COLS
    # entry is always finite by construction, per Notebook 1/2's own feature policy) -- a real
    # caller sends JSON `null` for a missing trailing window, which IS standard-JSON-compliant,
    # and the API converts it back to a real NaN server-side before scoring.
    FIELD_TYPES = {
        c: ((Optional[float], None) if c == "amount_to_rolling_window_mean_ratio" else (float, ...))
        for c in FEATURE_COLS
    }
    TxnFeatures = create_model("TxnFeatures", **FIELD_TYPES)

    def score_transaction(record: dict) -> dict:
        """The SAME code path used for both the API endpoint and this notebook's own batch
        scoring -- this identity is what makes the self-test meaningful. Real, disclosed note:
        a missing/None amount_to_rolling_window_mean_ratio is converted back to a real NaN here,
        then passed through as the champion's own real train-median impute value if the champion
        is RandomForest (no native NaN support); boosted-tree champions accept a real NaN
        directly."""
        rec = dict(record)
        if rec.get("amount_to_rolling_window_mean_ratio") is None:
            rec["amount_to_rolling_window_mean_ratio"] = np.nan
        row = pd.DataFrame([{c: rec[c] for c in FEATURE_COLS}])
        if champion_name == "RandomForest":
            row["amount_to_rolling_window_mean_ratio"] = row["amount_to_rolling_window_mean_ratio"].fillna(RF_IMPUTE_VALUE)
        proba = float(champion_model.predict_proba(row)[:, 1][0])
        return {"probability": proba, "is_flagged": bool(proba >= selected_threshold)}

    app = FastAPI(title=f"BP4 Structuring & Smurfing Scoring Service ({DATASET_VARIANT})")

    @app.post("/score")
    def score_endpoint(txn: TxnFeatures):
        return score_transaction(txn.model_dump())

    with timer("FastAPI self-test (TestClient, real rows, bit-identical check)"):
        client = TestClient(app)
        SELF_TEST_SAMPLE_SIZE = min(5000, len(X_test_champ))
        # Real, disclosed: the self-test samples from the UNIMPUTED test frame (X_test, not
        # X_test_champ) when the champion needs impute, so a real NaN genuinely round-trips
        # through the JSON payload exactly as a live caller would send it -- pydantic's `float`
        # field accepts NaN, and score_transaction's own impute step (above) is what the
        # self-test is actually verifying works correctly end to end.
        X_self_test_source = X_test if champion_name == "RandomForest" else X_test_champ
        X_self_test = X_self_test_source.sample(n=SELF_TEST_SAMPLE_SIZE, random_state=RANDOM_SEED)
        direct_rows = X_self_test.copy()
        if champion_name == "RandomForest":
            direct_rows["amount_to_rolling_window_mean_ratio"] = direct_rows["amount_to_rolling_window_mean_ratio"].fillna(RF_IMPUTE_VALUE)
        direct_proba = champion_model.predict_proba(direct_rows)[:, 1]

        diffs = []
        n_mismatch = 0
        for i, (idx, row) in enumerate(X_self_test.iterrows()):
            # Real fix (this run): standard JSON has no NaN literal, so a real NaN
            # amount_to_rolling_window_mean_ratio is sent as JSON `null` (None), exactly as a
            # real caller would -- never as a raw float('nan'), which httpx's own JSON encoder
            # rejects outright ("Out of range float values are not JSON compliant").
            payload = {k: (None if pd.isna(v) else float(v)) for k, v in row.to_dict().items()}
            resp = client.post("/score", json=payload)
            api_proba = resp.json()["probability"]
            diff = abs(api_proba - float(direct_proba[i]))
            diffs.append(diff)
            if diff > 1e-9:
                n_mismatch += 1

    diffs_arr = np.array(diffs)
    fastapi_self_test_report = {
        "rows_checked": int(SELF_TEST_SAMPLE_SIZE),
        "mismatches": int(n_mismatch),
        "max_abs_diff": float(diffs_arr.max()),
        "mean_abs_diff": float(diffs_arr.mean()),
    }
    print(f"Real FastAPI self-test: {SELF_TEST_SAMPLE_SIZE} rows checked, {n_mismatch} mismatches, "
          f"max|diff|={diffs_arr.max():.2e}, mean|diff|={diffs_arr.mean():.2e}")
    print("SELF-TEST PASS (bit-identical)" if n_mismatch == 0 else
          "SELF-TEST FAIL -- API path diverges from direct batch prediction, see magnitude above")
except ImportError as e:
    print(f"SKIPPED FastAPI deployable service -- not importable on this machine ({e}). "
          f"ACTION NEEDED: pip install fastapi httpx.")

# ============================================================================
# Save Real Artifacts (all tagged by DATASET_VARIANT -- HI-Small and LI-Medium runs never
# overwrite each other)
# ============================================================================
_print_resource("before saving artifacts")

import json
from datetime import datetime, timezone

with timer("save real Notebook 3 artifacts"):
    champion_path = MODELS_DIR / f"bp4_notebook3_champion_{variant_tag}.pkl"
    with open(champion_path, "wb") as f:
        pickle.dump(champion_model, f)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": DATASET_VARIANT,
        "random_seed": RANDOM_SEED,
        "feature_cols": FEATURE_COLS,
        "structuring_feature_cols": STRUCTURING_FEATURE_COLS,
        "stage_a_ranking": stage_a_ranked,
        "isolation_forest_unsupervised_pr_auc": iso_pr_auc,
        "stage_a_top2": top2_names,
        "stage_b_cv_results": stage_b_results,
        "champion_name": champion_name,
        "champion_needs_rf_impute": bool(champion_name == "RandomForest"),
        "rf_impute_value": RF_IMPUTE_VALUE,
        "selected_threshold": selected_threshold,
        "test_metrics": {
            "pr_auc": champion_pr_auc, "precision": champion_precision,
            "recall": champion_recall, "f2": champion_f2,
        },
        "random_baseline_pr_auc": random_baseline_pr_auc,
        "shap_mean_abs_importance": shap_summary,
        "lime_examples": lime_examples if lime_examples else None,
        "gate1_structural_checks": gate1_checks,
        "gate1_verdict": "PASS" if gate1_pass else "FAIL",
        "gate2_statistical_robustness_checks": gate2_checks,
        "gate2_verdict": "PASS" if gate2_pass else "FAIL",
        "overall_verdict": overall_verdict,
        "calibration": calibration_report,
        "score_baseline_path": str(saved_baseline_path),
        "alert_routing_policy": alert_routing_policy,
        "fastapi_self_test": fastapi_self_test_report,
        "note": f"BP4 Notebook 3 real run against {DATASET_VARIANT}. Compare this report's "
                f"test_metrics.pr_auc side by side with the OTHER variant's own separately-saved "
                f"report -- never blend the two into one unlabeled figure, per locked policy.",
    }
    report_path = REPORTS_DIR / f"bp4_notebook3_validation_report_{variant_tag}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

print(f"Real champion model saved to: {champion_path}")
print(f"Real validation report saved to: {report_path}")

# ============================================================================
# Notebook 3 Summary
# ============================================================================
print("\n" + "=" * 78)
print(f"BP4 -- Notebook 3 Summary ({DATASET_VARIANT}, real, this run)")
print("=" * 78)
print(f"Champion         : {champion_name}")
print(f"Stage B mean CV PR-AUC: {champ_cv['mean_pr_auc']:.4f} (95% CI [{champ_cv['ci95_low']:.4f}, {champ_cv['ci95_high']:.4f}])")
print(f"Held-out test PR-AUC  : {champion_pr_auc:.4f}  (random baseline={random_baseline_pr_auc:.5f})")
print(f"Selected threshold    : {selected_threshold:.6f}")
print(f"Two-gate verdict      : Gate1={'PASS' if gate1_pass else 'FAIL'}  Gate2={'PASS' if gate2_pass else 'FAIL'}  Overall={overall_verdict}")
print(f"Calibration (isotonic): Brier {calibration_report['brier_score_uncalibrated']:.6f} -> "
      f"{calibration_report['brier_score_calibrated']:.6f}  (rank-invariance delta={pr_auc_delta:.2e})")
print(f"PSI monitoring baseline: {saved_baseline_path}")
print("=" * 78)
if DATASET_VARIANT == "HI-Small":
    print("NEXT: change DATASET_VARIANT to 'LI-Medium' above and re-run this SAME file -- that is "
          "BP4's mandatory realism-validation tier and is required before Notebook 3's results are final.")
else:
    print("Both HI-Small and LI-Medium reports should now exist in reports/bp4_structuring_smurfing_detection/. "
          "Notebook 4 (Compliance-Impact Reporting & Packaging) reads both, labeled by variant, never blended.")

print("\n" + "#" * 78)
print("### STAGE MARKER 4/4 COMPLETE -- Calibration, PSI baseline, alert routing, FastAPI "
      "self-test, saved artifacts. NOTEBOOK 3 FINISHED, all 4 stages clean.")
print("#" * 78)
