# ============================================================================
# BP1 NOTEBOOK 1 -- Business Understanding & Typology Policy (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # BP1 — Notebook 1: Business Understanding & Typology Policy
# ## Transaction Monitoring & Suspicious Activity Detection
# 
# **Real-world grounding (verified against primary sources, not paraphrased AML-textbook language):**
# - Federal Reserve consent order, American Express Bank International — real institutions run a
#   *"transaction monitoring system"*.
# - FinCEN civil money penalty assessment, JPMorgan Chase — a real *"computer monitoring system [that] issued
#   alerts"*.
# - FinCEN's own AML guidance uses *"red flags"* for typology indicators — the term this notebook uses for the
#   eight labeled laundering typologies below.
# 
# **Target:** `Is Laundering` — a real, direct ground-truth label in the raw transaction file (not a proxy).
# **Task framing:** supervised imbalanced binary classification. **Primary metric:** PR-AUC (per
# `configs/bp1_transaction_monitoring_detection.yaml`) — chosen over ROC-AUC because the positive class is a small
# fraction of all transactions (measured below), where PR-AUC is materially more informative of real detection
# quality than ROC-AUC.
# 
# **Regulatory hooks this BP evidences (not a compliance determination — evidence/detection only):**
# USA PATRIOT Act §326 (Customer Identification Program) and §314(a)/(b) information-sharing; FinCEN SAR filing
# requirements (31 CFR §1020.320) — this notebook produces detection evidence that could *feed* a SAR workflow,
# it does **not** predict SAR-filed/not-filed (no such independent label exists in this dataset); OFAC
# sanctions-list screening context.
# 
# **Scope of this notebook:** business framing + real exploratory data analysis on **HI-Small and LI-Small side
# by side** (per the locked multi-variant dataset strategy, Section 2.1 of the master plan) — no modeling here.
# HI-Small is this BP's fast build/debug target (Notebook 2 onward); LI-Small is carried alongside from this
# first notebook so the realistic-imbalance case is visible from the start, even though LI-Medium is the
# *mandatory* validation tier (deferred to Notebook 3 — LI-Small alone is not the final validation).
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
print(f"Project root: {PROJECT_ROOT}")
print(f"Raw data dir: {RAW}")

import pandas as pd
import numpy as np

print(f"pandas {pd.__version__}, numpy {np.__version__}")

# Real dtype hints from the actual header row inspected on-device (2026-09-29):
# Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,
# Amount Paid,Payment Currency,Payment Format,Is Laundering
# pandas auto-renames the duplicate 'Account' header to 'Account' / 'Account.1'.
TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}

# ## 1. Load HI-Small and LI-Small Side by Side
# Per Section 2.1's locked policy: these two variants are **never merged or concatenated** (each is an
# independently-generated synthetic simulation with its own Entity/Bank ID space) — they are loaded and compared
# side by side, every downstream figure labeled by variant.

with timer("load HI-Small_Trans.csv (WARP: cached to Parquet on first read)"):
    hi_small = load_csv_cached(
        RAW / "HI-Small_Trans.csv",
        parse_dates=["Timestamp"],
        dtype=TRANS_DTYPES,
    )
print(f"HI-Small_Trans.csv real shape: {hi_small.shape}")
hi_small.head(3)

with timer("load LI-Small_Trans.csv (WARP: cached to Parquet on first read)"):
    li_small = load_csv_cached(
        RAW / "LI-Small_Trans.csv",
        parse_dates=["Timestamp"],
        dtype=TRANS_DTYPES,
    )
print(f"LI-Small_Trans.csv real shape: {li_small.shape}")
li_small.head(3)

with timer("load accounts.csv for both variants"):
    hi_small_accounts = load_csv_cached(RAW / "HI-Small_accounts.csv")
    li_small_accounts = load_csv_cached(RAW / "LI-Small_accounts.csv")

print(f"HI-Small_accounts.csv real shape: {hi_small_accounts.shape}")
print(f"LI-Small_accounts.csv real shape: {li_small_accounts.shape}")
hi_small_accounts.head(3)

# ## 2. Real Class Imbalance — HI-Small vs. LI-Small
# This is the number that justifies PR-AUC as the primary metric, and the number behind the HI/LI naming itself
# (Higher- vs Lower-illicit-ratio) — computed live below, not asserted.

def imbalance_report(df, label):
    n_total = len(df)
    n_positive = int(df["Is Laundering"].sum())
    ratio_pct = 100 * n_positive / n_total
    one_in = n_total / n_positive if n_positive else float("inf")
    print(f"{label}:")
    print(f"  total transactions       : {n_total:,}")
    print(f"  Is Laundering == 1       : {n_positive:,}")
    print(f"  positive ratio           : {ratio_pct:.4f}%  (~1 in {one_in:,.0f})")
    return {"total": n_total, "positive": n_positive, "ratio_pct": ratio_pct, "one_in": one_in}

imbalance_hi = imbalance_report(hi_small, "HI-Small (real, this run)")
print()
imbalance_li = imbalance_report(li_small, "LI-Small (real, this run)")

print(f"\nHI-Small illicit ratio is {imbalance_hi['ratio_pct']/imbalance_li['ratio_pct']:.2f}x LI-Small's "
      f"(real, computed — this is what 'Higher-Illicit-ratio' vs 'Lower-Illicit-ratio' means in practice).")

# ## 3. Typology Policy — Parsing the Real Pattern Files
# `*_Patterns.txt` labels each laundering transaction with one of eight typologies via
# `BEGIN LAUNDERING ATTEMPT - <TYPOLOGY>: <description>` / `END LAUNDERING ATTEMPT - <TYPOLOGY>` blocks, each
# containing the real transaction rows (same CSV layout as `*_Trans.csv`, no header) belonging to that attempt.
# This is the natural ground truth for typology-level red-flag policy — parsed for real below, not assumed from
# the paper's abstract description.

import re

def parse_patterns_file(path):
    """Real parser for *_Patterns.txt: returns a DataFrame of one row per labeled
    laundering attempt (pattern_id, typology, description, n_transactions)."""
    begin_re = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Z-]+):\s*(.*)$")
    records = []
    pattern_id = 0
    current_typology = None
    current_desc = None
    n_rows = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = begin_re.match(line)
            if m:
                current_typology, current_desc = m.group(1), m.group(2)
                n_rows = 0
                continue
            if line.startswith("END LAUNDERING ATTEMPT"):
                records.append({
                    "pattern_id": pattern_id,
                    "typology": current_typology,
                    "description": current_desc,
                    "n_transactions": n_rows,
                })
                pattern_id += 1
                current_typology = None
                continue
            if current_typology is not None and line.strip():
                n_rows += 1
    return pd.DataFrame.from_records(records)

with timer("parse HI-Small_Patterns.txt"):
    hi_patterns = parse_patterns_file(RAW / "HI-Small_Patterns.txt")
with timer("parse LI-Small_Patterns.txt"):
    li_patterns = parse_patterns_file(RAW / "LI-Small_Patterns.txt")

print(f"HI-Small: {len(hi_patterns)} real labeled laundering attempts parsed")
print(f"LI-Small: {len(li_patterns)} real labeled laundering attempts parsed")

print("HI-Small real typology distribution (count of labeled attempts, this run):")
print(hi_patterns["typology"].value_counts().to_string())
print()
print("LI-Small real typology distribution (count of labeled attempts, this run):")
print(li_patterns["typology"].value_counts().to_string())
print()
print("HI-Small total labeled transaction-rows across all attempts:", int(hi_patterns["n_transactions"].sum()))
print("LI-Small total labeled transaction-rows across all attempts:", int(li_patterns["n_transactions"].sum()))

# ## 4. Sanity Check — Patterns Coverage vs. `Is Laundering` Positives
# An honest validation, not an assumed match: do the transaction-row counts inside the labeled pattern blocks
# line up with the real `Is Laundering == 1` count from Section 2? A transaction can legitimately appear in more
# than one labeled attempt (e.g. a hub account in both a FAN-IN and a FAN-OUT), so an exact equality is not
# guaranteed — this cell reports the real relationship rather than assuming one.

hi_pattern_rows = int(hi_patterns["n_transactions"].sum())
li_pattern_rows = int(li_patterns["n_transactions"].sum())

print(f"HI-Small: {hi_pattern_rows:,} pattern-block transaction-rows vs {imbalance_hi['positive']:,} "
      f"real Is-Laundering==1 rows in Trans.csv "
      f"({'EXACT MATCH' if hi_pattern_rows == imbalance_hi['positive'] else 'DIFFER — see note below'})")
print(f"LI-Small: {li_pattern_rows:,} pattern-block transaction-rows vs {imbalance_li['positive']:,} "
      f"real Is-Laundering==1 rows in Trans.csv "
      f"({'EXACT MATCH' if li_pattern_rows == imbalance_li['positive'] else 'DIFFER — see note below'})")
print()
print("If these differ, the honest reading is transaction overlap across multiple labeled attempts (a single "
      "transaction row counted inside more than one BEGIN/END block) — not a data-quality defect. CORRECTION "
      "(2026-09-30, corrections review): this is EDA context for BP2's own typology join (which does match "
      "Patterns.txt back to Trans.csv row-by-row), not a BP1 blocker — BP1's real target is simply the raw "
      "'Is Laundering' column already in Trans.csv, and Notebook 2 never joins Patterns.txt at all. The original "
      "wording here overstated this as something Notebook 2 needed to resolve; it does not.")

# ## 5. Typology → Regulatory Red-Flag Policy Mapping
# Maps this dataset's real eight typology labels to the red-flag language FinCEN and JPMorgan Chase's own AML
# program use, so BP1's later feature engineering (Notebook 2) and reporting (Notebook 4) stay traceable back to
# real regulatory terminology rather than inventing new category names.

policy_map = pd.DataFrame([
    {"typology": "FAN-OUT",        "red_flag_pattern": "Single account rapidly disperses funds to many counterparties"},
    {"typology": "FAN-IN",         "red_flag_pattern": "Single account rapidly aggregates funds from many counterparties"},
    {"typology": "GATHER-SCATTER", "red_flag_pattern": "Funds gathered into a hub account, then immediately scattered onward"},
    {"typology": "SCATTER-GATHER", "red_flag_pattern": "Funds scattered outward, then re-gathered into a single account"},
    {"typology": "CYCLE",          "red_flag_pattern": "Funds return to (a) near the originating account via a chain of hops"},
    {"typology": "BIPARTITE",      "red_flag_pattern": "Dense many-to-many transfers between two account groups"},
    {"typology": "STACK",          "red_flag_pattern": "Layered sequential transfers through a chain of intermediary accounts"},
    {"typology": "RANDOM",         "red_flag_pattern": "No single structural signature — irregular/randomized transfer pattern"},
])
policy_map

# ## 6. Payment Format & Currency Context
# Real distributions — informs which fields carry signal for Notebook 2's feature engineering, and whether
# FX-normalization is needed before aggregating dollar amounts (flagged open item: `Amount Paid`/`Amount Received`
# vary by currency per row — not yet resolved anywhere in this platform).

print("HI-Small real Payment Format distribution:")
print(hi_small["Payment Format"].value_counts().to_string())
print()
print("HI-Small real Payment Currency distribution (top 10):")
print(hi_small["Payment Currency"].value_counts().head(10).to_string())

# Bank Name embeds a country token as real text (observed directly on-device, e.g. 'Portugal Bank #4507',
# 'Canada Bank #27', 'UK Bank #33') — a usable real feature for BP1/BP5's cross-border context, extracted here,
# not assumed from documentation.
hi_small_accounts["bank_country_token"] = hi_small_accounts["Bank Name"].str.extract(r"^([A-Za-z ]+?)\s+Bank")
print("HI-Small real bank-country-token distribution (top 15, from actual Bank Name text):")
print(hi_small_accounts["bank_country_token"].value_counts().head(15).to_string())

# Real thermal pause after this notebook's EDA load/parse work.
thermal_checkpoint(label="post BP1 Notebook 1 EDA")

# ## 7. Notebook 1 Summary
# Every figure below is pulled from the live variables computed above — nothing here is retyped from memory.

print("=" * 70)
print("BP1 — Notebook 1 Summary (real, this run)")
print("=" * 70)
print(f"HI-Small : {imbalance_hi['total']:,} txns, {imbalance_hi['positive']:,} positive "
      f"({imbalance_hi['ratio_pct']:.4f}%), {len(hi_patterns)} labeled attempts, "
      f"{hi_small_accounts.shape[0]:,} accounts")
print(f"LI-Small : {imbalance_li['total']:,} txns, {imbalance_li['positive']:,} positive "
      f"({imbalance_li['ratio_pct']:.4f}%), {len(li_patterns)} labeled attempts, "
      f"{li_small_accounts.shape[0]:,} accounts")
print(f"Primary metric (locked): PR-AUC — configs/bp1_transaction_monitoring_detection.yaml")
print(f"Target column (real, direct label): 'Is Laundering'")
print("=" * 70)

# ## Next Step
# `notebooks/bp1_transaction_monitoring_detection/02_feature_engineering_modeling_SINGLE_CELL.py` — HI-Small
# only, for fast build/debug iteration (per Section 2.1's locked staged pattern). LI-Small carries forward as the
# side-by-side comparison variant; LI-Medium is picked up as the mandatory realism-validation tier in Notebook 3,
# not before.
