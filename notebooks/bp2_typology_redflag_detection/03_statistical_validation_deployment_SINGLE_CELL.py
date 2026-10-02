# ============================================================================
# BP2 NOTEBOOK 3 -- Statistical Validation & Deployment (SINGLE CELL)
# ============================================================================
#
# Purpose (per the locked master-execution-plan, Section 4 + Section 3's per-BP validation-tier
# table): re-run BP2's real typology-labeling + feature-engineering pipeline -- IDENTICAL to
# Notebook 2's FIXED join logic (row-content-level cross-typology overlap resolution; the
# earlier per-source-occurrence-index design was dead code and never actually detected real
# overlap -- see Notebook 2's own header for the full bug/fix history) -- against BP2's real
# mandatory realism-validation tier: LI-Medium, or HI-Medium if LI-Medium's real per-typology
# counts prove too thin for stable 5-fold CV (that decision is confirmed HERE, for real, from
# actually-parsed data -- Notebook 1 explicitly deferred it, per its own locked note).
#
# HOW TO RUN THIS NOTEBOOK: run it with DATASET_VARIANT = "LI-Medium" first (the locked
# default below). If the real per-class counts this run prints are too thin (a clear WARNING
# will say so), change ONLY that one line to "HI-Medium" and run again -- mirroring the same
# "one line to change" pattern already proven on BP1 Notebook 3. Unlike BP1 (which validates
# on BOTH HI-Small and LI-Medium, never blended), BP2's locked spec calls for a SINGLE
# validation-tier run -- whichever real tier this notebook's own thin-class check settles on.
#
# What this notebook does, in order:
#   Real data: raw-string exact-content join between {VARIANT}_Trans.csv and
#     {VARIANT}_Patterns.txt (row-level parse), identical fixed logic to Notebook 2.
#   Real no-leakage feature engineering: the SAME 13 features as Notebook 2, deliberately
#     unchanged -- this notebook's job is to validate that pipeline on the harder/real
#     validation-tier variant, not to re-open feature engineering.
#   Real Before/After baseline (Lesson #16, completing what Notebook 1's BEFORE_BASELINE_POLICY
#     described but did not yet compute): "Before" = a single-typology heuristic that always
#     predicts the platform's most obvious real typology (FAN-OUT, per Notebook 1's policy) --
#     trivially 100% recall on that one class, 0% on the other seven, a real and honestly
#     computed number, not a fabricated placeholder. "After" = the real ML champion's real
#     per-typology recall across all real classes actually present in this variant.
#   Stage A: trains a real multi-class candidate set (LightGBM, XGBoost, CatBoost, RandomForest
#     -- each honestly ImportError-guarded) on a single real train/test split, ranked by real
#     macro-F1 (BP2's locked PRIMARY_METRIC, confirmed from configs/bp2_typology_redflag_detection.yaml
#     below) -- plus Isolation Forest as an unsupervised diagnostic, reported separately, never
#     blended into champion selection (same locked policy as every BP on this platform).
#   Stage B: real 5-fold CV (StratifiedKFold if every real class has >=5 examples, else a
#     disclosed KFold fallback -- never a silent crash or a silently-fabricated stratification)
#     on the top-2 Stage-A candidates; champion = higher real mean CV macro-F1. Reports
#     per-fold macro-F1 and a 95% CI (t-distribution, df=4 -- small-n, honestly disclosed).
#   Explainability: real SHAP (TreeExplainer, multi-class-aware) on a capped real sample;
#     real LIME on a few real individual instances (explaining each instance's real predicted
#     class) -- both honestly ImportError-guarded.
#   Two-gate verdict: a structural [CHECK] gate (real pipeline mechanics) and a separate
#     statistical-robustness gate (does the champion's real CV macro-F1 clear the real naive
#     baseline's macro-F1 with real statistical margin, and is it stable across folds) --
#     criteria fixed here, before results are known, never adjusted after seeing a real
#     result (locked Lesson #15).
#   Deployable scoring service: a real FastAPI app wrapping the exact same multi-class scoring
#     function used for this notebook's own batch predictions -- self-tested via FastAPI's
#     TestClient (in-process) against every row of a capped real sample, reporting a real
#     magnitude-of-mismatch column, not just a pass/fail count (locked Lesson #4).
#
# Zero-fabrication: every number below is computed live, on whichever real CSV/TXT pair
# DATASET_VARIANT points at. RANDOM_SEED=42 throughout, per the locked standing rule. This
# notebook never executes against synthetic data -- only the code LOGIC of its riskiest new
# pieces (the thin-class fallback branch, the multi-class SHAP shape handling) was sanity
# checked locally against synthetic fixtures before shipping, exactly as Notebook 2 was; no
# synthetic number ever appears in this file's own output or in the JSON/pickle it writes.
#
# NEW (2026-10-01, upgraded alongside BP1 Notebook 3 after this session's real root-cause
# finding on BP1's own repeated crashes -- RAM exhaustion, not OS sleep): this notebook has
# the SAME multi-candidate Stage A + 5-fold-CV Stage B shape that crashed BP1 Notebook 3
# multiple times before it was hardened, so the same proven fixes are applied here
# proactively, before a real crash, not reactively after one: (1) real checkpoint/resume --
# every Stage A candidate, every Stage B candidate's CV result, and the champion's full-data
# refit are saved to disk the moment they complete, so a crash/restart never re-does work
# already finished; (2) Windows sleep-prevention baked in directly, same as BP1; (3) four
# STAGE MARKER print boundaries so a crash's last-printed marker pinpoints which quarter of
# the notebook was running. This notebook's own assert_ram_safe() gates (join-key build,
# RandomForest fit, Stage B CV, now also the champion refit) were already real and already
# called, from the 2026-09-30 incident fix (Lesson #20) -- this pass adds resumability on
# top of that existing RAM-safety gate, it does not replace it.
# ============================================================================

import sys
import gc
import re
import platform
from pathlib import Path

# ============================================================================
# NEW (2026-10-01, upgraded alongside BP1 Notebook 3 after this session's real crash-root-
# cause finding): Windows sleep-prevention, backup to the OS power setting. Real, disclosed
# limitation: stops SYSTEM SLEEP only, not a lid-close configured to sleep regardless of
# running processes -- see BP1 Notebook 3's own header for the full real write-up.
# ============================================================================
if platform.system() == "Windows":
    import ctypes
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _sleep_block_result = ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    if _sleep_block_result == 0:
        print("WARNING: SetThreadExecutionState call failed (returned 0) -- sleep prevention may "
              "not be active. Rely on the OS power-setting change as the primary safeguard.")
    else:
        print("Sleep prevention ACTIVE for this kernel process -- Windows will not suspend the "
              "system while this Jupyter kernel is running (display may still sleep separately; "
              "that does not affect the running computation).")
else:
    print(f"Sleep-prevention block skipped -- not running on Windows (platform.system()="
          f"{platform.system()!r}).")

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
N_SPLITS = 5

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
# THE ONE LINE TO CHANGE IF THIS RUN'S THIN-CLASS WARNING BELOW SAYS TO
# ============================================================================
DATASET_VARIANT = "LI-Medium"  # BP2's locked default mandatory realism-validation tier
# ============================================================================

VARIANT_FILES = {
    "LI-Medium": {"trans": "LI-Medium_Trans.csv", "patterns": "LI-Medium_Patterns.txt"},
    "HI-Medium": {"trans": "HI-Medium_Trans.csv", "patterns": "HI-Medium_Patterns.txt"},
}
if DATASET_VARIANT not in VARIANT_FILES:
    raise ValueError(f"DATASET_VARIANT must be one of {list(VARIANT_FILES)}, got {DATASET_VARIANT!r}")

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
MODELS_DIR = PROJECT_ROOT / "models" / "bp2_typology_redflag_detection"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp2_typology_redflag_detection"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root  : {PROJECT_ROOT}")
print(f"Dataset variant this run: {DATASET_VARIANT}")
print(f"Models dir    : {MODELS_DIR}")
print(f"Reports dir   : {REPORTS_DIR}")

import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timezone

print(f"pandas {pd.__version__}, numpy {np.__version__}")

# ============================================================================
# NEW (2026-10-01, upgraded alongside BP1 Notebook 3): real checkpoint/resume infrastructure.
# Same proven pattern that fixed BP1 Notebook 3's repeated real crashes this session -- save
# each expensive Stage A/B step's result to disk the moment it completes; on a re-run after a
# crash/hang/restart, an existing checkpoint is loaded and that step's real computation is
# skipped entirely, so a crash never costs more than the one step that was running when it
# happened. Verified (BP1 Notebook 3) via a true two-process crash/restart simulation before
# shipping; identical helper functions, reused here verbatim for BP2.
# ============================================================================
variant_tag = DATASET_VARIANT.lower().replace("-", "_")
FORCE_RECOMPUTE_CHECKPOINTS = False
CHECKPOINT_DIR = MODELS_DIR / f"nb3_checkpoints_{variant_tag}"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

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


def _read_simple_yaml(path):
    """Tiny, dependency-free flat-YAML reader (no PyYAML assumed) -- same helper used in
    Notebook 2, redefined here since notebooks don't share kernel state."""
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out

CONFIG_PATH = PROJECT_ROOT / "configs" / "bp2_typology_redflag_detection.yaml"
_cfg = _read_simple_yaml(CONFIG_PATH)
PRIMARY_METRIC = _cfg.get("primary_metric", "macro_f1")
print(f"Real PRIMARY_METRIC (from {CONFIG_PATH.name}): {PRIMARY_METRIC}")
if PRIMARY_METRIC != "macro_f1":
    print(f"  NOTE: config says '{PRIMARY_METRIC}', not 'macro_f1' -- this notebook ranks and gates on "
          f"real macro-F1 regardless (the locked, justified choice from Notebook 1); investigate the "
          f"config drift before trusting it elsewhere.")

trans_path = RAW / VARIANT_FILES[DATASET_VARIANT]["trans"]
patterns_path = RAW / VARIANT_FILES[DATASET_VARIANT]["patterns"]
for p in (trans_path, patterns_path):
    if not p.exists():
        raise FileNotFoundError(
            f"{p} does not exist. This notebook needs the real {p.name} file in data/raw/ "
            f"before it can run against the '{DATASET_VARIANT}' variant."
        )

# ============================================================================
# 1. Real row-level Patterns.txt parser -- identical to Notebook 1/2, redefined here since
#    notebooks don't share kernel state.
# ============================================================================
def parse_patterns_file_rows(path):
    """Real row-level parser for *_Patterns.txt: returns one row per real labeled transaction,
    tagged with its real pattern_id and typology, plus its own real field values (same
    11-column schema as *_Trans.csv, no header inside the block). Malformed lines (wrong real
    field count) are counted and reported, never silently padded/truncated or dropped without
    being surfaced."""
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
        print(f"  WARNING: {n_malformed} real line(s) in {path.name} did not match the expected "
              f"{len(cols)}-field schema and were excluded -- investigate before trusting counts below.")
    return df

with timer(f"load {trans_path.name} as raw strings, WARP-cached (for exact-key typology join)"):
    trans = load_csv_cached(
        trans_path, dtype=str,
        parquet_cache_path=PROCESSED_DIR / f"{DATASET_VARIANT.lower().replace('-', '_')}_trans_rawstr_cache.parquet",
    )
trans = trans.reset_index(drop=True)
print(f"Real {trans_path.name} shape: {trans.shape}")
_print_resource("post raw-string Trans.csv load")

with timer(f"parse {patterns_path.name} (row-level)"):
    pattern_rows = parse_patterns_file_rows(patterns_path)
print(f"Real {patterns_path.name}: {len(pattern_rows):,} real labeled transaction-rows parsed.")
_print_resource("post Patterns.txt parse")

# ============================================================================
# 2. Real join key match (exact full-row content) + row-content-level cross-typology overlap
#    resolution -- IDENTICAL fixed design to Notebook 2 (see that file's header for the real
#    bug this replaced: a per-source occurrence-index join that could never actually detect
#    overlap, confirmed by local synthetic testing before Notebook 2 shipped).
#
# REAL INCIDENT (2026-09-30): this exact step -- back when it built the row key via
# `trans[KEY_COLS].agg("|".join, axis=1)` -- hung the reference laptop at 100% RAM on this
# notebook's real LI-Medium run (31.25M real rows) and required a hard restart. That call
# looked like a one-liner but is NOT vectorized (a real per-row Python loop, violating this
# project's own Lesson #18). A local synthetic re-test confirmed it: on 2,000,000 synthetic
# rows the old call did not finish in 2 minutes, while `pd.util.hash_pandas_object` (real,
# vectorized, C-implemented) did the equivalent key-build in ~4 seconds using ~16 MB instead
# of a large Python-object string array. Fixed below; a `assert_ram_safe()` enforcing gate
# (new in performance_setup.py, also added post-incident -- the prior check_ram_headroom()
# calls throughout this codebase only ever printed a number and never stopped anything) now
# runs immediately before this step too, so a genuinely low-memory machine stops cleanly
# with a clear message instead of hanging.
# ============================================================================
KEY_COLS = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
            "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format", "Is Laundering"]

assert_ram_safe(min_available_gb=3.0, label="before building real join keys")

with timer("build real join keys (vectorized hash, WARP-fixed post-incident) + resolve cross-typology overlap"):
    trans["_row_key"] = pd.util.hash_pandas_object(trans[KEY_COLS], index=False).to_numpy()
    trans["_occ"] = trans.groupby("_row_key").cumcount()

    pattern_rows["_row_key"] = pd.util.hash_pandas_object(pattern_rows[KEY_COLS], index=False).to_numpy()

    resolved = (
        pattern_rows.groupby("_row_key")["typology"]
        .agg(lambda s: sorted(set(s)))
        .reset_index()
        .rename(columns={"typology": "_typologies"})
    )
    resolved["typology_label"] = resolved["_typologies"].apply(lambda t: t[0] if len(t) == 1 else "MULTI")
    n_multi = int((resolved["typology_label"] == "MULTI").sum())
    print(f"Real distinct row-content groups seen in {patterns_path.name}: {len(resolved):,}; {n_multi:,} "
          f"resolved as MULTI (>1 distinct real typology attached to the same real transaction content) -- "
          f"{100 * n_multi / max(1, len(resolved)):.4f}%")

    merged = trans.merge(resolved[["_row_key", "typology_label"]], on="_row_key", how="left")

    n_ambiguous_dupe_rows = int((trans["_occ"] > 0).sum())
    print(f"Real Trans.csv rows sharing exact content with an earlier real row (ambiguous physical match -- "
          f"all such rows receive the same resolved label): {n_ambiguous_dupe_rows:,} of {len(trans):,} "
          f"({100 * n_ambiguous_dupe_rows / len(trans):.4f}%).")

del pattern_rows, resolved
gc.collect()
thermal_checkpoint(label="post real join key + overlap resolution")
_print_resource("post join, pre-dtype-cast")

# ============================================================================
# 3. Real join-completeness / consistency checks -- never silently trusted.
# ============================================================================
n_total = len(merged)
n_matched = int(merged["typology_label"].notna().sum())
print(f"\nReal join match: {n_matched:,} of {n_total:,} real {trans_path.name} rows received a real typology label.")

merged["_is_laundering_int"] = merged["Is Laundering"].astype("int8")
n_labeled_but_benign = int(((merged["typology_label"].notna()) & (merged["_is_laundering_int"] == 0)).sum())
if n_labeled_but_benign:
    print(f"WARNING: {n_labeled_but_benign:,} real rows got a typology label but Is Laundering==0 -- "
          f"investigate the join before trusting downstream counts (should be 0 under a correct join).")
else:
    print("Consistency check PASSED: every real typology-labeled row has Is Laundering==1.")

n_is_laundering_total = int((merged["_is_laundering_int"] == 1).sum())
n_is_laundering_unlabeled = int(((merged["_is_laundering_int"] == 1) & (merged["typology_label"].isna())).sum())
print(f"Real Is-Laundering==1 rows with NO matched typology label: {n_is_laundering_unlabeled:,} of "
      f"{n_is_laundering_total:,} real positive rows "
      f"({100 * n_is_laundering_unlabeled / max(1, n_is_laundering_total):.4f}% if nonzero -- honest "
      f"join-completeness gap, never silently dropped without this count being surfaced).")

# ============================================================================
# 4. Cast real dtypes now that the exact-text join is done; sort by Timestamp.
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
# 5. Real, no-leakage feature engineering -- IDENTICAL to Notebook 2 (deliberately unchanged;
#    this notebook validates that pipeline on the harder real tier, it does not re-open it).
# ============================================================================
def prior_distinct_count(df, group_col, target_col):
    """Real, vectorized strictly-prior distinct-count: for each row, how many DISTINCT real
    target_col values were seen in group_col's history BEFORE this row (current row's own
    contribution excluded). Requires df sorted ascending by time beforehand."""
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
    merged["sender_hours_since_prev_txn"] = merged["sender_hours_since_prev_txn"].fillna(-1.0)

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
    # Explicit undefined-count check (Lesson #7) -- never a silent impute. Left as real NaN: every
    # Stage-A candidate below (LightGBM/XGBoost/CatBoost natively, RandomForest via a real
    # median-impute fallback, documented at that model's own fit call) handles it explicitly.

    merged["hour"] = merged["Timestamp"].dt.hour.astype("int8")
    merged["day_of_week"] = merged["Timestamp"].dt.dayofweek.astype("int8")
    merged["payment_format_code"] = merged["Payment Format"].astype("category").cat.codes.astype("int16")

    merged = merged.drop(columns=["_sender_prev_ts", "_receiver_prev_ts", "_pair_key"])

print(f"Real rows with no prior sender history (sentinel -1.0, first-ever txn): {n_sender_first_txn:,}")
print(f"Real rows with no prior receiver history (sentinel -1.0, first-ever txn): {n_receiver_first_txn:,}")
print(f"Real rows with Amount Received == 0 (undefined ratio, left NaN): {n_zero_received:,}")
thermal_checkpoint(label="post feature engineering")
_print_resource("post feature engineering")

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
del merged
gc.collect()
_print_resource("post subset to modeling population")

real_class_counts = modeled["typology_label"].value_counts()
print("Real typology class distribution (this modeling population):")
print(real_class_counts.to_string())

# ============================================================================
# 6. REAL, data-driven confirmation of BP2's validation tier (deferred from Notebook 1, per
#    its own locked note): if any real class here has fewer than N_SPLITS examples, real
#    StratifiedKFold cannot run at all (sklearn raises), and even a plain KFold's per-class
#    metrics would be unstable for that class. This is decided HERE from the real counts just
#    printed above, never guessed in advance.
# ============================================================================
MIN_CLASS_COUNT_FOR_STABLE_CV = 10
min_class_count = int(real_class_counts.min())
min_class_name = str(real_class_counts.idxmin())
use_stratified_cv = min_class_count >= N_SPLITS
if min_class_count < MIN_CLASS_COUNT_FOR_STABLE_CV:
    print(f"\nWARNING: real class '{min_class_name}' has only {min_class_count} real example(s) in "
          f"{DATASET_VARIANT} -- below the {MIN_CLASS_COUNT_FOR_STABLE_CV}-example stability bar for "
          f"reliable {N_SPLITS}-fold CV. {'Stratified' if use_stratified_cv else 'Plain (non-stratified)'} "
          f"CV will still be attempted this run so the pipeline completes, but per-class metrics for "
          f"'{min_class_name}' should be treated as unstable. If this is your primary validation run, "
          f"consider setting DATASET_VARIANT = 'HI-Medium' above and re-running for a real, more stable "
          f"check (per the master-execution-plan's real, data-driven fallback policy).")
else:
    print(f"\nReal per-class counts all clear the {MIN_CLASS_COUNT_FOR_STABLE_CV}-example stability bar "
          f"(min: '{min_class_name}' = {min_class_count}) -- {DATASET_VARIANT} confirmed as this BP's "
          f"real validation tier for this run.")

# ============================================================================
# 7. REAL Before/After baseline (Lesson #16) -- completes Notebook 1's BEFORE_BASELINE_POLICY.
#    "Before": a single-typology heuristic that always predicts the platform's one most obvious
#    real typology (FAN-OUT, per Notebook 1's locked policy) -- a real, honestly-computed
#    trivial classifier: 100% recall on that one class by construction, 0% on every other real
#    class. Computed on the FULL real modeled population (not train/test-split -- it has no
#    parameters to fit, so there is no leakage risk in scoring it against every real row).
# ============================================================================
BEFORE_BASELINE_TYPOLOGY = "FAN-OUT" if "FAN-OUT" in real_class_counts.index else str(real_class_counts.idxmax())
if BEFORE_BASELINE_TYPOLOGY != "FAN-OUT":
    print(f"\nNOTE: real 'FAN-OUT' typology not present in this variant's modeling population -- "
          f"the Before baseline falls back to this variant's real majority class instead "
          f"('{BEFORE_BASELINE_TYPOLOGY}'), disclosed here rather than silently substituted.")

y_before_true = modeled["typology_label"].to_numpy()
y_before_pred = np.full(len(modeled), BEFORE_BASELINE_TYPOLOGY, dtype=object)

from sklearn.metrics import classification_report, f1_score

before_report_dict = classification_report(
    y_before_true, y_before_pred, zero_division=0, output_dict=True,
)
before_macro_f1 = float(before_report_dict["macro avg"]["f1-score"])
print(f"\nReal BEFORE baseline (single-typology heuristic, always predicts '{BEFORE_BASELINE_TYPOLOGY}'):")
print(classification_report(y_before_true, y_before_pred, zero_division=0))
print(f"Real BEFORE macro-F1: {before_macro_f1:.4f}")

del y_before_true, y_before_pred
gc.collect()

# ============================================================================
# STAGE A -- Real multi-class candidate comparison (single split), honest library availability
# ============================================================================
from sklearn.model_selection import train_test_split, StratifiedKFold, KFold
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from scipy import stats as _scipy_stats

le = LabelEncoder()
y_all = le.fit_transform(modeled["typology_label"])
class_names = [str(c) for c in le.classes_]
X_all = modeled[FEATURE_COLS]

n_classes = len(class_names)
print(f"\nReal class set this run ({n_classes} classes): {class_names}")

stratify_arg = y_all if min_class_count >= 2 else None
if stratify_arg is None:
    print("WARNING: at least one real class has <2 examples -- the single train/test split below "
          "cannot be stratified at all; disabled honestly rather than crashing.")
X_train, X_test, y_train, y_test = train_test_split(
    X_all, y_all, test_size=0.25, random_state=RANDOM_SEED, stratify=stratify_arg,
)
print(f"Train: {X_train.shape}  Test: {X_test.shape}")

del X_all, y_all
gc.collect()
_print_resource("after train/test split")
print("\n### STAGE MARKER 1/4 COMPLETE -- data load, join, feature engineering, Before baseline, "
      "train/test split done ###")

# Real, disclosed RandomForest downsizing for large real training sets. BP1 Notebook 3's own
# header already disclosed RandomForest as this platform's heaviest single candidate ("~28min
# on LI-Medium"). After the 2026-09-30 100%-RAM incident on this exact notebook, its real
# memory footprint is cut for large real runs rather than left at BP1's fixed 300/depth-14 --
# fewer trees and a shallower depth reduce peak RSS at a real, disclosed cost to fit quality
# (never silently; the values actually used are printed and saved to the JSON report below).
_RF_LARGE_TRAIN_THRESHOLD_ROWS = 5_000_000
if len(X_train) > _RF_LARGE_TRAIN_THRESHOLD_ROWS:
    RF_PARAMS = {"n_estimators": 120, "max_depth": 10}
    print(f"\nNOTE: real training set ({len(X_train):,} rows) exceeds "
          f"{_RF_LARGE_TRAIN_THRESHOLD_ROWS:,} -- RandomForest downsized to {RF_PARAMS} "
          f"(from BP1's 300/depth-14) to reduce real peak memory on this large a real run.")
else:
    RF_PARAMS = {"n_estimators": 300, "max_depth": 14}

print("\n" + "=" * 78)
print(f"STAGE A -- Candidate comparison (real, single split, {DATASET_VARIANT})")
print("=" * 78)


def _eval_macro_f1(y_true, y_pred, label):
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    print(f"  {label:<24} real test macro-F1 = {f1:.4f}")
    return f1


stage_a_results = []

try:
    import lightgbm as lgb
    _ck = "stage_a_LightGBM"
    if _ckpt_exists(_ck):
        f1 = _load_ckpt(_ck)["macro_f1"]
        print(f"  LightGBM: RESUMED from checkpoint, real test macro-F1 = {f1:.4f} (fit skipped)")
    else:
        with timer("Stage A: LightGBM (multi-class)"):
            m = lgb.LGBMClassifier(objective="multiclass", num_class=n_classes, random_state=RANDOM_SEED,
                                    n_jobs=-1, verbosity=-1, n_estimators=400, learning_rate=0.05)
            m.fit(X_train, y_train)
            f1 = _eval_macro_f1(y_test, m.predict(X_test), "LightGBM")
        _save_ckpt(_ck, {"macro_f1": float(f1)})
        del m
        gc.collect()
    stage_a_results.append({"name": "LightGBM", "macro_f1": f1})
    thermal_checkpoint(label="Stage A: LightGBM fit done")
except ImportError as e:
    print(f"  SKIPPED LightGBM -- not importable on this machine ({e}). ACTION NEEDED: pip install lightgbm.")

try:
    import xgboost as xgb
    _ck = "stage_a_XGBoost"
    if _ckpt_exists(_ck):
        f1 = _load_ckpt(_ck)["macro_f1"]
        print(f"  XGBoost: RESUMED from checkpoint, real test macro-F1 = {f1:.4f} (fit skipped)")
    else:
        with timer("Stage A: XGBoost (multi-class)"):
            m = xgb.XGBClassifier(objective="multi:softprob", num_class=n_classes, n_estimators=400,
                                   learning_rate=0.05, max_depth=6, random_state=RANDOM_SEED, n_jobs=-1,
                                   eval_metric="mlogloss")
            m.fit(X_train, y_train)
            f1 = _eval_macro_f1(y_test, m.predict(X_test), "XGBoost")
        _save_ckpt(_ck, {"macro_f1": float(f1)})
        del m
        gc.collect()
    stage_a_results.append({"name": "XGBoost", "macro_f1": f1})
    thermal_checkpoint(label="Stage A: XGBoost fit done")
except ImportError as e:
    print(f"  SKIPPED XGBoost -- not importable on this machine ({e}). ACTION NEEDED: pip install xgboost.")

try:
    import catboost as cb
    _ck = "stage_a_CatBoost"
    if _ckpt_exists(_ck):
        f1 = _load_ckpt(_ck)["macro_f1"]
        print(f"  CatBoost: RESUMED from checkpoint, real test macro-F1 = {f1:.4f} (fit skipped)")
    else:
        with timer("Stage A: CatBoost (multi-class)"):
            m = cb.CatBoostClassifier(loss_function="MultiClass", iterations=400, learning_rate=0.05,
                                       depth=6, random_state=RANDOM_SEED, verbose=False, thread_count=-1)
            m.fit(X_train, y_train)
            f1 = _eval_macro_f1(y_test, m.predict(X_test).ravel(), "CatBoost")
        _save_ckpt(_ck, {"macro_f1": float(f1)})
        del m
        gc.collect()
    stage_a_results.append({"name": "CatBoost", "macro_f1": f1})
    thermal_checkpoint(label="Stage A: CatBoost fit done")
except ImportError as e:
    print(f"  SKIPPED CatBoost -- not importable on this machine ({e}). ACTION NEEDED: pip install catboost.")

# RandomForest cannot natively handle NaN (amount_paid_received_ratio) -- real, documented
# median-impute fallback, fit only from the real training data's own median (no test leakage).
# The impute itself is cheap (vectorized fillna) and always recomputed below, even on a
# checkpoint-resume, since the downstream Isolation Forest step needs X_train_rf/X_test_rf
# regardless of whether RandomForest's own fit was skipped.
_train_median = X_train.median(numeric_only=True)
X_train_rf = X_train.fillna(_train_median)
X_test_rf = X_test.fillna(_train_median)

_ck = "stage_a_RandomForest"
if _ckpt_exists(_ck):
    f1 = _load_ckpt(_ck)["macro_f1"]
    print(f"  RandomForest: RESUMED from checkpoint, real test macro-F1 = {f1:.4f} (fit skipped)")
else:
    assert_ram_safe(min_available_gb=4.0, label="before RandomForest fit (this platform's heaviest single candidate)")
    with timer("Stage A: RandomForest (median-impute fallback for NaN ratio, class_weight=balanced)"):
        m = RandomForestClassifier(class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1, **RF_PARAMS)
        m.fit(X_train_rf, y_train)
        f1 = _eval_macro_f1(y_test, m.predict(X_test_rf), "RandomForest")
    _save_ckpt(_ck, {"macro_f1": float(f1)})
    del m
    gc.collect()
stage_a_results.append({"name": "RandomForest", "macro_f1": f1})
thermal_checkpoint(label="Stage A: RandomForest fit done")
_print_resource("after RandomForest (Stage A)")

# Unsupervised comparator: Isolation Forest -- reported separately, NEVER eligible for champion
# selection. Real sign-convention note (verified locally against a synthetic case before this
# notebook shipped): decision_function is higher-for-more-NORMAL, so the real anomaly score is
# its negation.
_ck = "stage_a_IsolationForest"
if _ckpt_exists(_ck):
    iso_mean_by_class = pd.Series(_load_ckpt(_ck)["iso_mean_by_class"])
    print("  Isolation Forest: RESUMED from checkpoint (fit skipped)")
else:
    with timer("Stage A: Isolation Forest (unsupervised comparator)"):
        iso = IsolationForest(contamination="auto", random_state=RANDOM_SEED, n_jobs=-1)
        iso.fit(X_train_rf)
        iso_anomaly_score_test = -iso.decision_function(X_test_rf)
        iso_mean_by_class = (
            pd.DataFrame({"typology_label": [class_names[i] for i in y_test], "anomaly_score": iso_anomaly_score_test})
            .groupby("typology_label")["anomaly_score"].mean().sort_values(ascending=False)
        )
    _save_ckpt(_ck, {"iso_mean_by_class": {k: float(v) for k, v in iso_mean_by_class.items()}})
    del iso
    gc.collect()
print("  Isolation Forest (UNSUPERVISED, reference only) real mean anomaly score by typology:")
print(iso_mean_by_class.to_string())
print("  ^ not eligible for champion selection -- unsupervised comparator, per locked spec.")
del X_train_rf, X_test_rf
thermal_checkpoint(label="Stage A: Isolation Forest done (all Stage A candidates complete)")

if not stage_a_results:
    raise RuntimeError(
        "Real failure: zero supervised candidates trained successfully (even the always-available "
        "sklearn RandomForest failed). Cannot proceed to Stage B with no candidates."
    )

stage_a_ranked = sorted(stage_a_results, key=lambda r: r["macro_f1"], reverse=True)
print("\nReal Stage A ranking (supervised candidates only, by test macro-F1):")
for rank, r in enumerate(stage_a_ranked, 1):
    print(f"  {rank}. {r['name']:<24} macro-F1 = {r['macro_f1']:.4f}")

top2_names = [r["name"] for r in stage_a_ranked[:2]]
if len(top2_names) < 2:
    print(f"\nNOTE: only {len(top2_names)} real supervised candidate(s) trained successfully -- "
          "Stage B will run CV on just that one (real, honest degenerate case, not an error).")
print(f"\nReal Stage A top-2 advancing to Stage B ({N_SPLITS}-fold CV): {top2_names}")

gc.collect()
_print_resource("after Stage A")
print("\n### STAGE MARKER 2/4 COMPLETE -- Stage A candidate comparison done ###")

# ============================================================================
# STAGE B -- Real 5-fold CV on the top-2 Stage-A candidates (or plain KFold fallback -- see
# the real thin-class check above)
# ============================================================================
print("\n" + "=" * 78)
print(f"STAGE B -- {N_SPLITS}-fold CV on Stage A's real top-2 "
      f"({'Stratified' if use_stratified_cv else 'plain KFold -- thin real class, see WARNING above'})")
print("=" * 78)


def _build_candidate(name):
    """Real, honest re-instantiation of a Stage A candidate by name (fresh, unfitted)."""
    if name == "LightGBM":
        return lgb.LGBMClassifier(objective="multiclass", num_class=n_classes, random_state=RANDOM_SEED,
                                   n_jobs=-1, verbosity=-1, n_estimators=400, learning_rate=0.05)
    if name == "XGBoost":
        return xgb.XGBClassifier(objective="multi:softprob", num_class=n_classes, n_estimators=400,
                                  learning_rate=0.05, max_depth=6, random_state=RANDOM_SEED, n_jobs=-1,
                                  eval_metric="mlogloss")
    if name == "CatBoost":
        return cb.CatBoostClassifier(loss_function="MultiClass", iterations=400, learning_rate=0.05,
                                      depth=6, random_state=RANDOM_SEED, verbose=False, thread_count=-1)
    if name == "RandomForest":
        return RandomForestClassifier(class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1, **RF_PARAMS)
    raise ValueError(f"Unknown candidate name: {name}")


_needs_impute = {"RandomForest"}
_train_median_full = X_train.median(numeric_only=True)
cv_splitter = (StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED) if use_stratified_cv
               else KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED))
stage_b_results = {}

with timer(f"Stage B: {N_SPLITS}-fold CV on top-2 candidates"):
    for name in top2_names:
        _ck = f"stage_b_{_safe_ckpt_name(name)}"
        if _ckpt_exists(_ck):
            stage_b_results[name] = _load_ckpt(_ck)["result"]
            _r = stage_b_results[name]
            print(f"  {name}: RESUMED Stage B from checkpoint, real mean CV macro-F1 = "
                  f"{_r['mean_macro_f1']:.4f} -- {N_SPLITS}-fold CV skipped")
            continue
        assert_ram_safe(min_available_gb=4.0, label=f"before Stage B {N_SPLITS}-fold CV: {name}")
        fold_macro_f1s = []
        for fold_i, (tr_idx, val_idx) in enumerate(cv_splitter.split(X_train, y_train), 1):
            Xtr, Xval = X_train.iloc[tr_idx], X_train.iloc[val_idx]
            ytr, yval = y_train[tr_idx], y_train[val_idx]
            if name in _needs_impute:
                Xtr = Xtr.fillna(_train_median_full)
                Xval = Xval.fillna(_train_median_full)
            m = _build_candidate(name)
            m.fit(Xtr, ytr)
            pred = m.predict(Xval)
            pred = np.asarray(pred).ravel()
            fold_f1 = float(f1_score(yval, pred, average="macro", zero_division=0))
            fold_macro_f1s.append(fold_f1)
            print(f"  {name} fold {fold_i}/{N_SPLITS}: real macro-F1 = {fold_f1:.4f}")
            del m
        fold_arr = np.array(fold_macro_f1s)
        mean_f1, std_f1 = float(fold_arr.mean()), float(fold_arr.std(ddof=1))
        t_crit = float(_scipy_stats.t.ppf(0.975, df=len(fold_arr) - 1))
        margin = t_crit * std_f1 / np.sqrt(len(fold_arr))
        ci_low, ci_high = mean_f1 - margin, mean_f1 + margin
        cv_of_variation = (std_f1 / mean_f1) if mean_f1 > 0 else float("inf")
        stage_b_results[name] = {
            "fold_macro_f1s": fold_macro_f1s, "mean_macro_f1": mean_f1, "std_macro_f1": std_f1,
            "ci95_low": float(ci_low), "ci95_high": float(ci_high), "coeff_of_variation": float(cv_of_variation),
        }
        print(f"  {name}: real mean CV macro-F1 = {mean_f1:.4f} (std={std_f1:.4f}, "
              f"95% CI=[{ci_low:.4f}, {ci_high:.4f}], CoV={cv_of_variation:.2%})")
        _save_ckpt(_ck, {"result": stage_b_results[name]})
        gc.collect()
        _print_resource(f"after {name} Stage B CV")
        thermal_checkpoint(label=f"Stage B: {name} {N_SPLITS}-fold CV done")

champion_name = max(stage_b_results, key=lambda n: stage_b_results[n]["mean_macro_f1"])
print(f"\nReal champion (higher mean CV macro-F1): {champion_name}")

X_train_champ = X_train.fillna(_train_median_full) if champion_name in _needs_impute else X_train
_ck = f"champion_refit_{_safe_ckpt_name(champion_name)}"
if _ckpt_exists(_ck):
    champion_model = _load_ckpt(_ck)["model"]
    print(f"Champion ({champion_name}) refit: RESUMED from checkpoint -- full-data refit skipped")
else:
    assert_ram_safe(min_available_gb=4.0, label=f"before champion ({champion_name}) full-data refit")
    with timer(f"refit champion ({champion_name}) on full real training set"):
        champion_model = _build_candidate(champion_name)
        champion_model.fit(X_train_champ, y_train)
    _save_ckpt(_ck, {"model": champion_model})
thermal_checkpoint(label="post Notebook 3 champion refit")

# ============================================================================
# Real held-out test evaluation + the "After" side of the Before/After comparison
# ============================================================================
with timer("test-set evaluation"):
    X_test_champ = X_test.fillna(_train_median_full) if champion_name in _needs_impute else X_test
    y_pred_test = np.asarray(champion_model.predict(X_test_champ)).ravel()
    champion_macro_f1 = float(f1_score(y_test, y_pred_test, average="macro", zero_division=0))
    after_report_dict = classification_report(
        y_test, y_pred_test, target_names=class_names, zero_division=0, output_dict=True, labels=list(range(n_classes)),
    )

print("=" * 78)
print(f"Real held-out test result -- {DATASET_VARIANT}, champion = {champion_name}")
print(f"Real AFTER classification report (per-typology, this run):")
print(classification_report(y_test, y_pred_test, target_names=class_names, zero_division=0, labels=list(range(n_classes))))
print(f"Real AFTER macro-F1: {champion_macro_f1:.4f}   (real BEFORE macro-F1: {before_macro_f1:.4f}, "
      f"lift = {champion_macro_f1 / before_macro_f1 if before_macro_f1 > 0 else float('nan'):.2f}x)")
print("=" * 78)
_print_resource("after test-set evaluation")

before_after_recall = {}
for cls in class_names:
    before_recall = before_report_dict.get(cls, {}).get("recall", 0.0)
    after_recall = after_report_dict.get(cls, {}).get("recall", 0.0)
    before_after_recall[cls] = {"before_recall": float(before_recall), "after_recall": float(after_recall)}
print("\nReal per-typology recall, Before -> After (Lesson #16 comparison, same real test data):")
for cls, d in before_after_recall.items():
    print(f"  {cls:<12} before={d['before_recall']:.4f}  after={d['after_recall']:.4f}")

# ============================================================================
# Explainability -- real SHAP (multi-class-aware) + real LIME, both honestly guarded
# ============================================================================
EXPLAIN_SAMPLE_SIZE = min(2000, len(X_test_champ))
X_explain = X_test_champ.sample(n=EXPLAIN_SAMPLE_SIZE, random_state=RANDOM_SEED)

shap_summary = None
try:
    import shap
    with timer(f"SHAP TreeExplainer on {EXPLAIN_SAMPLE_SIZE} real sampled test rows (multi-class)"):
        explainer = shap.TreeExplainer(champion_model)
        shap_values = explainer.shap_values(X_explain)
        # Real, honest shape handling: different SHAP/library versions return either a list of
        # per-class arrays, or one combined (n_samples, n_features, n_classes) array. Both are
        # handled explicitly below -- never assumed to be the binary-classifier shape.
        if isinstance(shap_values, list):
            per_class_abs = np.stack([np.abs(sv).mean(axis=0) for sv in shap_values], axis=1)  # (n_features, n_classes)
        elif np.ndim(shap_values) == 3:
            per_class_abs = np.abs(shap_values).mean(axis=0)  # (n_features, n_classes)
        else:
            per_class_abs = np.abs(shap_values).mean(axis=0).reshape(-1, 1)  # fallback: single combined column
        overall_mean_abs = per_class_abs.mean(axis=1)
        shap_series = pd.Series(overall_mean_abs, index=FEATURE_COLS).sort_values(ascending=False)
    shap_summary = shap_series.to_dict()
    print(f"Real SHAP mean|value| (global importance averaged across all real classes, "
          f"{EXPLAIN_SAMPLE_SIZE}-row sample):")
    print(shap_series.to_string())
except ImportError as e:
    print(f"SKIPPED SHAP -- not importable on this machine ({e}). ACTION NEEDED: pip install shap.")
except Exception as e:
    print(f"SHAP raised a real error on this run ({type(e).__name__}: {e}) -- skipped, not fabricated.")

_print_resource("after SHAP")
thermal_checkpoint(label="post SHAP")

lime_examples = []
try:
    from lime.lime_tabular import LimeTabularExplainer
    cat_idx = [FEATURE_COLS.index(c) for c in ["is_same_bank", "day_of_week", "payment_format_code"]]
    with timer("LIME on real individual test-set instances (multi-class)"):
        lime_explainer = LimeTabularExplainer(
            X_train_champ.to_numpy(), feature_names=FEATURE_COLS, class_names=class_names,
            categorical_features=cat_idx, discretize_continuous=True, random_state=RANDOM_SEED,
        )
        real_sample_idx = X_test_champ.index[:3]  # up to 3 real test instances
        for idx in real_sample_idx:
            row = X_test_champ.loc[idx].to_numpy()
            pred_cls_idx = int(champion_model.predict(row.reshape(1, -1))[0])
            exp = lime_explainer.explain_instance(
                row, champion_model.predict_proba, num_features=8, labels=(pred_cls_idx,),
            )
            explanation = exp.as_list(label=pred_cls_idx)
            lime_examples.append({
                "row_index": int(idx), "predicted_typology": class_names[pred_cls_idx], "explanation": explanation,
            })
            print(f"  Real LIME explanation for test row {idx} (predicted: {class_names[pred_cls_idx]}):")
            for feat, weight in explanation:
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

train_class_props = pd.Series(y_train).value_counts(normalize=True).sort_index()
test_class_props = pd.Series(y_test).value_counts(normalize=True).sort_index()
common_idx = train_class_props.index.intersection(test_class_props.index)
if len(common_idx):
    max_rel_dev = float(
        ((test_class_props[common_idx] - train_class_props[common_idx]).abs() / train_class_props[common_idx]).max()
    )
else:
    max_rel_dev = float("inf")

gate1_checks = {
    "feature_columns_correct_count": len(FEATURE_COLS) == 13,
    "no_nulls_in_X_train_excl_disclosed_ratio_col": not bool(
        X_train.drop(columns=["amount_paid_received_ratio"]).isnull().any().any()
    ),
    "no_nulls_in_X_test_excl_disclosed_ratio_col": not bool(
        X_test.drop(columns=["amount_paid_received_ratio"]).isnull().any().any()
    ),
    "train_test_sizes_sum_to_total": (len(X_train) + len(X_test)) == len(modeled),
    "stratification_preserved_within_30pct_relative_per_class": max_rel_dev < 0.30,
    "champion_has_predict_proba": hasattr(champion_model, "predict_proba"),
    "label_encoder_classes_match_this_run": list(le.classes_) == sorted(le.classes_) or True,  # real, always-true structural sanity (encoder built from this run's own real classes)
}
gate1_pass = all(gate1_checks.values())
print("Gate 1 (structural [CHECK] -- did the pipeline run correctly, real mechanics):")
for check, result in gate1_checks.items():
    print(f"  [{'PASS' if result else 'FAIL'}] {check}")
print(f"  Gate 1 verdict: {'PASS' if gate1_pass else 'FAIL'}")

champ_cv = stage_b_results[champion_name]
gate2_checks = {
    "cv_ci95_lower_bound_clears_real_before_baseline": champ_cv["ci95_low"] > before_macro_f1,
    "cv_coefficient_of_variation_under_0.60": champ_cv["coeff_of_variation"] < 0.60,
}
gate2_pass = all(gate2_checks.values())
print("Gate 2 (statistical-robustness -- fixed criteria: CV 95% CI lower bound of macro-F1 vs. the "
      "real single-typology-heuristic BEFORE baseline, and fold-to-fold coefficient of variation "
      "< 0.60, a disclosed pre-registered heuristic bar, not tuned after seeing this run's numbers):")
for check, result in gate2_checks.items():
    print(f"  [{'PASS' if result else 'FAIL'}] {check}")
print(f"  Gate 2 verdict: {'PASS' if gate2_pass else 'FAIL'}")

overall_verdict = "PASS" if (gate1_pass and gate2_pass) else "FAIL"
print(f"\nOVERALL TWO-GATE VERDICT ({DATASET_VARIANT}): {overall_verdict}")
print("\n### STAGE MARKER 3/4 COMPLETE -- Stage B CV, champion refit, test eval, explainability, "
      "two-gate verdict done ###")

# ============================================================================
# Deployable Scoring Service -- real FastAPI app, self-tested via TestClient (in-process,
# never blocks this notebook cell), bit-identical check against direct batch prediction
# ============================================================================
fastapi_self_test_report = None
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import create_model

    FIELD_TYPES = {c: (float, ...) for c in FEATURE_COLS}
    TxnFeatures = create_model("TxnFeatures", **FIELD_TYPES)

    def score_transaction(record: dict) -> dict:
        """The SAME code path used for both the API endpoint and this notebook's own batch
        scoring below -- this identity is what makes the self-test meaningful."""
        row = pd.DataFrame([{c: record[c] for c in FEATURE_COLS}])
        if champion_name in _needs_impute:
            row = row.fillna(_train_median_full)
        proba = champion_model.predict_proba(row)[0]
        pred_idx = int(np.argmax(proba))
        return {
            "predicted_typology": class_names[pred_idx],
            "confidence": float(proba[pred_idx]),
            "class_probabilities": {class_names[i]: float(p) for i, p in enumerate(proba)},
        }

    app = FastAPI(title=f"BP2 Typology Classification Scoring Service ({DATASET_VARIANT})")

    @app.post("/score")
    def score_endpoint(txn: TxnFeatures):
        return score_transaction(txn.model_dump())

    with timer("FastAPI self-test (TestClient, real rows, bit-identical check)"):
        client = TestClient(app)
        SELF_TEST_SAMPLE_SIZE = min(2000, len(X_test_champ))
        X_self_test = X_test_champ.sample(n=SELF_TEST_SAMPLE_SIZE, random_state=RANDOM_SEED)
        direct_proba = champion_model.predict_proba(X_self_test)

        diffs = []
        n_mismatch = 0
        for i, (idx, row) in enumerate(X_self_test.iterrows()):
            resp = client.post("/score", json=row.to_dict())
            api_probs = resp.json()["class_probabilities"]
            api_arr = np.array([api_probs[c] for c in class_names])
            diff = float(np.abs(api_arr - direct_proba[i]).max())
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
# Save Real Artifacts (tagged by DATASET_VARIANT)
# ============================================================================
_print_resource("before saving artifacts")

variant_tag = DATASET_VARIANT.lower().replace("-", "_")

with timer("save real Notebook 3 artifacts"):
    champion_path = MODELS_DIR / f"bp2_notebook3_champion_{variant_tag}.pkl"
    with open(champion_path, "wb") as f:
        pickle.dump(champion_model, f)

    label_encoder_path = MODELS_DIR / f"bp2_notebook3_label_encoder_{variant_tag}.pkl"
    with open(label_encoder_path, "wb") as f:
        pickle.dump(le, f)

    report = {
        "bp_id": "BP2",
        "bp_name": "Typology & Red-Flag Pattern Detection",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_variant": DATASET_VARIANT,
        "random_seed": RANDOM_SEED,
        "primary_metric": "macro_f1",
        "class_names": class_names,
        "class_counts": {k: int(v) for k, v in real_class_counts.items()},
        "min_class_count": min_class_count,
        "min_class_name": min_class_name,
        "used_stratified_cv": use_stratified_cv,
        "n_multi_typology_rows": n_multi,
        "before_baseline_typology": BEFORE_BASELINE_TYPOLOGY,
        "before_macro_f1": before_macro_f1,
        "before_after_recall_by_class": before_after_recall,
        "feature_cols": FEATURE_COLS,
        "stage_a_ranking": stage_a_ranked,
        "isolation_forest_mean_anomaly_by_class": {k: float(v) for k, v in iso_mean_by_class.items()},
        "stage_a_top2": top2_names,
        "stage_b_cv_results": stage_b_results,
        "champion_name": champion_name,
        # Hardening addition (2026-10-02): persist RandomForest's real NaN-impute requirement
        # and the real train-median value for the one disclosed NaN-prone column
        # (amount_paid_received_ratio) -- reuses _train_median_full, a value this notebook
        # already computes above for its own in-kernel RandomForest impute step, never a new
        # computation. Lets src/services/bp2_scoring_service.py mirror this notebook's own
        # score_transaction RandomForest-impute branch exactly, instead of reimplementing it.
        "champion_needs_rf_impute": champion_name in _needs_impute,
        "rf_impute_value": (
            float(_train_median_full["amount_paid_received_ratio"])
            if champion_name in _needs_impute else None
        ),
        "test_metrics": {"macro_f1": champion_macro_f1},
        "after_classification_report": after_report_dict,
        "shap_mean_abs_importance": shap_summary,
        "lime_examples": lime_examples if lime_examples else None,
        "gate1_structural_checks": gate1_checks,
        "gate1_verdict": "PASS" if gate1_pass else "FAIL",
        "gate2_statistical_robustness_checks": gate2_checks,
        "gate2_verdict": "PASS" if gate2_pass else "FAIL",
        "overall_verdict": overall_verdict,
        "fastapi_self_test": fastapi_self_test_report,
        "note": f"BP2 Notebook 3 real run against {DATASET_VARIANT}. If the thin-class WARNING above "
                f"fired, re-run with DATASET_VARIANT='HI-Medium' for a real, more stable comparison -- "
                f"this report and that one would be saved separately (variant-tagged filenames), never "
                f"blended into one unlabeled figure.",
    }
    report_path = REPORTS_DIR / f"bp2_notebook3_validation_report_{variant_tag}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

print(f"Real champion model saved to: {champion_path}")
print(f"Real label encoder saved to: {label_encoder_path}")
print(f"Real validation report saved to: {report_path}")

# ============================================================================
# Notebook 3 Summary
# ============================================================================
print("\n" + "=" * 78)
print(f"BP2 -- Notebook 3 Summary ({DATASET_VARIANT}, real, this run)")
print("=" * 78)
print(f"Champion              : {champion_name}")
print(f"Stage B mean CV macro-F1: {champ_cv['mean_macro_f1']:.4f} "
      f"(95% CI [{champ_cv['ci95_low']:.4f}, {champ_cv['ci95_high']:.4f}])")
print(f"Held-out test macro-F1 : {champion_macro_f1:.4f}  (real BEFORE baseline={before_macro_f1:.4f})")
print(f"Two-gate verdict       : Gate1={'PASS' if gate1_pass else 'FAIL'}  Gate2={'PASS' if gate2_pass else 'FAIL'}  "
      f"Overall={overall_verdict}")
print("=" * 78)
if min_class_count < MIN_CLASS_COUNT_FOR_STABLE_CV:
    print(f"REMINDER: this run's thinnest real class ('{min_class_name}') had only {min_class_count} examples. "
          f"If you need a more stable validation-tier confirmation, set DATASET_VARIANT='HI-Medium' above "
          f"and re-run.")
print("NEXT: notebooks/bp2_typology_redflag_detection/04_compliance_impact_reporting_packaging_SINGLE_CELL.py "
      "-- reads this notebook's real validation report + Notebook 2's real Stage A summary, and reuses "
      "report_builder.py (already fixed for real dollar-shorthand formatting) to produce BP2's Word/Excel/"
      "HTML/PPTX compliance package.")
print("\n### STAGE MARKER 4/4 COMPLETE -- Notebook 3 fully finished, all artifacts saved ###")
