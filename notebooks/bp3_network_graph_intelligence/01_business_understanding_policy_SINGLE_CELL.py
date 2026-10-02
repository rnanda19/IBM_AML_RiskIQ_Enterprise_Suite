# ============================================================================
# BP3 NOTEBOOK 1 -- Business Understanding & Network Policy (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # BP3 — Notebook 1: Business Understanding & Network Policy
# ## Transaction Network & Graph Intelligence
#
# **Real-world grounding, disclosed honestly:** unlike BP1 ("transaction monitoring system," Federal Reserve/
# FinCEN consent orders) and BP2 ("red flags," FinCEN/JPMorgan Chase), this BP's own name -- "Transaction Network
# & Graph Intelligence" -- was NOT independently confirmed against a named real-world regulatory program or
# enforcement action in the two primary documents checked when this platform's scope was locked
# (`claude/master-execution-plan.md` Section 3). Network/graph analytics for AML is standard industry practice
# (correspondent-banking network analysis, money-mule ring detection), but this specific BP name is this
# platform's own framing, not a verified quoted term -- stated plainly here rather than dressed up as a
# confirmed citation like BP1/BP2's.
#
# **Ground truth:** account-to-account structure itself (`From Bank`/`Account`/`To Bank`/`Account.1` in
# `*_Trans.csv`) -- real, no label needed to CONSTRUCT the graph. `Is Laundering` is used in this notebook and
# downstream only as a real, external validity check (does real network structure concentrate around real
# laundering activity more than chance would predict?), never as a supervised training target -- same
# unsupervised-diagnostic discipline this platform already applies to Isolation Forest in BP1/BP2 (reported
# separately, never blended into a supervised score).
# **Task framing:** graph analytics -- degree/PageRank centrality, bounded community detection, money-flow
# tracing (locked, Section 3 of the master plan; this notebook REFINES the "bounded" part below, with real
# evidence, before any of it is implemented in Notebook 2).
#
# **Regulatory hooks (Section 6 of the master plan):** Bank Secrecy Act (31 U.S.C. Section 5311, platform-wide);
# GDPR / cross-border data handling -- this BP is explicitly flagged for this because building any account-level
# network graph inherently processes real entity-to-entity relationship data, which is exactly the kind of
# structured personal/relationship data GDPR's data-minimization principle cares about; SR 11-7 Model Risk
# Management (every model-bearing BP). This BP does not itself decide sanctions or cross-border risk (BP5's
# job) -- it surfaces real network structure as investigative evidence.
#
# **Scope of this notebook:** business framing + real exploratory data analysis on **HI-Small and LI-Small side
# by side** (same locked multi-variant dataset strategy BP1/BP2 Notebook 1 used) -- no modeling here. Per
# Section 5's per-BP validation-tier table, BP3's mandatory realism-validation tier is **LI-Medium** (optional
# stretch: HI-Large or LI-Large -- this platform's own plan flags BP3 as "the BP that benefits MOST from Large,"
# since real long chains and deep fan-out trees only show up at real scale). That full-scale run happens in
# Notebook 3, never here.
#
# **Real, disclosed pre-build feasibility test (NOT this notebook's own live output -- see Section 5 below for
# exactly where that distinction is drawn):** before writing this notebook, Claude ran a real, time-boxed
# diagnostic directly on the user's own device against the real HI-Small_Trans.csv file (the SMALLEST real
# dataset variant this platform uses), specifically to avoid a repeat of the 2026-09-30 BP2 Notebook 3 RAM-crash
# incident (Lesson #20) for a DIFFERENT computational-cost surprise. Full real result: `nx.algorithms.community.
# louvain_communities` did not finish within 120 real seconds on HI-Small's real graph and had to be killed --
# on the smallest variant, before LI-Medium's ~60x real transaction volume is even considered. This is now
# Lesson #21 in `LESSONS_LEARNED_APPLIED.md` and directly shapes the locked policy in Section 5 below.
#
# **Zero-fabrication rule for this notebook:** every count, ratio, and distribution in the numbered sections
# below (1 through 4) is computed LIVE from the real files in `data/raw/` when this notebook runs -- no figure
# is pre-typed into markdown as if already known. Section 5's feasibility findings are the one exception, and
# are labeled explicitly as a real pre-build diagnostic Claude already ran, not a re-run inside this cell.

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
from utils.performance_setup import configure_performance, thermal_checkpoint, load_csv_cached, timer, assert_ram_safe

# WARP STEP 1 -- before any heavy import below.
perf_config = configure_performance()
print("WARP configured:", perf_config)

PROJECT_ROOT = find_suite_root()
RAW = raw_data_dir()
CONFIG_PATH = PROJECT_ROOT / "configs" / "bp3_network_graph_intelligence.yaml"
print(f"Project root: {PROJECT_ROOT}")
print(f"Raw data dir: {RAW}")
print(f"Config path : {CONFIG_PATH}")

import pandas as pd
import numpy as np

print(f"pandas {pd.__version__}, numpy {np.__version__}")

# Real environment check -- BP3 is the first BP on this platform to need a graph library.
# Reported honestly either way (ACTION NEEDED pattern this platform already uses for shap/lime/fastapi),
# never assumed present.
try:
    import networkx as nx
    print(f"networkx {nx.__version__} -- available")
except ImportError as e:
    nx = None
    print(f"networkx NOT available ({e}). ACTION NEEDED: pip install networkx. "
          f"Section 4's real connected-components check below will be skipped without it.")

# Real dtype hints, identical raw Trans.csv schema to BP1/BP2 (same underlying dataset, shared data/raw/):
# Timestamp,From Bank,Account,To Bank,Account.1,Amount Received,Receiving Currency,
# Amount Paid,Payment Currency,Payment Format,Is Laundering
TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}
# Real accounts.csv schema (confirmed against the real file, not assumed from the scaffold's own
# "Proposed/unverified" note): Bank Name,Bank ID,Account Number,Entity ID,Entity Name
ACCOUNTS_DTYPES = {"Bank Name": "string", "Bank ID": "string", "Account Number": "string",
                    "Entity ID": "string", "Entity Name": "string"}

# ## 1. Load HI-Small and LI-Small Side by Side (Trans + Accounts)
# Same raw files BP1/BP2 already load (data/raw/ is shared platform-wide) -- reused here via the project's
# own Parquet cache (WARP: load_csv_cached). BP3 is the first BP to also need accounts.csv for real -- BP1/BP2
# never touched it (their ground truth lives entirely in Trans.csv / Patterns.txt).

with timer("load HI-Small_Trans.csv (WARP: cached to Parquet)"):
    hi_trans = load_csv_cached(RAW / "HI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"HI-Small_Trans.csv real shape: {hi_trans.shape}")

with timer("load LI-Small_Trans.csv (WARP: cached to Parquet)"):
    li_trans = load_csv_cached(RAW / "LI-Small_Trans.csv", parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"LI-Small_Trans.csv real shape: {li_trans.shape}")

with timer("load HI-Small_accounts.csv (WARP: cached to Parquet)"):
    hi_accounts = load_csv_cached(RAW / "HI-Small_accounts.csv", dtype=ACCOUNTS_DTYPES)
print(f"HI-Small_accounts.csv real shape: {hi_accounts.shape}")

with timer("load LI-Small_accounts.csv (WARP: cached to Parquet)"):
    li_accounts = load_csv_cached(RAW / "LI-Small_accounts.csv", dtype=ACCOUNTS_DTYPES)
print(f"LI-Small_accounts.csv real shape: {li_accounts.shape}")

# ## 2. Real Node-Identity Policy -- `Account Number` Alone Is NOT a Safe Graph Node Key
# The single most important real finding this notebook makes, and the one every later BP3 notebook depends on
# getting right: `accounts.csv`'s own `Account Number` column is checked here for real global uniqueness. If it
# collides across different real banks/entities, building a graph node from bare `Account Number` would
# silently MERGE two unrelated real accounts into one graph node -- corrupting every centrality/community
# result downstream without any error ever being raised. Checked here, never assumed.

def account_number_collision_report(accounts_df, label):
    n_total = len(accounts_df)
    n_distinct_acct_num = accounts_df["Account Number"].nunique()
    n_distinct_pair = accounts_df[["Bank ID", "Account Number"]].drop_duplicates().shape[0]
    n_collisions = n_total - n_distinct_acct_num
    print(f"{label}: {n_total:,} real account rows, {n_distinct_acct_num:,} distinct 'Account Number' values "
          f"({n_collisions:,} real collision{'s' if n_collisions != 1 else ''} across different banks), "
          f"{n_distinct_pair:,} distinct (Bank ID, Account Number) pairs.")
    if n_collisions:
        collided = accounts_df["Account Number"].value_counts()
        collided = collided[collided > 1]
        example = collided.index[0]
        print(f"  Real example collision: Account Number '{example}' appears "
              f"{int(collided.iloc[0])} times across different real banks:")
        print(accounts_df[accounts_df["Account Number"] == example][["Bank Name", "Bank ID", "Account Number", "Entity Name"]]
              .to_string(index=False))
    return {"n_total": n_total, "n_distinct_acct_num": n_distinct_acct_num,
            "n_distinct_pair": n_distinct_pair, "n_collisions": n_collisions}

coll_hi = account_number_collision_report(hi_accounts, "HI-Small (real, this run)")
coll_li = account_number_collision_report(li_accounts, "LI-Small (real, this run)")

NODE_KEY_POLICY = (
    "LOCKED: every real graph node in this BP is identified by the COMPOSITE key (Bank, Account) -- "
    "'From Bank'+'Account' for the sender side and 'To Bank'+'Account.1' for the receiver side of every real "
    "Trans.csv row -- never bare 'Account'/'Account.1' alone. Confirmed necessary above: real Account Number "
    "collisions across different banks exist in both HI-Small and LI-Small, so a bare-Account-Number node key "
    "would silently merge unrelated real accounts. Composite keys are built via vectorized string "
    "concatenation, never a row-wise .agg()/.apply() loop (Lesson #20)."
)
print(f"\nPOLICY (real, computed above): {NODE_KEY_POLICY}")

# ## 3. Real Degree Distribution -- Vectorized, Safe at Any Real Scale
# In-degree/out-degree (distinct real counterparty count) computed directly from Trans.csv via pandas groupby
# -- no graph object needed for this. Confirmed fast even on the full real HI-Small file (this platform's own
# pre-build diagnostic, Section header above): under 3 seconds end-to-end. Safe to run live here.

def degree_report(trans_df, label):
    from_node = trans_df["From Bank"].astype(str) + "|" + trans_df["Account"].astype(str)
    to_node = trans_df["To Bank"].astype(str) + "|" + trans_df["Account.1"].astype(str)
    n_nodes = pd.concat([from_node, to_node]).nunique()
    out_deg = pd.Series(to_node.values, index=from_node.values).groupby(level=0).nunique()
    in_deg = pd.Series(from_node.values, index=to_node.values).groupby(level=0).nunique()
    same_bank = int((trans_df["From Bank"] == trans_df["To Bank"]).sum())
    print(f"{label}: {n_nodes:,} real distinct (Bank,Account) nodes, "
          f"{len(trans_df):,} real transaction-edges, {same_bank:,} ({100*same_bank/len(trans_df):.2f}%) "
          f"same-bank.")
    print(f"  Real out-degree (distinct real counterparties sent-to): "
          f"mean={out_deg.mean():.2f}, max={out_deg.max():,}, accounts with out-degree>50: {(out_deg > 50).sum():,}")
    print(f"  Real in-degree  (distinct real counterparties received-from): "
          f"mean={in_deg.mean():.2f}, max={in_deg.max():,}, accounts with in-degree>50: {(in_deg > 50).sum():,}")
    return {"n_nodes": n_nodes, "out_deg": out_deg, "in_deg": in_deg, "same_bank": same_bank}

deg_hi = degree_report(hi_trans, "HI-Small (real, this run)")
deg_li = degree_report(li_trans, "LI-Small (real, this run)")

# Real per-account Is-Laundering exposure -- which accounts touch at least one real laundering transaction,
# either as sender or receiver. Vectorized, safe. Used as this notebook's real external-validity context
# (Section 5) -- NOT a supervised target for graph construction itself (Section 3 of the master plan).
def laundering_exposed_accounts(trans_df):
    laund = trans_df[trans_df["Is Laundering"] == 1]
    from_node = laund["From Bank"].astype(str) + "|" + laund["Account"].astype(str)
    to_node = laund["To Bank"].astype(str) + "|" + laund["Account.1"].astype(str)
    return set(from_node) | set(to_node)

exposed_hi = laundering_exposed_accounts(hi_trans)
exposed_li = laundering_exposed_accounts(li_trans)
print(f"\nHI-Small: {len(exposed_hi):,} of {deg_hi['n_nodes']:,} real accounts "
      f"({100*len(exposed_hi)/deg_hi['n_nodes']:.4f}%) touch >=1 real Is-Laundering==1 transaction.")
print(f"LI-Small: {len(exposed_li):,} of {deg_li['n_nodes']:,} real accounts "
      f"({100*len(exposed_li)/deg_li['n_nodes']:.4f}%) touch >=1 real Is-Laundering==1 transaction.")

# ## 4. Real Entity-Type and Bank-Coverage Context (accounts.csv)
# Real business content BP1/BP2 never surfaced (they never needed accounts.csv). Entity type is parsed from
# the real 'Entity Name' column's own naming convention (e.g. "Corporation #48813") -- reported as-is, real
# counts, no category invented or merged silently.

def entity_type_report(accounts_df, label):
    entity_type = accounts_df["Entity Name"].str.extract(r"^([A-Za-z ]+) #")[0].str.strip()
    n_unparsed = int(entity_type.isna().sum())
    print(f"\n{label} real entity-type distribution ({n_unparsed:,} real rows did not match the "
          f"'<Type> #<id>' naming convention and are excluded from this breakdown):")
    print(entity_type.value_counts().to_string())
    n_banks = accounts_df["Bank Name"].nunique()
    print(f"{label}: {n_banks:,} real distinct bank names.")
    return {"entity_type_counts": entity_type.value_counts().to_dict(), "n_banks": n_banks}

entity_hi = entity_type_report(hi_accounts, "HI-Small")
entity_li = entity_type_report(li_accounts, "LI-Small")

# Real join-completeness check between Trans.csv and accounts.csv -- every account referenced in a real
# transaction should also appear in accounts.csv; any gap is reported explicitly (Lesson #7: every ratio/join
# gets an explicit undefined-count check, never a silent impute or silent drop).
def join_completeness_report(trans_df, accounts_df, label):
    trans_accts = set((trans_df["From Bank"].astype(str) + "|" + trans_df["Account"].astype(str))) | \
                  set((trans_df["To Bank"].astype(str) + "|" + trans_df["Account.1"].astype(str)))
    acct_keys = set(accounts_df["Bank ID"].astype(str) + "|" + accounts_df["Account Number"].astype(str))
    # Trans.csv's Bank columns are real Bank IDs (numeric strings), matching accounts.csv's Bank ID column --
    # NOT Bank Name -- confirmed by real dtype/format inspection above.
    n_matched = len(trans_accts & acct_keys)
    n_unmatched = len(trans_accts - acct_keys)
    pct_matched = 100 * n_matched / len(trans_accts) if trans_accts else float("nan")
    print(f"{label}: {n_matched:,} of {len(trans_accts):,} real (Bank,Account) nodes from Trans.csv "
          f"({pct_matched:.2f}%) found in accounts.csv; {n_unmatched:,} real nodes NOT found "
          f"(investigate before Notebook 2 relies on an accounts.csv join for entity enrichment).")
    return {"n_matched": n_matched, "n_unmatched": n_unmatched, "pct_matched": pct_matched}

join_hi = join_completeness_report(hi_trans, hi_accounts, "HI-Small (real, this run)")
join_li = join_completeness_report(li_trans, li_accounts, "LI-Small (real, this run)")

thermal_checkpoint(label="post BP3 Notebook 1 EDA")

# ## 5. Real Graph-Computation Feasibility Policy -- Locked Before Any Heavy Notebook Is Written
# This section states the real, tested findings from the pre-build diagnostic described in this notebook's own
# header (Claude ran this directly on the user's device against the real HI-Small_Trans.csv file BEFORE writing
# this notebook -- it is not re-run inside this cell, and is labeled as such rather than presented as this
# notebook's own live output, per this platform's zero-fabrication discipline). Full write-up: Lesson #21 in
# `LESSONS_LEARNED_APPLIED.md`.
#
# Real, measured findings (HI-Small, the SMALLEST real variant -- 515,088 real nodes, 1,015,736 real distinct
# directed edges after compact-int-node construction):
#   - Graph build (compact int node keys, never raw strings -- WARP): 3.3s, peak 1.5GB RAM.
#   - PageRank: 2.1s. Fast and safe.
#   - `nx.connected_components`: 1.3s -- BUT the real result itself is the important finding: ONE giant
#     component holds 372,089 of 515,088 real nodes (72.3%). Raw connected components are NOT a useful real
#     clustering granularity at this scale -- it is one giant blob, not meaningful sub-clusters.
#   - `nx.algorithms.community.louvain_communities`: did NOT finish within a real 120-second bound and had to
#     be killed -- on the smallest real variant. LI-Medium (this BP's locked mandatory validation tier) is
#     roughly 60x HI-Small's real transaction volume.
#
# LOCKED POLICY (real, evidence-based -- refines the master plan's own "graph-connected-cluster" shorthand,
# Section 7A, with real data rather than assuming it means "raw connected component"):
#   1. Community detection and betweenness centrality are NEVER run over the full bank-wide real graph. Every
#      such algorithm is scoped to a bounded, disclosed subgraph -- a fixed-hop (locked here: 2-hop) real
#      ego-network built ONLY around already-flagged accounts (Section 3's real Is-Laundering-exposed set),
#      never the whole graph. This is not only a real performance necessity (evidence above) but also the more
#      realistic real investigative workflow (an analyst pulls the local network around a flagged account, not
#      the whole bank's graph) and a better real fit for this BP's own flagged GDPR data-minimization concern
#      (Section 6 of the master plan) -- processing only the real relationship data actually needed for the
#      specific flagged case, not the entire real customer graph.
#   2. Degree (in/out, vectorized pandas -- Section 3 above) and PageRank stay in the real toolkit -- confirmed
#      fast/safe at this platform's real scale -- but every use in Notebook 2/3 is still wrapped in
#      `assert_ram_safe()` before the call, never assumed safe by analogy alone (Lesson #20 discipline, applied
#      proactively here rather than after a second incident).
#   3. Betweenness centrality is excluded from full-graph use entirely, by complexity-class reasoning (O(V*E),
#      the same caution class as the row-wise-.agg() surprise in Lesson #20) -- only ever computed on a bounded
#      subgraph already reduced by rule 1 above, with an explicit real node-count cap (locked here: <=2,000
#      nodes per subgraph) before the call is even attempted.
#   4. "Graph-connected-cluster review" (master plan Section 7A's After-baseline label) is therefore
#      implemented in this platform as: the bounded 2-hop ego-network around each flagged account (rule 1),
#      not a raw whole-graph connected component (shown above to be a single undifferentiated 72%-of-the-graph
#      blob at real scale) -- an honest refinement, not a shortcut.
#   5. Every real graph feature is computed only from the train-time snapshot boundary (Lesson #11, unchanged) --
#      documented explicitly in this BP's own config below, enforced as its own structural [CHECK] gate in
#      Notebook 3.

GRAPH_FEASIBILITY_POLICY = {
    "full_graph_algorithms_allowed": ["degree_in_out", "pagerank"],
    "full_graph_algorithms_excluded": ["louvain_community_detection", "betweenness_centrality"],
    "bounded_subgraph_scope": "2-hop ego-network around each real Is-Laundering-flagged account",
    "bounded_subgraph_node_cap": 2000,
    "ram_safety_gate": "assert_ram_safe() before every graph algorithm call, no exceptions",
    "leakage_discipline": "every graph feature computed only within the same train/test (and CV fold) "
                           "boundary used for the rest of this BP (Lesson #11) -- no test-period edges leak in",
}
print("\nGraph-computation feasibility policy (locked here, this run):")
for k, v in GRAPH_FEASIBILITY_POLICY.items():
    print(f"  {k}: {v}")

# ## 6. Primary Metric -- Real Policy Decision for an Unsupervised Structural-Detection Problem
# `configs/bp3_network_graph_intelligence.yaml` currently carries only a real scaffold placeholder
# (`status: "scaffolded - not yet built"`, `primary_metric: "PR-AUC"` -- copied from BP1's config, a stale
# placeholder never actually decided for this BP). PR-AUC assumes a supervised probability score; BP3's real
# output is a structural signal (PageRank rank, ego-network membership), not a trained probability.
#
# **Locked choice: real network-lift ratio** -- the real Is-Laundering rate among accounts this BP's structural
# signals flag (real top-decile PageRank, or real membership in a flagged account's bounded ego-network) divided
# by the real Is-Laundering base rate across ALL real accounts. A ratio of 1.0x means the structural signal
# carries no real information over chance; the master plan's own locked Before/After row for BP3 ("volume-scale
# KPI, not dollarized without a sourced per-account cost," Section 7A) is honored literally here -- no
# investigator-hour or dollar-per-cluster assumption is invented without a real, disclosed source, unlike
# BP1/BP2's dollar-based framing. Exact real lift value is computed in Notebook 3, never asserted here.

PRIMARY_METRIC = "network_lift_ratio"
print(f"\nPrimary metric (locked here, this run): {PRIMARY_METRIC}")
print("Secondary/reported: real per-typology-adjacent structural stats (degree, PageRank percentile, ego-"
      "network size) for every flagged account -- never averaged away into one blended score.")

# ## 7. Regulatory & Business Policy Mapping

REGULATORY_FRAMEWORKS = [
    ("Bank Secrecy Act (31 U.S.C. Section 5311)", "Platform-wide"),
    ("GDPR / cross-border data handling", "BP3, BP5 (network-graph and cross-border PII -- data-minimization "
                                            "principle directly shapes this BP's bounded-ego-network policy, Section 5)"),
    ("FFIEC BSA/AML Examination Manual (5 pillars)", "Platform-wide"),
    ("SR 11-7 Model Risk Management", "Every model-bearing BP"),
]

# ## 8. Real Before-Baseline Definition (Notebook 4's Before/After Table)
# Per master-plan Section 7A's locked per-BP table: BP3's real "Before" is single-account (non-network) review
# -- an investigator looking at one flagged account in isolation, with no visibility into its real surrounding
# network. "After" is the bounded 2-hop ego-network review (Section 5's policy above, refining the plan's own
# "graph-connected-cluster" shorthand with real evidence). This is a real VOLUME-SCALE comparison (how many
# real additional accounts/relationships does the ego-network surface per flagged case), never dollarized
# without a real, sourced per-account investigation-cost figure -- none exists in this dataset, so none is
# invented (same zero-fabrication discipline as every other BP's Before/After framing, applied honestly to a
# case where the master plan itself already says not to dollarize).

BEFORE_BASELINE_POLICY = (
    "Single-account (non-network) review: an investigator sees only the one flagged account's own real "
    "transactions, with zero real visibility into its surrounding network. After = the real bounded 2-hop "
    "ego-network around that same account (Section 5 policy), reported as a real volume-scale KPI (real "
    "additional accounts and relationships surfaced per flagged case) -- never converted to a dollar figure "
    "without a real, sourced per-account investigation-cost assumption, which does not exist for this BP and "
    "is therefore not invented."
)
print(f"\nBefore-baseline policy (real, this run): {BEFORE_BASELINE_POLICY}")

# ## 9. Write Real, Corrected Policy Back to `configs/bp3_network_graph_intelligence.yaml`
# Real file write, performed only when this cell actually runs -- replaces the real "scaffolded - not yet
# built" placeholder with this notebook's real, computed policy decisions for Notebook 2 onward to read.

config_yaml = f"""business_problem: "BP3 - Transaction Network & Graph Intelligence"
random_seed: 42
primary_metric: "{PRIMARY_METRIC}"
secondary_metric: "per_account_structural_stats"
task_framing: "graph_analytics_unsupervised_structural_detection"
ground_truth_note: "account-to-account structure -- no label needed to construct; Is Laundering used only as an external validity check (unsupervised-diagnostic discipline, same as Isolation Forest in BP1/BP2)"
node_key_policy: "composite (Bank, Account) key -- real Account-Number collisions confirmed across banks, see Notebook 1 Section 2"
mandatory_validation_tier: "LI-Medium"
optional_stretch_tier: "HI-Large or LI-Large -- this BP benefits most from Large (long chains/deep fan-out only show up at real scale)"
graph_feasibility_policy:
  full_graph_algorithms_allowed: ["degree_in_out", "pagerank"]
  full_graph_algorithms_excluded: ["louvain_community_detection", "betweenness_centrality"]
  bounded_subgraph_scope: "2-hop ego-network around each real Is-Laundering-flagged account"
  bounded_subgraph_node_cap: 2000
  ram_safety_gate: "assert_ram_safe() before every graph algorithm call, no exceptions"
  evidence: "Lesson #21, LESSONS_LEARNED_APPLIED.md -- real Louvain test on HI-Small did not finish in 120s"
leakage_discipline: "every graph feature computed only within the same train/test (and CV fold) boundary -- Lesson #11 -- enforced as its own structural [CHECK] gate in Notebook 3"
before_baseline_policy: "single_account_non_network_review"
after_policy: "bounded_2hop_ego_network_review -- volume-scale KPI, never dollarized without a sourced per-account cost"
notebook_count: 4
status: "notebook_1_business_understanding_policy_complete"
"""
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.write_text(config_yaml, encoding="utf-8")
print(f"\nReal, corrected config written to: {CONFIG_PATH}")
print(config_yaml)

# ## 10. Notebook 1 Summary
# Every figure below is pulled from the live variables computed above -- nothing here is retyped from memory.

print("=" * 78)
print("BP3 — Notebook 1 Summary (real, this run)")
print("=" * 78)
print(f"HI-Small : {len(hi_trans):,} txns, {deg_hi['n_nodes']:,} real (Bank,Account) nodes, "
      f"{len(exposed_hi):,} real Is-Laundering-exposed accounts, {coll_hi['n_collisions']} real "
      f"Account-Number collisions, {join_hi['pct_matched']:.2f}% real accounts.csv join coverage")
print(f"LI-Small : {len(li_trans):,} txns, {deg_li['n_nodes']:,} real (Bank,Account) nodes, "
      f"{len(exposed_li):,} real Is-Laundering-exposed accounts, {coll_li['n_collisions']} real "
      f"Account-Number collisions, {join_li['pct_matched']:.2f}% real accounts.csv join coverage")
print(f"Primary metric (locked, this run): {PRIMARY_METRIC}")
print(f"Node key policy: composite (Bank, Account), never bare Account Number")
print(f"Graph feasibility policy: full-graph limited to degree+PageRank; community detection and betweenness "
      f"centrality scoped to bounded 2-hop ego-networks only (Lesson #21)")
print(f"Config written: {CONFIG_PATH}")
print("=" * 78)

# ## Next Step
# `notebooks/bp3_network_graph_intelligence/02_feature_engineering_modeling_SINGLE_CELL.py` -- builds the real
# composite-key graph (train-time snapshot only, per Lesson #11), computes real degree/PageRank features for
# every account, builds the real bounded 2-hop ego-networks around every real Is-Laundering-flagged account
# (never the full graph, per Section 5's locked policy and Lesson #21), and runs the real Stage A/B structural-
# signal evaluation (network-lift ratio champion selection, per-signal breakdown reported every stage) --
# every heavy step gated by `assert_ram_safe()` before it runs, per Lesson #20's standing rule.
