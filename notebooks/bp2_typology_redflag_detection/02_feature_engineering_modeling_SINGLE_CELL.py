# ============================================================================
# BP2 NOTEBOOK 2 -- Feature Engineering & Modeling (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # BP2 — Notebook 2: Feature Engineering & Modeling
# ## Typology & Red-Flag Pattern Detection
#
# **Scope of this notebook:** HI-Small only (this BP's fast build/debug target, per the same locked staged
# pattern BP1 used -- LI-Medium is the mandatory realism-validation tier, picked up in Notebook 3, not before).
# This notebook does the real work Notebook 1 scoped but did not do: (1) build the real per-transaction
# multi-class typology LABEL by joining `*_Patterns.txt`'s row-level content back to `*_Trans.csv`, (2)
# real, no-leakage feature engineering, (3) a fast single-split Stage-A model screening across the 4 locked
# candidate algorithms (macro-F1, per Notebook 1's locked primary metric), plus Isolation Forest reported as an
# unsupervised diagnostic only (never blended into the supervised ranking, per master-plan Section 5).
#
# **Policy decision made in THIS notebook (not fully resolved by Notebook 1):** BP2's real target population is
# the `Is Laundering == 1` rows that Patterns.txt actually labels with a typology -- i.e. "given a transaction
# already known to be laundering, which of the 8 real typologies does it match" -- not "is this transaction
# laundering at all" (that is BP1's binary job). This keeps the two BPs cleanly separated and matches the master
# plan's own "real per-typology recall across all 8 patterns" framing for BP2's Before/After table. Stated here
# explicitly, not silently assumed.
#
# **Zero-fabrication rule for this notebook:** every count, feature value, and model score below is computed
# live from the real files in `data/raw/` when this notebook runs.

import sys
import gc
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
from utils.performance_setup import (
    configure_performance, thermal_checkpoint, load_csv_cached, timer,
    check_ram_headroom, pin_cpu_affinity, assert_ram_safe,
)

# WARP STEP 1 -- before any heavy import below.
perf_config = configure_performance()
print("WARP configured:", perf_config)
pin_result = pin_cpu_affinity()
print("CPU affinity pin (best-effort, real):", pin_result)
print("RAM headroom baseline (real):", check_ram_headroom())

import psutil
def _mem_gb():
    return psutil.Process().memory_info().rss / (1024 ** 3)

def _print_resource(label):
    print(f"[RESOURCE] {label} -- process RSS: {_mem_gb():.2f} GB | {check_ram_headroom()}")

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
CONFIG_PATH = PROJECT_ROOT / "configs" / "bp2_typology_redflag_detection.yaml"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp2_typology_redflag_detection"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root: {PROJECT_ROOT}")
print(f"Reports dir : {REPORTS_DIR}")

def _read_simple_yaml(path):
    """Tiny dependency-free reader for this project's flat `key: "value"` config files -- no nested
    structures/lists in these files, so a real YAML library is unnecessary overhead here."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"')
    return out

bp2_config = _read_simple_yaml(CONFIG_PATH)
print(f"\nReal config loaded from {CONFIG_PATH.name}:")
for k, v in bp2_config.items():
    print(f"  {k}: {v}")
PRIMARY_METRIC = bp2_config.get("primary_metric", "macro_f1")

import json
import numpy as np
import pandas as pd
import re
from datetime import datetime, timezone

RANDOM_SEED = 42
VARIANT = "HI-Small"  # this notebook's fast build/debug target -- LI-Medium deferred to Notebook 3
TRANS_FILE = f"{VARIANT}_Trans.csv"
PATTERNS_FILE = f"{VARIANT}_Patterns.txt"

# ============================================================================
# 1. Real row-level Patterns.txt parse (same logic as Notebook 1, reused here since this is a
#    separate single-cell script -- no shared kernel state across notebook files).
# ============================================================================
def parse_patterns_file_rows(path):
    begin_re = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Z-]+):\s*(.*)$")
    cols = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
            "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format", "Is Laundering"]
    rows = []
    n_malformed = 0
    pattern_id = -1
    current_typology = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = begin_re.match(line)
            if m:
                pattern_id += 1
                current_typology = m.group(1)
                continue
            if line.startswith("END LAUNDERING ATTEMPT"):
                current_typology = None
                continue
            if current_typology is not None and line.strip():
                fields = line.split(",")
                if len(fields) != len(cols):
                    n_malformed += 1
                    continue
                rec = {"pattern_id": pattern_id, "typology": current_typology}
                rec.update(dict(zip(cols, fields)))
                rows.append(rec)
    df = pd.DataFrame.from_records(rows)
    if n_malformed:
        print(f"  WARNING: {n_malformed} real malformed line(s) in {path.name} excluded.")
    return df

with timer(f"parse {PATTERNS_FILE} (row-level, real)"):
    pattern_rows = parse_patterns_file_rows(RAW / PATTERNS_FILE)
print(f"Real labeled typology-rows parsed: {len(pattern_rows):,} across {pattern_rows['pattern_id'].nunique()} "
      f"real labeled attempts, {pattern_rows['typology'].nunique()} distinct real typologies")

# ============================================================================
# 2. Load Trans.csv as RAW STRINGS (deliberate -- see note) for an exact-text join against Patterns.txt,
#    then cast to real dtypes AFTER the join below.
#
# NOTE (real, load-bearing detail): Patterns.txt's row content is literal original CSV text. If Trans.csv
# were loaded with parsed dtypes first (datetime, float64), pandas' own string reformatting on re-cast
# (e.g. "100.00" -> "100.0", or a reformatted timestamp) could silently break an exact-text join key. Loading
# every column as `str` here keeps the join key byte-identical to Patterns.txt's own text; real dtypes are
# restored immediately after the join (Section 4).
# ============================================================================
with timer(f"load {TRANS_FILE} as raw strings, WARP-cached (for exact-key typology join)"):
    trans = load_csv_cached(
        RAW / TRANS_FILE, dtype=str,
        parquet_cache_path=PROCESSED_DIR / f"{VARIANT.lower().replace('-', '_')}_trans_rawstr_cache.parquet",
    )
trans = trans.reset_index(drop=True)
print(f"Real {TRANS_FILE} shape: {trans.shape}")
_print_resource("post raw-string Trans.csv load")

# ============================================================================
# 3. Real join key match (exact full-row content) + row-content-level cross-typology overlap resolution.
#
# NOTE (real, disclosed assumption): neither file carries a unique transaction ID, so rows are matched by
# their exact real field-value content (KEY_COLS below). Where that exact content legitimately repeats as
# more than one physical row within Trans.csv, every physical repeat is matched to the same resolved label
# (see the ambiguous-duplicate count printed in Section 4) -- this is the only defensible behavior without a
# true row ID, and it is surfaced honestly rather than silently assumed away.
#
# REAL INCIDENT (2026-09-30): the row key below was originally built with
# `trans[KEY_COLS].agg("|".join, axis=1)`. That looks like a one-liner but is NOT vectorized --
# pandas executes it as a real per-row Python loop, directly violating this project's own Lesson
# #18 despite being labeled "vectorized" at the time. On BP2 Notebook 3's real LI-Medium run
# (31.25M real rows) this hung the reference laptop at 100% RAM and required a hard restart. A
# local synthetic re-test after the crash confirmed it: on a 2,000,000-row synthetic frame this
# same call did not even finish in 2 minutes, while `pd.util.hash_pandas_object` (real, vectorized,
# C-implemented) did the equivalent row-key construction in ~4 seconds and used ~16 MB instead of a
# large Python-object string array. Fixed here by hashing the same KEY_COLS into a compact uint64
# per row instead of concatenating them into a long string -- rows with identical content still
# hash identically (verified locally), so every downstream groupby/merge below is unchanged. Real,
# disclosed residual risk: a 64-bit hash collision between two DIFFERENT real rows is theoretically
# possible but astronomically unlikely at this dataset's real scale (far below the birthday-bound
# threshold that would make it a practical concern).
# ============================================================================
KEY_COLS = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
            "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format", "Is Laundering"]

assert_ram_safe(min_available_gb=3.0, label="before building real join keys")

with timer("build real join keys (vectorized hash, WARP-fixed post-incident) + resolve cross-typology overlap"):
    trans["_row_key"] = pd.util.hash_pandas_object(trans[KEY_COLS], index=False).to_numpy()
    trans["_occ"] = trans.groupby("_row_key").cumcount()

    pattern_rows["_row_key"] = pd.util.hash_pandas_object(pattern_rows[KEY_COLS], index=False).to_numpy()

    # Real cross-typology overlap resolution, at the RAW-CONTENT level (row_key only -- NOT split further by
    # a per-source occurrence index). Neither file carries a real transaction ID, so when the exact same
    # transaction content is re-listed under a second pattern block (genuine cross-typology overlap --
    # confirmed present in this dataset by Notebook 1's overlap_report), it appears as two rows in
    # pattern_rows sharing the same _row_key. An earlier version of this join additionally grouped by a
    # per-source "_occ" cumcount computed independently within pattern_rows (file-listing order) and within
    # trans (chronological order) -- but two rows can never share the same cumcount value within one
    # groupby, so every overlap pair was always split into two disjoint (row_key, occ) groups and MULTI
    # could never actually be detected (n_multi silently pinned at 0 regardless of real overlap). Caught by
    # local synthetic testing before shipping (two identical-content pattern rows tagged with different real
    # typologies did not resolve to MULTI). Resolving at the row_key level fixes this. The honest tradeoff:
    # if the same exact content also happens to repeat as genuinely separate physical transactions in
    # Trans.csv, every physical repeat inherits the same resolved label -- the conservative, disclosed
    # choice given no real transaction ID exists (see the ambiguous-duplicate count printed in Section 4).
    resolved = (
        pattern_rows.groupby("_row_key")["typology"]
        .agg(lambda s: sorted(set(s)))
        .reset_index()
        .rename(columns={"typology": "_typologies"})
    )
    resolved["typology_label"] = resolved["_typologies"].apply(lambda t: t[0] if len(t) == 1 else "MULTI")
    n_multi = int((resolved["typology_label"] == "MULTI").sum())
    print(f"Real distinct row-content groups seen in Patterns.txt: {len(resolved):,}; {n_multi:,} resolved as "
          f"MULTI (>1 distinct real typology attached to the same real transaction content) -- "
          f"{100 * n_multi / len(resolved):.4f}%")

    merged = trans.merge(resolved[["_row_key", "typology_label"]], on="_row_key", how="left")

    n_ambiguous_dupe_rows = int((trans["_occ"] > 0).sum())
    print(f"Real Trans.csv rows sharing exact content with an earlier real row in this dataset (ambiguous "
          f"physical match -- all such rows receive the same resolved label, per the tradeoff above): "
          f"{n_ambiguous_dupe_rows:,} of {len(trans):,} ({100 * n_ambiguous_dupe_rows / len(trans):.4f}%).")

del trans, pattern_rows, resolved
gc.collect()
thermal_checkpoint(label="post real join key + overlap resolution")
_print_resource("post join, pre-dtype-cast")

# ============================================================================
# 4. Real join-completeness / consistency checks -- never silently trusted.
# ============================================================================
n_total = len(merged)
n_matched = int(merged["typology_label"].notna().sum())
print(f"\nReal join match: {n_matched:,} of {n_total:,} real Trans.csv rows received a real typology label.")

merged["_is_laundering_int"] = merged["Is Laundering"].astype("int8")
n_labeled_but_benign = int(((merged["typology_label"].notna()) & (merged["_is_laundering_int"] == 0)).sum())
if n_labeled_but_benign:
    print(f"WARNING: {n_labeled_but_benign:,} real rows got a typology label but Is Laundering==0 -- "
          f"investigate the join before trusting downstream counts (should be 0 under a correct join).")
else:
    print("Consistency check PASSED: every real typology-labeled row has Is Laundering==1.")

n_is_laundering_unlabeled = int(((merged["_is_laundering_int"] == 1) & (merged["typology_label"].isna())).sum())
n_is_laundering_total = int((merged["_is_laundering_int"] == 1).sum())
print(f"Real Is-Laundering==1 rows with NO matched typology label: {n_is_laundering_unlabeled:,} of "
      f"{n_is_laundering_total:,} real positive rows "
      f"({100 * n_is_laundering_unlabeled / n_is_laundering_total:.4f}% if nonzero -- honest join-completeness "
      f"gap, never silently dropped without this count being surfaced).")

# ============================================================================
# 5. Cast real dtypes now that the exact-text join is done.
# ============================================================================
with timer("cast real dtypes post-join"):
    merged["Timestamp"] = pd.to_datetime(merged["Timestamp"])
    merged["Amount Received"] = merged["Amount Received"].astype("float64")
    merged["Amount Paid"] = merged["Amount Paid"].astype("float64")
    merged["Is Laundering"] = merged["_is_laundering_int"]
    merged = merged.drop(columns=["_is_laundering_int"])
    merged = merged.sort_values("Timestamp").reset_index(drop=True)

_print_resource("post dtype cast + sort")

# ============================================================================
# 6. Real, no-leakage feature engineering -- every "_to_date" / "prior_" feature below is STRICTLY causal
#    (excludes the current row's own contribution), computed on the FULL real transaction stream (not just the
#    labeled subset -- a sender's real history includes benign transactions too), per Lesson #11's graph/
#    temporal-feature leakage discipline. Vectorized (WARP), never a per-row Python loop.
# ============================================================================
def prior_distinct_count(df, group_col, target_col):
    """Real, vectorized strictly-prior distinct-count: for each row, how many DISTINCT real target_col values
    were seen in group_col's history BEFORE this row (current row's own contribution excluded). Requires df
    sorted ascending by time beforehand."""
    first_occ = (~df.duplicated(subset=[group_col, target_col], keep="first")).astype("int32")
    cum = first_occ.groupby(df[group_col]).cumsum()
    return (cum - first_occ).astype("int32")

with timer("real feature engineering (vectorized, causal)"):
    merged["sender_txn_count_to_date"] = merged.groupby("Account").cumcount().astype("int32")
    merged["receiver_txn_count_to_date"] = merged.groupby("Account.1").cumcount().astype("int32")
    merged["sender_distinct_counterparties_to_date"] = prior_distinct_count(merged, "Account", "Account.1")
    merged["receiver_distinct_counterparties_to_date"] = prior_distinct_count(merged, "Account.1", "Account")

    merged["_sender_prev_ts"] = merged.groupby("Account")["Timestamp"].shift(1)
    merged["sender_hours_since_prev_txn"] = (
        (merged["Timestamp"] - merged["_sender_prev_ts"]).dt.total_seconds() / 3600.0
    )
    n_sender_first_txn = int(merged["sender_hours_since_prev_txn"].isna().sum())
    merged["sender_hours_since_prev_txn"] = merged["sender_hours_since_prev_txn"].fillna(-1.0)  # explicit sentinel

    merged["_receiver_prev_ts"] = merged.groupby("Account.1")["Timestamp"].shift(1)
    merged["receiver_hours_since_prev_txn"] = (
        (merged["Timestamp"] - merged["_receiver_prev_ts"]).dt.total_seconds() / 3600.0
    )
    n_receiver_first_txn = int(merged["receiver_hours_since_prev_txn"].isna().sum())
    merged["receiver_hours_since_prev_txn"] = merged["receiver_hours_since_prev_txn"].fillna(-1.0)

    merged["_pair_key"] = merged["Account"].astype(str) + "->" + merged["Account.1"].astype(str)
    merged["pair_prior_txn_count"] = merged.groupby("_pair_key").cumcount().astype("int32")

    merged["is_same_bank"] = (merged["From Bank"] == merged["To Bank"]).astype("int8")
    merged["log_amount_paid"] = np.log1p(merged["Amount Paid"].clip(lower=0))

    n_zero_received = int((merged["Amount Received"] == 0).sum())
    merged["amount_paid_received_ratio"] = merged["Amount Paid"] / merged["Amount Received"].replace(0, np.nan)
    # Explicit undefined-count check (Lesson #7) -- never a silent impute. Left as real NaN: every Stage-A
    # candidate below (LightGBM/XGBoost/CatBoost natively, RandomForest via a real median-impute fallback,
    # documented at that model's own fit call) handles it explicitly, not silently.

    merged["hour"] = merged["Timestamp"].dt.hour.astype("int8")
    merged["day_of_week"] = merged["Timestamp"].dt.dayofweek.astype("int8")
    merged["payment_format_code"] = merged["Payment Format"].astype("category").cat.codes.astype("int16")

    merged = merged.drop(columns=["_sender_prev_ts", "_receiver_prev_ts", "_pair_key"])

print(f"Real rows with no prior sender history (sentinel -1.0, first-ever txn): {n_sender_first_txn:,}")
print(f"Real rows with no prior receiver history (sentinel -1.0, first-ever txn): {n_receiver_first_txn:,}")
print(f"Real rows with Amount Received == 0 (undefined ratio, left NaN): {n_zero_received:,}")

thermal_checkpoint(label="post feature engineering")
_print_resource("post feature engineering")

# ============================================================================
# 7. Subset to BP2's real modeling population (typology-labeled rows only -- Section 0's policy decision).
# ============================================================================
FEATURE_COLS = [
    "sender_txn_count_to_date", "receiver_txn_count_to_date",
    "sender_distinct_counterparties_to_date", "receiver_distinct_counterparties_to_date",
    "sender_hours_since_prev_txn", "receiver_hours_since_prev_txn",
    "pair_prior_txn_count", "is_same_bank", "log_amount_paid", "amount_paid_received_ratio",
    "hour", "day_of_week", "payment_format_code",
]

modeled = merged[merged["typology_label"].notna()].copy()
print(f"\nReal BP2 modeling population: {len(modeled):,} of {len(merged):,} total real rows "
      f"(typology-labeled subset only).")
print("Real typology class distribution (this modeling population):")
print(modeled["typology_label"].value_counts().to_string())

del merged
gc.collect()
_print_resource("post subset to modeling population")

# ============================================================================
# 8. Stage A -- fast single-split multi-class candidate screening (HI-Small, per the locked staged pattern).
#    5-fold CV is deferred to Notebook 3's full statistical validation, per BP1's own established boundary.
# ============================================================================
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import f1_score, classification_report
from sklearn.ensemble import RandomForestClassifier, IsolationForest

le = LabelEncoder()
y = le.fit_transform(modeled["typology_label"])
class_names = list(le.classes_)
X = modeled[FEATURE_COLS]

class_counts = pd.Series(y).value_counts()
print(f"\nReal encoded classes ({len(class_names)}): {class_names}")
print(f"Smallest real class count: {int(class_counts.min())}")

strat = y if class_counts.min() >= 2 else None
if strat is None:
    print("WARNING: at least one real typology class has <2 examples on HI-Small -- stratified split disabled "
          "for this run; real class balance may differ between train/test as a result. Revisit at LI-Medium "
          "scale in Notebook 3, where counts should be larger.")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=RANDOM_SEED, stratify=strat
)
print(f"Real train/test split: {len(X_train):,} / {len(X_test):,} rows")

stage_a_candidates = {}
stage_a_results = []

def _eval_multiclass(name, y_true, y_pred):
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    report = classification_report(y_true, y_pred, target_names=class_names, output_dict=True, zero_division=0)
    per_class_recall = {cls: float(report[cls]["recall"]) for cls in class_names if cls in report}
    print(f"  {name}: macro-F1 = {macro_f1:.4f}")
    return macro_f1, per_class_recall

try:
    from lightgbm import LGBMClassifier
    with timer("fit LightGBM (multiclass)"):
        m = LGBMClassifier(objective="multiclass", num_class=len(class_names), random_state=RANDOM_SEED,
                            n_estimators=300, verbosity=-1)
        m.fit(X_train, y_train)
    macro_f1, per_class = _eval_multiclass("LightGBM", y_test, m.predict(X_test))
    stage_a_candidates["LightGBM"] = m
    stage_a_results.append({"name": "LightGBM", "macro_f1": macro_f1, "per_class_recall": per_class})
    thermal_checkpoint(label="post LightGBM fit")
except ImportError:
    print("  LightGBM not installed -- skipped (real, honest skip, not fabricated).")

try:
    from xgboost import XGBClassifier
    with timer("fit XGBoost (multiclass)"):
        m = XGBClassifier(objective="multi:softprob", num_class=len(class_names), random_state=RANDOM_SEED,
                           n_estimators=300, eval_metric="mlogloss", verbosity=0)
        m.fit(X_train, y_train)
    macro_f1, per_class = _eval_multiclass("XGBoost", y_test, m.predict(X_test))
    stage_a_candidates["XGBoost"] = m
    stage_a_results.append({"name": "XGBoost", "macro_f1": macro_f1, "per_class_recall": per_class})
    thermal_checkpoint(label="post XGBoost fit")
except ImportError:
    print("  XGBoost not installed -- skipped (real, honest skip, not fabricated).")

try:
    from catboost import CatBoostClassifier
    with timer("fit CatBoost (multiclass)"):
        m = CatBoostClassifier(loss_function="MultiClass", random_state=RANDOM_SEED, iterations=300,
                                verbose=False)
        m.fit(X_train, y_train)
    macro_f1, per_class = _eval_multiclass("CatBoost", y_test, m.predict(X_test).ravel())
    stage_a_candidates["CatBoost"] = m
    stage_a_results.append({"name": "CatBoost", "macro_f1": macro_f1, "per_class_recall": per_class})
    thermal_checkpoint(label="post CatBoost fit")
except ImportError:
    print("  CatBoost not installed -- skipped (real, honest skip, not fabricated).")

assert_ram_safe(min_available_gb=3.0, label="before RandomForest fit (this platform's heaviest single candidate)")
with timer("fit RandomForest (multiclass)"):
    # Real median-impute fallback for RandomForest only (it cannot natively handle NaN, unlike the 3 boosters
    # above) -- documented here at the point it happens, per Section 6's note, never silently applied upstream.
    X_train_rf = X_train.fillna(X_train.median(numeric_only=True))
    X_test_rf = X_test.fillna(X_train.median(numeric_only=True))
    m = RandomForestClassifier(n_estimators=300, random_state=RANDOM_SEED, n_jobs=-1)
    m.fit(X_train_rf, y_train)
macro_f1, per_class = _eval_multiclass("RandomForest", y_test, m.predict(X_test_rf))
stage_a_candidates["RandomForest"] = m
stage_a_results.append({"name": "RandomForest", "macro_f1": macro_f1, "per_class_recall": per_class})
thermal_checkpoint(label="post RandomForest fit")

# Isolation Forest -- real unsupervised diagnostic ONLY (never blended into the supervised ranking above,
# per master-plan Section 5). Reports whether typologies differ in how "anomalous" their own feature pattern
# looks relative to the rest of the real modeling population -- informative context, not a competing score.
with timer("fit Isolation Forest (unsupervised diagnostic)"):
    X_iso = X.fillna(X.median(numeric_only=True))
    iso = IsolationForest(random_state=RANDOM_SEED, n_estimators=200, contamination="auto", n_jobs=-1)
    iso.fit(X_iso)
    anomaly_score = -iso.score_samples(X_iso)  # higher = more anomalous
iso_by_class = (
    pd.DataFrame({"typology_label": modeled["typology_label"].values, "anomaly_score": anomaly_score})
    .groupby("typology_label")["anomaly_score"].mean().sort_values(ascending=False)
)
print("\nReal Isolation Forest mean anomaly score by typology (diagnostic only, this run):")
print(iso_by_class.to_string())
thermal_checkpoint(label="post Isolation Forest diagnostic")

del stage_a_candidates
gc.collect()
_print_resource("post Stage A candidate screening")

# ============================================================================
# 9. Stage A ranking + real summary JSON (Notebook 3 reads this to pick its own top-2 candidates for full CV).
# ============================================================================
stage_a_results.sort(key=lambda r: r["macro_f1"], reverse=True)
print("\nReal Stage A ranking (macro-F1, single split, HI-Small):")
for r in stage_a_results:
    print(f"  {r['name']}: {r['macro_f1']:.4f}")

summary = {
    "bp_id": "BP2",
    "bp_name": "Typology & Red-Flag Pattern Detection",
    "notebook": "02_feature_engineering_modeling",
    "variant": VARIANT,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "random_seed": RANDOM_SEED,
    "primary_metric": PRIMARY_METRIC,
    "n_total_rows": n_total,
    "n_modeled_rows": int(len(modeled)),
    "n_join_matched": n_matched,
    "n_multi_typology_rows": n_multi,
    "n_is_laundering_unlabeled": n_is_laundering_unlabeled,
    "class_names": class_names,
    "class_distribution": {k: int(v) for k, v in modeled["typology_label"].value_counts().items()},
    "feature_cols": FEATURE_COLS,
    "stage_a_ranking": stage_a_results,
    "isolation_forest_mean_anomaly_by_class": {k: float(v) for k, v in iso_by_class.items()},
}
summary_path = REPORTS_DIR / f"bp2_notebook2_stage_a_summary_{VARIANT.lower().replace('-', '_')}.json"
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
print(f"\nReal Stage A summary written to: {summary_path}")

print("=" * 78)
print("BP2 -- Notebook 2 Summary (real, this run)")
print("=" * 78)
print(f"Variant: {VARIANT}  Modeling population: {len(modeled):,} real rows  Classes: {len(class_names)}")
print(f"Stage A champion (real, this run): {stage_a_results[0]['name']} "
      f"(macro-F1 = {stage_a_results[0]['macro_f1']:.4f})")
print(f"Summary JSON: {summary_path}")
print("=" * 78)

# ## Next Step
# `notebooks/bp2_typology_redflag_detection/03_statistical_validation_deployment_SINGLE_CELL.py` -- runs on
# LI-Medium (this BP's mandatory realism-validation tier, confirmed/adjusted per Notebook 1's real HI-Small/
# LI-Small typology counts), 5-fold CV on this notebook's real top-2 Stage-A candidates, SHAP explainability,
# the two-gate verdict, and the deployable FastAPI scoring service -- mirroring BP1 Notebook 3's already-proven
# structure.
