# ============================================================================
# BP2 NOTEBOOK 1 -- Business Understanding & Typology Policy (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # BP2 — Notebook 1: Business Understanding & Typology Policy
# ## Typology & Red-Flag Pattern Detection
#
# **Real-world grounding (verified against primary sources, not paraphrased AML-textbook language):**
# - FinCEN civil money penalty assessment, JPMorgan Chase (re: the Madoff/Bernard L. Madoff Investment
#   Securities case) — real use of the term *"red flags"* for typology indicators, the same term FinCEN's own
#   AML guidance uses for structural laundering patterns.
# - FATF 40 Recommendations — the international standard-setting body whose typology taxonomy this BP's eight
#   labeled patterns are a synthetic instance of.
#
# **Target:** a real, direct multi-class typology label -- **not** `Is Laundering` (BP1's binary target). This
# BP's ground truth is `*_Patterns.txt`: real block-structured labels, one of eight typologies per labeled
# laundering attempt -- **FAN-OUT, FAN-IN, GATHER-SCATTER, SCATTER-GATHER, CYCLE, BIPARTITE, STACK, RANDOM**
# (per `claude/master-execution-plan.md` Section 3, cross-checked against the real file content parsed below --
# not assumed from the source paper's abstract description).
# **Task framing:** multi-class typology classification (locked, Section 3 of the master plan).
# **Primary metric (this notebook's own policy decision, justified below in Section 5, then written back to
# `configs/bp2_typology_redflag_detection.yaml`):** macro-averaged F1 across the 8 typologies -- not PR-AUC
# (BP1's binary metric, currently a stale placeholder in that same config file, corrected here for real).
#
# **Regulatory hooks this BP evidences (not a compliance determination — evidence/detection only):**
# FinCEN SAR filing requirements (31 CFR §1020.320) — this BP's typology-level detections are evidence that
# could *feed* a SAR narrative, never itself a SAR-filed/not-filed prediction (no such independent label exists
# in this dataset, same constraint as BP1); FATF 40 Recommendations — the typology taxonomy itself.
#
# **Scope of this notebook:** business framing + real exploratory data analysis on **HI-Small and LI-Small side
# by side** (per the locked multi-variant dataset strategy, Section 2.1 of the master plan) — no modeling here.
# Per Section 3's per-BP validation-tier table, BP2's mandatory realism-validation tier is **LI-Medium (or
# HI-Medium if typology counts prove too thin at LI-Medium scale)** — that call is deferred to Notebook 3 once
# real Medium-scale typology counts exist; this notebook's HI-Small/LI-Small counts (Section 3 below) are an
# early real read, not the final decision.
#
# **Zero-fabrication rule for this notebook:** every count, ratio, and distribution below is computed live from
# the real files in `data/raw/` when this notebook runs. No figure is pre-typed into markdown as if already
# known — if a number appears in a markdown cell, it is because the code cell immediately above computed it.

import sys
from pathlib import Path

def _locate_project_root():
    # 1. Walk upward from cwd looking for the locked-structure marker.
    cur = Path.cwd()
    for _ in range(8):
        if (cur / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    # 2. Fallback: the real, confirmed on-device location (2026-09-29).
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

# WARP STEP 1 — before any heavy import below.
perf_config = configure_performance()
print("WARP configured:", perf_config)

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
CONFIG_PATH = PROJECT_ROOT / "configs" / "bp2_typology_redflag_detection.yaml"
print(f"Project root: {PROJECT_ROOT}")
print(f"Raw data dir: {RAW}")
print(f"Config path : {CONFIG_PATH}")

import pandas as pd
import numpy as np
import re

print(f"pandas {pd.__version__}, numpy {np.__version__}")

# Real dtype hints, identical raw schema to BP1 (same underlying dataset, shared data/raw/):
# Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,
# Amount Paid,Payment Currency,Payment Format,Is Laundering
TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}

# ## 1. Load HI-Small and LI-Small Side by Side
# Same raw files BP1 already loads (data/raw/ is shared platform-wide, not per-BP) — reused here via the
# project's own Parquet cache (WARP: load_csv_cached), so this is fast even on first run of this notebook.

with timer("load HI-Small_Trans.csv (WARP: cached to Parquet)"):
    hi_small = load_csv_cached(RAW / "HI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"HI-Small_Trans.csv real shape: {hi_small.shape}")

with timer("load LI-Small_Trans.csv (WARP: cached to Parquet)"):
    li_small = load_csv_cached(RAW / "LI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"LI-Small_Trans.csv real shape: {li_small.shape}")

# ## 2. Real Class Imbalance Context (`Is Laundering`) -- Background Only
# BP2's real target is the typology label (Section 3), not `Is Laundering` -- but the real Is-Laundering==1
# count is still the real upper bound on how many transaction-rows the typology labels below can possibly
# cover, so it is computed here as context, not as this BP's target.

def imbalance_report(df, label):
    n_total = len(df)
    n_positive = int(df["Is Laundering"].sum())
    ratio_pct = 100 * n_positive / n_total
    print(f"{label}: {n_total:,} total txns, {n_positive:,} Is-Laundering==1 ({ratio_pct:.4f}%)")
    return {"total": n_total, "positive": n_positive, "ratio_pct": ratio_pct}

imbalance_hi = imbalance_report(hi_small, "HI-Small (real, this run)")
imbalance_li = imbalance_report(li_small, "LI-Small (real, this run)")

# ## 3. Real Typology Ground Truth -- Row-Level Parse of `*_Patterns.txt`
# `*_Patterns.txt` labels each laundering transaction with one of eight typologies via
# `BEGIN LAUNDERING ATTEMPT - <TYPOLOGY>: <description>` / `END LAUNDERING ATTEMPT - <TYPOLOGY>` blocks. Unlike
# BP1 Notebook 1 (which only counted rows per block), this BP's own ground truth REQUIRES each real row's actual
# field content -- because the eventual per-transaction typology label (built for real in Notebook 2) has to be
# joined back to `*_Trans.csv`, and because Section 4 below checks real cross-typology overlap at the row level,
# not just the block level.

def parse_patterns_file_rows(path):
    """Real row-level parser for *_Patterns.txt: returns one row per real labeled transaction, tagged with its
    real pattern_id and typology, plus its own real field values (same 11-column schema as *_Trans.csv, no
    header inside the block). Malformed lines (wrong real field count) are counted and reported, never
    silently padded/truncated or dropped without being surfaced."""
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

with timer("parse HI-Small_Patterns.txt (row-level)"):
    hi_pattern_rows = parse_patterns_file_rows(RAW / "HI-Small_Patterns.txt")
with timer("parse LI-Small_Patterns.txt (row-level)"):
    li_pattern_rows = parse_patterns_file_rows(RAW / "LI-Small_Patterns.txt")

print(f"\nHI-Small: {len(hi_pattern_rows):,} real labeled transaction-rows parsed, "
      f"{hi_pattern_rows['pattern_id'].nunique()} real labeled attempts")
print(f"LI-Small: {len(li_pattern_rows):,} real labeled transaction-rows parsed, "
      f"{li_pattern_rows['pattern_id'].nunique()} real labeled attempts")

print("\nHI-Small real typology distribution (transaction-ROW count, this run):")
print(hi_pattern_rows["typology"].value_counts().to_string())
print("\nLI-Small real typology distribution (transaction-ROW count, this run):")
print(li_pattern_rows["typology"].value_counts().to_string())

n_typologies_hi = hi_pattern_rows["typology"].nunique()
n_typologies_li = li_pattern_rows["typology"].nunique()
print(f"\nDistinct real typologies observed: HI-Small={n_typologies_hi}, LI-Small={n_typologies_li} "
      f"(master-plan Section 3 expects 8 -- {'MATCHES' if n_typologies_hi == 8 else 'DIFFERS, investigate'} "
      f"for HI-Small).")

# ## 4. Real Cross-Typology Overlap Check -- the Key Open Policy Question for Notebook 2
# A single real transaction-row can legitimately appear inside more than one BEGIN/END block (e.g. a hub
# account's transfer is simultaneously part of a FAN-IN attempt and a downstream STACK attempt). This is
# computed here directly from the real row content parsed above -- never assumed -- because it determines
# whether Notebook 2 can build a clean multi-CLASS target (one typology per row) or must instead treat
# multi-typology rows as their own explicit category / a multi-LABEL problem. This notebook does not silently
# pick one; it reports the real measured overlap and states the resulting policy below.

ROW_KEY_COLS = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
                 "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format"]

def overlap_report(pattern_rows_df, label):
    keyed = pattern_rows_df.copy()
    keyed["row_key"] = keyed[ROW_KEY_COLS].astype(str).agg("|".join, axis=1)
    typologies_per_key = keyed.groupby("row_key")["typology"].nunique()
    n_unique_rows = int(len(typologies_per_key))
    n_multi = int((typologies_per_key > 1).sum())
    pct_multi = 100 * n_multi / n_unique_rows if n_unique_rows else float("nan")
    print(f"{label}: {n_unique_rows:,} real distinct transaction-rows across all labeled attempts, "
          f"{n_multi:,} ({pct_multi:.4f}%) appear in MORE THAN ONE typology block.")
    return {"n_unique_rows": n_unique_rows, "n_multi": n_multi, "pct_multi": pct_multi}

overlap_hi = overlap_report(hi_pattern_rows, "HI-Small (real, this run)")
overlap_li = overlap_report(li_pattern_rows, "LI-Small (real, this run)")

MULTI_TYPOLOGY_POLICY_THRESHOLD_PCT = 1.0  # a real, disclosed policy threshold set here, not tuned post-hoc
if max(overlap_hi["pct_multi"], overlap_li["pct_multi"]) < MULTI_TYPOLOGY_POLICY_THRESHOLD_PCT:
    TYPOLOGY_LABEL_POLICY = (
        f"Real cross-typology overlap is under {MULTI_TYPOLOGY_POLICY_THRESHOLD_PCT}% on both variants -- "
        f"Notebook 2 will build a clean multi-CLASS target (single typology per row), assigning the real "
        f"first-encountered pattern_id's typology to the small number of overlapping rows and flagging them "
        f"explicitly in that notebook's own label-construction cell (never silently dropped or merged)."
    )
else:
    TYPOLOGY_LABEL_POLICY = (
        f"Real cross-typology overlap is {MULTI_TYPOLOGY_POLICY_THRESHOLD_PCT}%+ on at least one variant -- "
        f"this is material enough that Notebook 2 must not silently collapse it to a single label. Overlapping "
        f"rows will be tagged with an explicit 'MULTI' category alongside the 8 real typologies, evaluated and "
        f"reported separately, and the multi-class-vs-multi-label framing question re-opened there with the "
        f"real numbers above as evidence."
    )
print(f"\nPOLICY (real, computed above -- not asserted): {TYPOLOGY_LABEL_POLICY}")

# ## 5. Primary Metric -- Real Policy Decision for a Multi-Class, Multi-Typology Problem
# `configs/bp2_typology_redflag_detection.yaml` currently carries `primary_metric: "PR-AUC"` -- a real but STALE
# placeholder copied from BP1's binary-classification config when this BP's scaffold was first created. PR-AUC
# is a binary/ranking metric and does not apply to an 8-class (or 9, if Section 4's MULTI category is needed)
# classification target. This notebook corrects that for real, in the config file itself (Section 7 below).
#
# **Locked choice: macro-averaged F1** across all real typology classes observed in Section 3 -- not
# micro-averaged (which would let the largest real typology dominate the score, the same imbalance-blindness
# problem PR-AUC solves for BP1) and not accuracy (meaningless once class counts are this uneven). Per-typology
# recall is additionally reported per class in every later notebook (this is the master plan's own locked
# Before/After framing for BP2: "Real per-typology recall across all 8 patterns").

PRIMARY_METRIC = "macro_f1"
print(f"\nPrimary metric (locked here, this run): {PRIMARY_METRIC}")
print("Secondary/reported: per-typology recall (all real observed typologies, never averaged away silently).")

# ## 6. Regulatory & Business Policy Mapping
# Real typology -> red-flag language, matching FinCEN/FATF terminology rather than inventing new category names
# (same discipline as BP1 Notebook 1 Section 5).

policy_map = pd.DataFrame([
    {"typology": "FAN-OUT",        "red_flag_pattern": "Single account rapidly disperses funds to many counterparties"},
    {"typology": "FAN-IN",         "red_flag_pattern": "Single account rapidly aggregates funds from many counterparties"},
    {"typology": "GATHER-SCATTER", "red_flag_pattern": "Funds gathered into a hub account, then immediately scattered onward"},
    {"typology": "SCATTER-GATHER", "red_flag_pattern": "Funds scattered outward, then re-gathered into a single account"},
    {"typology": "CYCLE",          "red_flag_pattern": "Funds return to (near) the originating account via a chain of hops"},
    {"typology": "BIPARTITE",      "red_flag_pattern": "Dense many-to-many transfers between two account groups"},
    {"typology": "STACK",          "red_flag_pattern": "Layered sequential transfers through a chain of intermediary accounts"},
    {"typology": "RANDOM",         "red_flag_pattern": "No single structural signature -- irregular/randomized transfer pattern"},
])
print("\nReal typology -> red-flag policy mapping (FinCEN/FATF terminology, all 8 locked typologies):")
print(policy_map.to_string(index=False))

REGULATORY_FRAMEWORKS = [
    ("FinCEN SAR filing requirements (31 CFR Section 1020.320)",
     "BP2 (typology evidence feeding any future SAR workflow, not itself a SAR-prediction model)"),
    ("FATF 40 Recommendations", "BP2, BP6 (the typology taxonomy itself)"),
    ("Bank Secrecy Act (31 U.S.C. Section 5311)", "Platform-wide"),
    ("FFIEC BSA/AML Examination Manual (5 pillars)", "Platform-wide"),
    ("SR 11-7 Model Risk Management", "Every model-bearing BP"),
]

# ## 7. Real Before-Baseline Definition (Notebook 4's Before/After Table)
# Per master-plan Section 7A's locked per-BP table: BP2's real "Before" is a **single-typology heuristic** --
# a rule that only catches the most structurally obvious of the 8 typologies (FAN-OUT: a single account with an
# unusually high real distinct-counterparty count in a short real window) without any ML. This is defined as
# policy here; it is RECOMPUTED for real against real data in Notebook 4, exactly like BP1's naive baseline --
# no number is asserted in this notebook.
BEFORE_BASELINE_POLICY = (
    "Single-typology heuristic: flag an account as FAN-OUT-suspicious if its real distinct-counterparty count "
    "in a rolling real window exceeds a fixed real threshold (mirrors BP1's fixed-threshold baseline pattern) "
    "-- the one typology a human analyst could plausibly flag by eye without ML. All other 7 real typologies "
    "are NOT caught by this baseline by construction, which is itself the real business case for BP2's ML "
    "model. Exact threshold and real precision/recall are computed in Notebook 4, never asserted here."
)
print(f"\nBefore-baseline policy (real, this run): {BEFORE_BASELINE_POLICY}")

# Real thermal pause after this notebook's EDA/parse work.
thermal_checkpoint(label="post BP2 Notebook 1 EDA")

# ## 8. Write Real, Corrected Policy Back to `configs/bp2_typology_redflag_detection.yaml`
# Real file write, performed only when this cell actually runs -- corrects the stale `primary_metric: PR-AUC`
# placeholder and records this notebook's real, computed policy decisions for Notebook 2 onward to read.

config_yaml = f"""business_problem: "BP2 - Typology & Red-Flag Pattern Detection"
random_seed: 42
primary_metric: "{PRIMARY_METRIC}"
secondary_metric: "per_typology_recall"
task_framing: "multi_class_typology_classification"
target_source: "Patterns.txt (block-structured, row-level parsed) -- NOT Is Laundering"
n_typologies_locked: 8
mandatory_validation_tier: "LI-Medium (or HI-Medium if typology counts are thin -- confirm in Notebook 3)"
cross_typology_overlap_policy: "{TYPOLOGY_LABEL_POLICY.splitlines()[0]}"
before_baseline_policy: "single_typology_heuristic_fanout_only"
notebook_count: 4
status: "notebook_1_business_understanding_policy_complete"
"""
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.write_text(config_yaml, encoding="utf-8")
print(f"\nReal, corrected config written to: {CONFIG_PATH}")
print(config_yaml)

# ## 9. Notebook 1 Summary
# Every figure below is pulled from the live variables computed above — nothing here is retyped from memory.

print("=" * 78)
print("BP2 — Notebook 1 Summary (real, this run)")
print("=" * 78)
print(f"HI-Small : {imbalance_hi['total']:,} txns, {len(hi_pattern_rows):,} real labeled typology-rows, "
      f"{n_typologies_hi} distinct typologies, {overlap_hi['pct_multi']:.4f}% cross-typology overlap")
print(f"LI-Small : {imbalance_li['total']:,} txns, {len(li_pattern_rows):,} real labeled typology-rows, "
      f"{n_typologies_li} distinct typologies, {overlap_li['pct_multi']:.4f}% cross-typology overlap")
print(f"Primary metric (locked, this run): {PRIMARY_METRIC}")
print(f"Target: multi-class typology label, derived from Patterns.txt (built for real in Notebook 2)")
print(f"Config written: {CONFIG_PATH}")
print("=" * 78)

# ## Next Step
# `notebooks/bp2_typology_redflag_detection/02_feature_engineering_modeling_SINGLE_CELL.py` -- builds the real
# per-transaction multi-class typology label from the row-level parse above (joined back to `*_Trans.csv`),
# engineers structural/graph-adjacent features (distinct-counterparty counts, in/out-degree, time-window
# aggregates -- no test-period leakage, per Lesson #11), and runs the same Stage A/B model-benchmark process
# BP1 used, adapted for multi-class (macro-F1 champion selection, per-typology recall reported every stage).
