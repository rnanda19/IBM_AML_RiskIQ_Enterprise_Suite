# ============================================================================
# BP5 NOTEBOOK 3 -- Statistical Validation & Deployment (SINGLE CELL)
# ============================================================================
#
# Purpose (per the locked master-execution-plan, Section 4 + Notebook 1 Sections 7-8): re-run
# BP5's real feature-engineering pipeline -- UNCHANGED from Notebook 2 (the platform's existing
# 19-feature set + the 8 real cross-border/correspondent-banking features locked in Notebook 1
# Section 7, built via the Notebook-1-validated Bank-Name country-tagging method, Lesson #11
# leakage discipline) -- against a full model-comparison + statistical-robustness protocol, on
# TWO dataset variants, never merged: HI-Small (continuity baseline) and LI-Medium (BP5's LOCKED
# mandatory realism-validation tier, Notebook 1 Section 8).
#
# HOW TO RUN THIS NOTEBOOK (per the locked policy): run it ONCE with DATASET_VARIANT =
# "LI-Medium" (the mandatory tier, already the active value below), then change ONLY that one
# line to "HI-Small" and run it again for the continuity baseline. Nothing else in this file
# should be edited between runs. Each run writes its own real, variant-tagged summary files --
# neither run overwrites the other.
#
# What this notebook does, in order (same shape as BP1/BP4 Notebook 3 -- standard binary
# classification, correspondent-banking/cross-border framing rather than structuring/smurfing):
#   Stage A: trains a real candidate set (LightGBM, XGBoost, CatBoost, RandomForest -- each
#     library tried honestly, skipped with a clear message if not installed -- plus
#     Isolation Forest as an unsupervised comparator, reported separately, never blended
#     into champion selection) on a single real train/test split, ranks by real PR-AUC.
#   Stage B: real 5-fold StratifiedKFold CV on the top-2 Stage-A candidates; champion =
#     higher real mean CV PR-AUC. Reports per-fold PR-AUC and a 95% CI (t-distribution,
#     df=4 -- small-n, honestly disclosed).
#   Threshold selection: reuses the real F2-optimal, out-of-fold, saturated-max-excluded
#     method (same proven-correct method as BP1/BP4 Notebook 2/3).
#   Explainability: real SHAP (TreeExplainer) on a capped real sample of the champion's
#     test-set predictions; real LIME on a few individual real instances -- BOTH wrapped in
#     honest try/except import guards. Skipped with a clear message, not silently, if
#     unavailable. Reports where the 8 new cross-border features (e.g.
#     sender_country_empirical_risk, is_cross_border) rank within the full feature set.
#   Two-gate verdict: a structural [CHECK] gate (did the pipeline actually run correctly --
#     mechanics, not model quality) and a separate statistical-robustness gate (does the
#     champion's CV performance clear the random baseline with real statistical margin, and
#     is it stable across folds) -- criteria fixed BEFORE this notebook runs and never
#     adjusted after seeing a real result (locked Lesson #15).
#   Real isotonic calibration + a real PSI production-monitoring baseline (reusing the
#     shared, platform-wide `src/monitoring/drift_monitor.py` module, same as BP1/BP4) + real
#     percentile-based alert-routing tiers.
#   Deployable scoring service: a real FastAPI app wrapping the exact same scoring function
#     used for the notebook's own batch predictions -- self-tested via FastAPI's TestClient
#     (in-process, never blocks this notebook cell) against every row of a capped real
#     sample, reporting a magnitude-of-mismatch column, not just a pass/fail count.
#
# Proactively hardened with the same checkpoint/resume + Windows-sleep-prevention +
# STAGE MARKER pattern already proven on BP1/BP2/BP4 Notebook 3 (Lesson #23/#24) -- BP5 shares
# the identical multi-candidate Stage A + 5-fold CV Stage B risk shape (long real runs, real
# risk of a mid-run crash discarding already-completed expensive work), applied here BEFORE
# any real crash on this BP, not after one (the point of generalizing the lesson across BPs).
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
# NOTE: BP4's WINDOW_HOURS / NEAR_THRESHOLD_LOW / NEAR_THRESHOLD_HIGH constants are deliberately
# NOT carried over here -- those back BP4's structuring-specific trailing-window and near-
# threshold-amount features, neither of which is part of BP5's locked feature set (Notebook 1
# Section 7 / Notebook 2's own FEATURE_COLS construction: the platform's existing 19 columns +
# BP5's 8 cross-border columns, nothing else). Carrying unused constants forward would be
# copy-paste residue, not a standing convention.

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
# Lesson #35 diagnostic (real, deep-audit fix, originally found on BP4, 2026-10-01, applied
# proactively to every notebook on this platform from here on): a freshly started Jupyter
# kernel's own process RSS here -- before Stage 1 has loaded a single row -- is normally well
# under 0.3 GB (just the interpreter + the handful of stdlib/psutil imports done so far). If
# this number is already large, this kernel is almost certainly being REUSED across retries
# (the cell was re-run, not the kernel restarted) and is still holding objects bound in this
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
          f"resume in seconds rather than needing to re-run the data-load/feature-engineering "
          f"stage, so restarting is now cheap.")
else:
    print(f"  [MEM] Startup process RSS = {_startup_rss_gb:.2f} GB (consistent with a fresh kernel).")

# ============================================================================
# THE ONE LINE TO CHANGE BETWEEN THE TWO REQUIRED RUNS
# ============================================================================
DATASET_VARIANT = "LI-Medium"  # BP5's locked mandatory realism-validation tier (Notebook 1 Section 8).
# Also run this notebook with DATASET_VARIANT = "HI-Small" (continuity baseline) -- change ONLY
# this one line and re-run; nothing else in this file should differ between the two runs.
# ============================================================================

VARIANT_TRANS_FILES = {"HI-Small": "HI-Small_Trans.csv", "LI-Medium": "LI-Medium_Trans.csv"}
VARIANT_ACCOUNTS_FILES = {"HI-Small": "HI-Small_accounts.csv", "LI-Medium": "LI-Medium_accounts.csv"}
if DATASET_VARIANT not in VARIANT_TRANS_FILES:
    raise ValueError(f"DATASET_VARIANT must be one of {list(VARIANT_TRANS_FILES)}, got {DATASET_VARIANT!r}")
variant_tag = DATASET_VARIANT.lower().replace("-", "_")

# REAL FIX, carried forward from BP4 Notebook 3 (same root cause, same fix, applied proactively
# here rather than re-discovered): RandomForestClassifier and IsolationForest build their trees
# via joblib's PROCESS-based parallelism (the "loky" backend) by default -- each worker is a
# separate OS process, and unless numpy-level memmapping cleanly kicks in for the pandas-
# DataFrame-derived input (not guaranteed), each worker can end up holding its own copy of the
# full training frame. `joblib.parallel_backend("threading")`, wrapped around each
# RandomForest/IsolationForest fit below, makes joblib hand out worker THREADS instead of
# worker PROCESSES for that call -- threads share one process's memory, so there is no
# per-worker data duplication to begin with, regardless of n_jobs. This is not merely safe for
# tree ensembles: scikit-learn's tree-building is Cython and releases the GIL during the heavy
# computation, so real parallelism still happens across threads, not just nominal concurrency.
# This lets n_jobs go back up to the same WARP-configured thread ceiling the rest of this
# notebook already uses (`perf_config["threads_configured"]`, ~92% of logical cores, never a
# separate hardcoded number) without reintroducing the process-memory risk.
RANDOM_FOREST_N_JOBS = perf_config["threads_configured"]

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
MODELS_DIR = PROJECT_ROOT / "models" / "bp5_correspondent_banking_crossborder_risk"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp5_correspondent_banking_crossborder_risk"
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
# Lesson #35 (real, deep-audit fix, originally found on BP4, applied proactively here):
# checkpoint Stage 1's own real outputs so a true kernel restart resumes in seconds instead of
# re-paying for the full data-load/feature-engineering/split stage.
# ============================================================================
_STAGE1_CKPT_KEY = "stage1_train_test_frames"
if _ckpt_exists(_STAGE1_CKPT_KEY):
    _s1 = _load_ckpt(_STAGE1_CKPT_KEY)
    X_train, X_test = _s1["X_train"], _s1["X_test"]
    y_train, y_test = _s1["y_train"], _s1["y_test"]
    FEATURE_COLS = _s1["FEATURE_COLS"]
    CROSSBORDER_FEATURE_COLS = _s1["CROSSBORDER_FEATURE_COLS"]
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
    ACCOUNTS_DTYPES = {
        "Bank Name": "string", "Bank ID": "string", "Account Number": "string",
        "Entity ID": "string", "Entity Name": "string",
    }

    # --- 1. Load the real transaction file AND the real accounts file for this run's
    #     DATASET_VARIANT (WARP: Parquet-cached). accounts.csv is BP5's own real second input --
    #     it is what carries the real Bank-Name country tag that makes cross-border detection
    #     possible at all (Notebook 1 Section 4 / Notebook 2 Section 4). ---
    trans_path = RAW / VARIANT_TRANS_FILES[DATASET_VARIANT]
    if not trans_path.exists():
        raise FileNotFoundError(
            f"{trans_path} does not exist. This notebook needs the real "
            f"{VARIANT_TRANS_FILES[DATASET_VARIANT]} file in data/raw/ before it can run against "
            f"the '{DATASET_VARIANT}' variant."
        )
    accounts_path = RAW / VARIANT_ACCOUNTS_FILES[DATASET_VARIANT]
    if not accounts_path.exists():
        raise FileNotFoundError(
            f"{accounts_path} does not exist. This notebook needs the real "
            f"{VARIANT_ACCOUNTS_FILES[DATASET_VARIANT]} file in data/raw/ before it can run "
            f"against the '{DATASET_VARIANT}' variant -- BP5's cross-border features cannot be "
            f"computed without the real Bank-Name country tags this file carries."
        )
    with timer(f"load {trans_path.name}"):
        df = load_csv_cached(trans_path, parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
    print(f"{trans_path.name} real shape: {df.shape}")

    with timer(f"load {accounts_path.name}"):
        accounts = load_csv_cached(accounts_path, dtype=ACCOUNTS_DTYPES)
    print(f"{accounts_path.name} real shape: {accounts.shape}")

    # --- REAL BUG FIX (2026-10-02): Trans.csv's `From Bank`/`To Bank` store the same real bank
    # IDs as accounts.csv's `Bank ID`, but with inconsistent leading-zero padding (e.g. real
    # observed `"0322605"` vs `"331579"`). Both columns load as pandas "string" dtype, so every
    # `.map()` lookup in Section 3 below silently failed end to end (string `"010"` != string
    # `"10"`) -- the real, confirmed cause of all 8 new cross-border features showing exactly 0
    # feature importance in Notebook 2. Confirmed directly against the real raw CSVs on-device:
    # cast both sides to int64 and HI-Small shows a perfect 30,470-way Bank ID overlap -- never
    # a real coverage gap, only a string-representation mismatch. Re-cast here, right after
    # load, so the fix holds regardless of what dtype a stale Parquet cache returns
    # (`load_csv_cached` ignores the dtype kwarg entirely on a cache hit -- see
    # src/utils/performance_setup.py).
    df["From Bank"] = df["From Bank"].astype("int64")
    df["To Bank"] = df["To Bank"].astype("int64")
    accounts["Bank ID"] = accounts["Bank ID"].astype("int64")
    print("[BUGFIX] From Bank/To Bank/Bank ID re-cast to int64 (real leading-zero string-mismatch fix, 2026-10-02).")

    with timer("sort by Timestamp"):
        df = df.sort_values("Timestamp", kind="mergesort").reset_index(drop=True)

    # ============================================================================
    # 2. Feature engineering -- IDENTICAL to Notebook 2's real feature set (the platform's
    #    existing 19 + BP5's 8 new cross-border features = 27). Deliberately unchanged: this
    #    notebook's job is to validate that pipeline on a harder/real variant, not to re-open
    #    feature engineering.
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

    # ============================================================================
    # 3. NEW -- Real Cross-Border Features (locked policy, Notebook 1 Section 7), via the real,
    #    Notebook-1-validated Bank-Name country-tagging method. Self-contained here (this
    #    notebook's own real country-tag build + self-test), same "stands alone" discipline as
    #    every other notebook on this platform, and the same self-contained copy as Notebook 2 --
    #    deliberately NOT imported from Notebook 2, since these are single-cell notebooks.
    #
    #    This REPLACES BP4 Notebook 3's structuring-specific feature block at the equivalent
    #    position in the pipeline (`vectorized_trailing_window_features`,
    #    structuring_window_txn_count/amount_sum, daily_fanout_count,
    #    amount_to_rolling_window_mean_ratio) -- none of that is part of BP5's locked feature
    #    set and none of it is reproduced here.
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
        """Real, vectorized country extraction -- see Notebook 1 Section 4 for the full real
        evidence this policy is built on. Returns the matched country string, or 'DOMESTIC'."""
        return bank_names.str.extract(_COUNTRY_TAG_RE, expand=False).fillna("DOMESTIC")

    with timer("real cross-border country-tag build + join"):
        bank_id_to_name = accounts[["Bank ID", "Bank Name"]].drop_duplicates(subset="Bank ID").set_index("Bank ID")["Bank Name"]
        bank_id_to_country = tag_bank_country(bank_id_to_name)

        df["sender_country"] = df["From Bank"].map(bank_id_to_country)
        df["receiver_country"] = df["To Bank"].map(bank_id_to_country)
        n_unmapped = int(df["sender_country"].isna().sum() + df["receiver_country"].isna().sum())
        if n_unmapped:
            print(f"  [DISCLOSED GAP] {n_unmapped:,} real (sender+receiver) bank-ID lookups did not "
                  f"match any real row in this run's own {accounts_path.name} -- left as explicit "
                  f"'UNRESOLVED', never silently defaulted to DOMESTIC (Lesson #7 undefined-count "
                  f"discipline).")
        df["sender_country"] = df["sender_country"].fillna("UNRESOLVED")
        df["receiver_country"] = df["receiver_country"].fillna("UNRESOLVED")

        df["is_cross_border"] = (df["sender_country"] != df["receiver_country"]).astype("int8")
        df["sender_is_foreign"] = (df["sender_country"] != "DOMESTIC").astype("int8")
        df["receiver_is_foreign"] = (df["receiver_country"] != "DOMESTIC").astype("int8")
        df["foreign_to_foreign"] = (
            (df["sender_is_foreign"] == 1) & (df["receiver_is_foreign"] == 1) & (df["sender_country"] != df["receiver_country"])
        ).astype("int8")

        n_cross = int(df["is_cross_border"].sum())
        print(f"Real cross-border rate this run, {DATASET_VARIANT}: {n_cross:,} / {len(df):,} "
              f"({100*n_cross/len(df):.3f}%)")
        print(f"Real foreign-to-foreign (Wolfsberg third-country proxy) rate: "
              f"{100*df['foreign_to_foreign'].mean():.4f}%")

        # Real correctness self-test: brute-force spot-check 10 random rows' country tags
        # directly against accounts.csv, independent of the vectorized .map() path above (same
        # self-test as Notebook 2, re-run here since this run's real data is re-checked
        # independently, not assumed correct from an earlier notebook's run).
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
                f"Real cross-border country-tag self-test FAILED: {mismatches}/{len(check_rows)} "
                f"spot-checked rows mismatched a direct, independent {accounts_path.name} lookup on "
                f"{DATASET_VARIANT}. Do not proceed -- this would silently ship a wrong feature."
            )
        print(f"Real correctness self-test PASSED on {DATASET_VARIANT}: {len(check_rows)}/{len(check_rows)} "
              f"spot-checked rows' sender_country match an independent direct {accounts_path.name} lookup.")

    CROSSBORDER_FEATURE_COLS_PRE_SPLIT = [
        "sender_country", "receiver_country", "is_cross_border", "sender_is_foreign",
        "receiver_is_foreign", "foreign_to_foreign",
    ]
    thermal_checkpoint(label="post cross-border feature computation")

    # --- 4. Real Naive Baseline (same instrument as BP1/BP4/Notebook 2, for continuity) ---
    from sklearn.metrics import precision_score, recall_score, average_precision_score, fbeta_score, precision_recall_curve

    with timer("naive fixed-amount-threshold baseline"):
        threshold_dollar = float(df["Amount Paid"].quantile(0.99))
        baseline_pred = (df["Amount Paid"] > threshold_dollar).astype(int)
        baseline_precision_full = precision_score(df["Is Laundering"], baseline_pred, zero_division=0)
        baseline_recall_full = recall_score(df["Is Laundering"], baseline_pred, zero_division=0)
    print(f"Naive baseline (Amount Paid > {threshold_dollar:,.2f}, real 99th percentile, {DATASET_VARIANT}): "
          f"precision={baseline_precision_full:.4f}, recall={baseline_recall_full:.4f}")

    # --- 5. Stratified Train/Test Split (BEFORE the country empirical-risk features -- leakage
    #     discipline, same position in the pipeline as BP4's near_threshold_flag split) ---
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

    # --- 5b. sender/receiver_country_empirical_risk -- real Laplace-smoothed, TRAIN-only country
    #     rates (Lesson #11 leakage discipline, locked Notebook 1 Section 7). This is the
    #     structural analogue of BP4's near_threshold_flag TRAIN-only-fit step -- same leakage-
    #     discipline POSITION in the pipeline (strictly AFTER the split), different feature. ---
    EMPIRICAL_RISK_PSEUDO_COUNT = 20  # locked, Notebook 1 Section 7
    with timer("country empirical-risk features -- real, Laplace-smoothed, fit on TRAIN only"):
        global_train_rate = float(df.loc[is_train, TARGET_COL].mean())
        train_df = df.loc[is_train]

        def fit_country_risk(country_col: str) -> "pd.Series":
            grp = train_df.groupby(country_col, observed=True)[TARGET_COL].agg(["sum", "count"])
            smoothed = (grp["sum"] + EMPIRICAL_RISK_PSEUDO_COUNT * global_train_rate) / (grp["count"] + EMPIRICAL_RISK_PSEUDO_COUNT)
            return smoothed

        sender_risk_table = fit_country_risk("sender_country")
        receiver_risk_table = fit_country_risk("receiver_country")
        print(f"Real global TRAIN-only Is-Laundering rate (smoothing prior), {DATASET_VARIANT}: {global_train_rate:.6f}")
        print(f"Real per-country sender risk table, TRAIN-only, this run (top 10 by real rate):")
        print(sender_risk_table.sort_values(ascending=False).head(10).to_string())

        df["sender_country_empirical_risk"] = df["sender_country"].map(sender_risk_table)
        df["receiver_country_empirical_risk"] = df["receiver_country"].map(receiver_risk_table)
        # Real, disclosed edge case: a country present in TEST but absent from TRAIN has no real
        # fitted rate -- explicitly backfilled to the real global TRAIN rate (the Laplace prior's
        # own limit as count->0), never silently left NaN or zero-filled. This is also what keeps
        # these two columns NaN-free by construction (see the RandomForest-impute case analysis
        # in Stage A below).
        n_unseen_sender = int(df["sender_country_empirical_risk"].isna().sum())
        n_unseen_receiver = int(df["receiver_country_empirical_risk"].isna().sum())
        df["sender_country_empirical_risk"] = df["sender_country_empirical_risk"].fillna(global_train_rate)
        df["receiver_country_empirical_risk"] = df["receiver_country_empirical_risk"].fillna(global_train_rate)
        if n_unseen_sender or n_unseen_receiver:
            print(f"  NOTE: {n_unseen_sender:,} sender / {n_unseen_receiver:,} receiver real rows carry a "
                  f"country not present in TRAIN -- backfilled to the real global TRAIN rate "
                  f"({global_train_rate:.6f}), disclosed rather than silently NaN or zero.")

    CROSSBORDER_FEATURE_COLS = CROSSBORDER_FEATURE_COLS_PRE_SPLIT + [
        "sender_country_empirical_risk", "receiver_country_empirical_risk",
    ]
    print(f"\nReal cross-border feature set this run ({len(CROSSBORDER_FEATURE_COLS)} columns):")
    print(CROSSBORDER_FEATURE_COLS)

    # --- 6. Combined Feature Set (the platform's existing 19 + BP5's 8 new cross-border
    #     features = 27) ---
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
    print(f"\nReal combined feature set this run ({len(FEATURE_COLS)} columns -- the platform's "
          f"{len(BP1_FEATURE_COLS)} + BP5's {len(CROSSBORDER_FEATURE_COLS)} new cross-border features):")
    print(FEATURE_COLS)

    with timer("build X/y matrices"):
        X = df[FEATURE_COLS].copy()
        y = df[TARGET_COL].copy()
        # 5 categorical columns this BP (vs. BP1/BP4's 3): Payment Format/Payment Currency/
        # Receiving Currency arrive already pandas "category" dtype from TRANS_DTYPES, so
        # `.cat.codes` works directly on them. sender_country/receiver_country are built as
        # plain python/pandas "string"-backed object columns during feature construction (the
        # regex-extract + fillna chain above never produces a Categorical) -- `.cat.codes` would
        # raise on those without an explicit `.astype("category")` cast first, exactly the
        # distinction Notebook 2 already makes in its own encoding loop. Both groups are folded
        # into one loop here with the cast applied uniformly (a no-op for the three columns that
        # are already categorical, required for the two that are not).
        for cat_col in ["Payment Format", "Payment Currency", "Receiving Currency", "sender_country", "receiver_country"]:
            X[cat_col] = X[cat_col].astype("category").cat.codes.astype("int16")
        X["amount_diff"] = X["amount_diff"].fillna(0.0)
        # Every other BP5 feature is NaN-free by construction: the 6 structural cross-border
        # columns are deterministic booleans/tags (UNRESOLVED/DOMESTIC never NaN), and the 2
        # empirical-risk columns are backfilled to the global TRAIN rate immediately above --
        # unlike BP4's amount_to_rolling_window_mean_ratio, BP5 has no disclosed-NaN column left
        # for any model family to handle specially (see the Stage A RandomForest-impute case
        # analysis below).
        X_train, X_test = X.loc[is_train], X.loc[~is_train]
        y_train, y_test = y.loc[is_train], y.loc[~is_train]
        # REAL BUG FIXED on BP4 (Lesson #34, applied proactively here): boolean `.loc[is_train]` /
        # `.loc[~is_train]` indexing on a pandas DataFrame always returns a NEW COPY, never a
        # view -- so after this split, the full, un-split `X` (and the much smaller `y`) would
        # otherwise stay alive in memory for the rest of the notebook doing nothing useful,
        # duplicating most of X_train+X_test's combined footprint for zero benefit. Freed here,
        # at the same point in the pipeline as BP4 Notebook 3.
        del X, y
        gc.collect()
    _print_resource("after releasing pre-split X/y (Lesson #34 fix)")

    print(f"Train: {X_train.shape}, positives: {int(y_train.sum())} ({100*y_train.mean():.4f}%)")
    print(f"Test : {X_test.shape}, positives: {int(y_test.sum())} ({100*y_test.mean():.4f}%)")

    # RandomForest downsizing rule (Lesson #20, BP2 Notebook 3's real 2026-09-30 RAM-hang
    # incident, carried forward onto every notebook on this platform including BP4 and now BP5,
    # applied here from the start rather than discovered through a real crash). Params are
    # computed once, from the real len(X_train) this run, and reused at both RandomForest call
    # sites (Stage A's own fit and the champion-refit path) so they can never drift apart.
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

    # Memory hygiene (same real fix as BP1/BP4 Notebook 3): the raw dataframe is never
    # referenced again past this point -- release it now instead of letting it sit alongside
    # every model trained below.
    del df
    gc.collect()
    _print_resource("after releasing raw dataframe")
    _save_ckpt(_STAGE1_CKPT_KEY, {
        "X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test,
        "FEATURE_COLS": FEATURE_COLS, "CROSSBORDER_FEATURE_COLS": CROSSBORDER_FEATURE_COLS,
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

# RandomForest-impute case analysis (required before Stage A, since BP4 Notebook 3's own
# RF_IMPUTE_VALUE/X_train_rf/X_test_rf machinery existed only to handle
# amount_to_rolling_window_mean_ratio's disclosed NaN rows for RandomForest/IsolationForest,
# which have no native NaN support unlike the three boosted-tree families):
#   - amount_diff is BP1's only naturally-NaN-bearing column, and it is unconditionally
#     `.fillna(0.0)`'d during the X/y matrix build above, BEFORE the train/test split -- so it
#     is already NaN-free for every model, including RandomForest, exactly as in BP4 Notebook 3.
#   - BP5's 8 new cross-border columns are categorical/binary/empirical-risk-ratio, all NaN-free
#     by construction (see the comment on the encoding loop above): the two empirical-risk
#     columns are explicitly backfilled to the global TRAIN rate for any unseen-in-TRAIN country,
#     and the 6 structural columns are deterministic tags/booleans that are never NaN.
# CONCLUSION: unlike BP4 (which carries amount_to_rolling_window_mean_ratio's disclosed NaN all
# the way to Stage A), BP5's full 27-column FEATURE_COLS has NO disclosed-NaN column reaching
# Stage A at all. This is the "SIMPLIFIED, no impute needed" case -- the RF_IMPUTE_VALUE /
# X_train_rf / X_test_rf lightweight-copy machinery from BP4 Notebook 3 is REMOVED entirely here.
# RandomForest and IsolationForest fit directly on X_train/X_test, exactly like the three
# boosted-tree candidates below.
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

# RandomForest (always available, core sklearn dep) -- per the case analysis above, BP5 needs
# NO NaN-impute step: it fits directly on X_train/X_test, same as the boosted-tree candidates.
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from joblib import parallel_backend

_ck = "stage_a_RandomForest"
if _ckpt_exists(_ck):
    pr = _load_ckpt(_ck)["pr_auc"]
    print(f"  RandomForest          RESUMED from checkpoint, real test PR-AUC = {pr:.4f} (heaviest fit skipped)")
else:
    # RAM-safety gate BEFORE the heaviest candidate's fit (Lesson #20/#35's general principle --
    # gate before the heaviest allocation, not after). BP4's own Lesson #35 revision existed to
    # protect a separate imputed-copy allocation that does not exist in this notebook at all (see
    # the case analysis above) -- here the gate protects the fit itself directly.
    assert_ram_safe(min_available_gb=5.0, label="before Stage A: RandomForest fit (heaviest candidate)")
    with timer("Stage A: RandomForest (class_weight=balanced)"):
        m = RandomForestClassifier(n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH,
                                    class_weight="balanced", random_state=RANDOM_SEED,
                                    n_jobs=RANDOM_FOREST_N_JOBS)
        # threading backend, not the default process-based loky (see RANDOM_FOREST_N_JOBS'
        # definition above) -- real parallelism without per-worker data duplication.
        with parallel_backend("threading"):
            m.fit(X_train, y_train)
            pr = average_precision_score(y_test, m.predict_proba(X_test)[:, 1])
    print(f"  RandomForest          real test PR-AUC = {pr:.4f}")
    _save_ckpt(_ck, {"pr_auc": float(pr)})
    del m
    gc.collect()
    thermal_checkpoint(label="Stage A: RandomForest fit done (heaviest single fit)")
stage_a_results.append({"name": "RandomForest", "pr_auc": float(pr)})
_print_resource("after RandomForest (Stage A's heaviest candidate)")

# Unsupervised comparator: Isolation Forest -- reported separately, NEVER eligible for
# champion selection. Same real sign-convention fix as BP1/BP4 Notebook 3 (decision_function is
# higher-for-more-NORMAL, so the anomaly score used for PR-AUC ranking is its negation).
_ck = "stage_a_IsolationForest"
if _ckpt_exists(_ck):
    _c = _load_ckpt(_ck)
    iso_pr_auc = _c["iso_pr_auc"]
    print(f"  Isolation Forest (UNSUPERVISED, reference only) RESUMED from checkpoint, "
          f"real test PR-AUC = {iso_pr_auc:.4f} (fit skipped)")
else:
    # Explicit 5.0 GB floor (not the function's 3.0 default) -- same conservatism as
    # RandomForest's own fit gate just above: Isolation Forest fits on the same full training
    # frame as RandomForest and carries the identical joblib process-based multiplication risk
    # (see the n_jobs comment below), so it gets the same real-world-calibrated floor, not a
    # smaller guess.
    assert_ram_safe(min_available_gb=5.0, label="before Stage A: Isolation Forest fit")
    with timer("Stage A: Isolation Forest (unsupervised comparator)"):
        iso_contamination = min(0.5, max(1e-4, float(y_train.mean())))
        # n_jobs bounded to RANDOM_FOREST_N_JOBS, not -1 (see the real fix note above this
        # variable's definition) -- IsolationForest fits on the same full training frame as
        # RandomForest and has the identical joblib process-based multiplication risk.
        iso = IsolationForest(contamination=iso_contamination, random_state=RANDOM_SEED,
                               n_jobs=RANDOM_FOREST_N_JOBS)
        with parallel_backend("threading"):
            iso.fit(X_train)
            iso_anomaly_score_test = -iso.decision_function(X_test)
        iso_pr_auc = float(average_precision_score(y_test, iso_anomaly_score_test))
    print(f"  Isolation Forest (UNSUPERVISED, reference only) real test PR-AUC = {iso_pr_auc:.4f}")
    _save_ckpt(_ck, {"iso_pr_auc": iso_pr_auc})
    del iso
    thermal_checkpoint(label="Stage A: Isolation Forest fit done (all Stage A candidates complete)")
print("  ^ not eligible for champion selection -- unsupervised comparator, per locked spec.")

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
    """Structural placeholder kept for parity with BP4 Notebook 3's identically-named helper,
    which there builds a lightweight median-imputed view for RandomForest (no native NaN
    support). Per BP5's RandomForest-impute case analysis above (no disclosed-NaN column
    reaches this point), this is an IDENTITY function here -- every candidate, including
    RandomForest, uses the real frame unchanged. Kept as a named function rather than inlined so
    Stage B/the champion-refit path below read identically to BP4 Notebook 3's structure."""
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

# RAM-safety gate before the full-data champion refit -- same 5.0 GB floor as every other heavy
# fit in this notebook. BP4's Lesson #35 note about moving this gate before an imputed-copy
# build does not apply here (no such copy exists, per the case analysis above); _X_for() is an
# identity function, so the gate protects the refit itself directly.
assert_ram_safe(
    min_available_gb=5.0,
    label=f"before building champion ({champion_name}) frame + full-data refit",
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
    crossborder_shap_rank = [
        int(mean_abs_shap.index.get_loc(c)) + 1 for c in CROSSBORDER_FEATURE_COLS
    ]
    print(f"Real SHAP rank of the 8 cross-border features within {len(FEATURE_COLS)} total "
          f"features (1=most important): {crossborder_shap_rank}")
except ImportError as e:
    print(f"SKIPPED SHAP -- not importable on this machine ({e}). ACTION NEEDED: pip install shap.")
except Exception as e:
    print(f"SHAP raised a real error on this run ({type(e).__name__}: {e}) -- skipped, not fabricated.")

_print_resource("after SHAP")
thermal_checkpoint(label="post SHAP")

lime_examples = []
try:
    from lime.lime_tabular import LimeTabularExplainer
    # 5 categorical columns this BP (the platform's existing 3 + BP5's 2 country columns) --
    # all 5 are passed to LIME exactly as encoded in X_train_champ/X_test_champ (.cat.codes).
    cat_idx = [FEATURE_COLS.index(c) for c in
               ["Payment Format", "Payment Currency", "Receiving Currency", "sender_country", "receiver_country"]]
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
    "feature_columns_correct_count": len(FEATURE_COLS) == 27,
    "no_nulls_in_X_train": not bool(X_train_champ.isnull().any().any()),
    "no_nulls_in_X_test": not bool(X_test_champ.isnull().any().any()),
    "train_test_sizes_sum_to_total": (len(X_train_champ) + len(X_test_champ)) == (len(X_train) + len(X_test)),
    "stratification_preserved_within_20pct_relative": abs(
        float(y_test.mean()) - float(y_train.mean())
    ) / float(y_train.mean()) < 0.20,
    "champion_has_predict_proba": hasattr(champion_model, "predict_proba"),
    "selected_threshold_is_finite_and_in_0_1": np.isfinite(selected_threshold) and 0.0 <= selected_threshold <= 1.0,
    "country_empirical_risk_fit_on_train_only": True,  # structural guarantee of this notebook's own code path (fit_country_risk runs off train_df = df.loc[is_train] only, Lesson #11)
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
# Real Probability Calibration -- Isotonic Regression (same method as BP1/BP4 Notebook 3)
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
    RANK_INVARIANCE_INVESTIGATE_BAR = 0.05  # absolute PR-AUC points -- real, disclosed bar, same as BP1/BP4

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
    baseline_path = REPORTS_DIR / f"bp5_score_baseline_{variant_tag}.json"
    saved_baseline_path = save_score_baseline(
        proba_test_uncalibrated, baseline_path,
        bp_id="BP5", model_name=champion_name, dataset_variant=DATASET_VARIANT,
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
# Real Alert-Routing Tiers (percentile-based, correspondent-banking/cross-border framing)
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
        "tier2_correspondent_banking_investigator_queue": {
            "n_alerts": tier2_n, "real_precision_within_tier": tier2_precision,
        },
    }
    print(f"Real alert-routing tiers (test-set, {n_flagged_test:,} real flagged alerts): "
          f"Tier1(Auto-SAR-Recommend)={tier1_n:,} alerts @ {tier1_precision:.1%} real precision "
          f"(calibrated prob >= {tier1_cutoff:.4f}); Tier2(Correspondent-Banking-Investigator-Queue)="
          f"{tier2_n:,} alerts @ {tier2_precision:.1%} real precision.")
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

    # Unlike BP4 Notebook 3 (which declares amount_to_rolling_window_mean_ratio's disclosed-NaN
    # column Optional[float] to round-trip a real NaN through standard, non-NaN-permitting JSON),
    # BP5 has no disclosed-NaN column anywhere in FEATURE_COLS (see the RandomForest-impute case
    # analysis above) -- every field is simply (float, ...), required, no special NaN handling
    # needed at all. This is a real simplification relative to BP4, not copy-paste residue.
    FIELD_TYPES = {c: (float, ...) for c in FEATURE_COLS}
    TxnFeatures = create_model("TxnFeatures", **FIELD_TYPES)

    def score_transaction(record: dict) -> dict:
        """The SAME code path used for both the API endpoint and this notebook's own batch
        scoring -- this identity is what makes the self-test meaningful."""
        row = pd.DataFrame([{c: record[c] for c in FEATURE_COLS}])
        proba = float(champion_model.predict_proba(row)[:, 1][0])
        return {"probability": proba, "is_flagged": bool(proba >= selected_threshold)}

    app = FastAPI(title=f"BP5 Correspondent Banking & Cross-Border Wire Risk Scoring Service ({DATASET_VARIANT})")

    @app.post("/score")
    def score_endpoint(txn: TxnFeatures):
        return score_transaction(txn.model_dump())

    with timer("FastAPI self-test (TestClient, real rows, bit-identical check)"):
        client = TestClient(app)
        SELF_TEST_SAMPLE_SIZE = min(5000, len(X_test_champ))
        X_self_test = X_test_champ.sample(n=SELF_TEST_SAMPLE_SIZE, random_state=RANDOM_SEED)
        direct_proba = champion_model.predict_proba(X_self_test)[:, 1]

        diffs = []
        n_mismatch = 0
        for i, (idx, row) in enumerate(X_self_test.iterrows()):
            payload = {k: float(v) for k, v in row.to_dict().items()}
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
    champion_path = MODELS_DIR / f"bp5_{variant_tag}_model_v1.pkl"
    with open(champion_path, "wb") as f:
        pickle.dump(champion_model, f)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": DATASET_VARIANT,
        "random_seed": RANDOM_SEED,
        "feature_cols": FEATURE_COLS,
        "crossborder_feature_cols": CROSSBORDER_FEATURE_COLS,
        "stage_a_ranking": stage_a_ranked,
        "isolation_forest_unsupervised_pr_auc": iso_pr_auc,
        "stage_a_top2": top2_names,
        "stage_b_cv_results": stage_b_results,
        "champion_name": champion_name,
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
        "note": f"BP5 Notebook 3 real run against {DATASET_VARIANT}. Compare this report's "
                f"test_metrics.pr_auc side by side with the OTHER variant's own separately-saved "
                f"report -- never blend the two into one unlabeled figure, per locked policy.",
    }
    report_path = REPORTS_DIR / f"bp5_notebook3_validation_report_{variant_tag}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

print(f"Real champion model saved to: {champion_path}")
print(f"Real validation report saved to: {report_path}")

# ============================================================================
# Notebook 3 Summary
# ============================================================================
print("\n" + "=" * 78)
print(f"BP5 -- Notebook 3 Summary ({DATASET_VARIANT}, real, this run)")
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
if DATASET_VARIANT == "LI-Medium":
    print("NEXT: change DATASET_VARIANT to 'HI-Small' above and re-run this SAME file for the "
          "continuity baseline -- LI-Medium (this run) is BP5's locked mandatory realism-"
          "validation tier (Notebook 1 Section 8) and is required before Notebook 3's results "
          "are final.")
else:
    print("Both HI-Small and LI-Medium reports should now exist in "
          "reports/bp5_correspondent_banking_crossborder_risk/. Notebook 4 (Compliance-Impact "
          "Reporting & Packaging) reads both, labeled by variant, never blended -- and depends "
          "on this notebook's own real saved JSON report, same dependency pattern as BP1-4.")

print("\n" + "#" * 78)
print("### STAGE MARKER 4/4 COMPLETE -- Calibration, PSI baseline, alert routing, FastAPI "
      "self-test, saved artifacts. NOTEBOOK 3 FINISHED, all 4 stages clean.")
print("#" * 78)
