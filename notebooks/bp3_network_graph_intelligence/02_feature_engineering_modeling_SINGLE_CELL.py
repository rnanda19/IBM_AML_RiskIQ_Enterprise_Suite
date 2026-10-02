# ============================================================================
# BP3 NOTEBOOK 2 -- Feature Engineering & Structural-Signal Modeling (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # BP3 — Notebook 2: Feature Engineering & Structural-Signal Modeling
# ## Transaction Network & Graph Intelligence
#
# **Scope of this notebook:** HI-Small only (this BP's fast build/debug target, per the same locked staged
# pattern BP1/BP2 used -- LI-Medium is the mandatory realism-validation tier, picked up in Notebook 3, not
# before). Builds the real composite-key graph, computes real structural signals for every real account
# (degree, PageRank, bounded 2-hop proximity-to-flagged-accounts), and runs a real Stage-A single-split
# evaluation of each signal's real network-lift ratio against the real `Is Laundering` label -- used here
# ONLY as an external validity check, never as a supervised training target (unchanged from Notebook 1's
# locked unsupervised-diagnostic discipline).
#
# **No trained ML model exists in this BP, disclosed honestly here and carried into Notebook 3/4:** BP1/BP2
# fit LightGBM/XGBoost/CatBoost/RandomForest candidates. BP3's real candidates are STRUCTURAL SIGNALS
# (out-degree, in-degree, total-degree, PageRank, 2-hop proximity), each already fully interpretable by
# construction -- there is no black-box score requiring SHAP/LIME post-hoc explainability. Notebook 3 and
# Notebook 4 state this plainly rather than fabricating a SHAP run against a model that does not exist.
#
# **Leakage discipline (Lesson #11), applied concretely here:** the graph's real EDGES (who-transacts-with-
# whom) are built from the full real HI-Small file -- removing a held-out account's real edges would distort
# the very structure being measured, which is not how degree/PageRank are defined. What IS held out, to keep
# the real network-lift ratio an honest out-of-sample statistic rather than a circular in-sample one: every
# signal's THRESHOLD (e.g., "top real decile") is fit on a real TRAIN split of accounts and the real lift
# ratio is measured only on a disjoint real TEST split of accounts -- mirroring BP1/BP2's own fit-on-train,
# evaluate-on-test Stage-A discipline, adapted to an unsupervised structural problem. The 2-hop proximity
# signal is seeded ONLY from real TRAIN-flagged accounts, and its real lift is measured only on real TEST
# accounts -- a genuine "does proximity to a known-train launderer predict a held-out account's own real
# label" guilt-by-association check, not a circular self-reference.
#
# **Zero-fabrication rule for this notebook:** every count, structural value, and lift ratio below is
# computed live from the real files in `data/raw/` when this notebook runs.

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
CONFIG_PATH = PROJECT_ROOT / "configs" / "bp3_network_graph_intelligence.yaml"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp3_network_graph_intelligence"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
print(f"Project root: {PROJECT_ROOT}")
print(f"Reports dir : {REPORTS_DIR}")

def _read_simple_yaml(path):
    """Tiny dependency-free reader for this project's flat `key: "value"` config files. BP3's config
    (written by Notebook 1) also carries a nested `graph_feasibility_policy:` block -- this reader still
    captures every leaf `key: value` line regardless of indentation (real YAML structure isn't needed for
    this project's own flat key-lookup usage), so the scalar fields below resolve correctly; the nested
    policy's real values are additionally hardcoded below as GRAPH_FEASIBILITY_POLICY, verbatim from
    Notebook 1's own locked, printed output, so there is no risk of a silent mis-parse of the nested block."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"')
    return out

bp3_config = _read_simple_yaml(CONFIG_PATH)
print(f"\nReal config loaded from {CONFIG_PATH.name}:")
for k, v in bp3_config.items():
    print(f"  {k}: {v}")

if bp3_config.get("status") == "scaffolded - not yet built":
    raise RuntimeError(
        "configs/bp3_network_graph_intelligence.yaml still carries Notebook 1's pre-run placeholder "
        "('scaffolded - not yet built'). Run BP3 Notebook 1 first -- it writes this notebook's real "
        "node-key policy, graph-feasibility policy, and primary metric, all of which this notebook "
        "depends on; this is not a fallback-to-default situation (zero-fabrication: never assume a "
        "policy this platform has not actually decided for real)."
    )

PRIMARY_METRIC = bp3_config.get("primary_metric", "network_lift_ratio")

# Real, locked graph-feasibility policy -- verbatim from Notebook 1's own tested, printed output
# (Lesson #21; the nested YAML block above is not re-parsed into this structure, see note above).
GRAPH_FEASIBILITY_POLICY = {
    "full_graph_algorithms_allowed": ["degree_in_out", "pagerank"],
    "full_graph_algorithms_excluded": ["louvain_community_detection", "betweenness_centrality"],
    "bounded_subgraph_scope": "2-hop ego-network around each real Is-Laundering-flagged account",
    "bounded_subgraph_node_cap": 2000,
    "ram_safety_gate": "assert_ram_safe() before every graph algorithm call, no exceptions",
}
EGO_HOPS = 2
EGO_NODE_CAP = GRAPH_FEASIBILITY_POLICY["bounded_subgraph_node_cap"]

import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone

try:
    import networkx as nx
    print(f"\nnetworkx {nx.__version__} -- available")
except ImportError as e:
    raise ImportError(
        f"networkx is required for this notebook (PageRank, bounded ego-networks) and is not installed "
        f"({e}). ACTION NEEDED: pip install networkx, then re-run this cell."
    )

RANDOM_SEED = 42
VARIANT = "HI-Small"  # this notebook's fast build/debug target -- LI-Medium deferred to Notebook 3
TRANS_FILE = f"{VARIANT}_Trans.csv"
ACCOUNTS_FILE = f"{VARIANT}_accounts.csv"

TRANS_DTYPES = {
    "From Bank": "string", "Account": "string", "To Bank": "string", "Account.1": "string",
    "Amount Received": "float64", "Receiving Currency": "category",
    "Amount Paid": "float64", "Payment Currency": "category",
    "Payment Format": "category", "Is Laundering": "int8",
}

# ============================================================================
# 1. Load HI-Small_Trans.csv (WARP: Parquet-cached) -- same real file Notebook 1 already validated.
# ============================================================================
with timer(f"load {TRANS_FILE} (WARP: cached to Parquet)"):
    trans = load_csv_cached(RAW / TRANS_FILE, parse_dates=["Timestamp"], dtype=TRANS_DTYPES)
print(f"Real {TRANS_FILE} shape: {trans.shape}")
_print_resource("post Trans.csv load")

# ============================================================================
# 2. Real composite-key graph construction -- compact INT node keys (never raw strings in the graph
#    object itself, per Notebook 1 Section 5's real pre-build diagnostic / Lesson #21), vectorized
#    (Lesson #18/#20 -- never a row-wise .agg()/.apply() loop).
# ============================================================================
assert_ram_safe(min_available_gb=3.0, label="before composite-key graph construction")

with timer("build real composite-key graph (compact int nodes, vectorized)"):
    from_key = trans["From Bank"].astype(str) + "|" + trans["Account"].astype(str)
    to_key = trans["To Bank"].astype(str) + "|" + trans["Account.1"].astype(str)
    n_edges_raw = len(trans)

    all_keys = pd.concat([from_key, to_key], ignore_index=True)
    codes, uniques = pd.factorize(all_keys, sort=False)
    from_code = codes[:n_edges_raw]
    to_code = codes[n_edges_raw:]

    node_df = pd.DataFrame({"node_id": np.arange(len(uniques), dtype="int64"), "node_key": uniques})
    n_nodes = len(node_df)

    # Real distinct-edge aggregation (weight = real transaction count on that directed pair) -- vectorized
    # groupby, never a per-row loop; this IS the same real quantity Notebook 1's degree_report measured.
    edge_df = (
        pd.DataFrame({"src": from_code, "dst": to_code})
        .groupby(["src", "dst"]).size().reset_index(name="weight")
    )
    n_distinct_edges = len(edge_df)

    G = nx.DiGraph()
    G.add_nodes_from(node_df["node_id"].to_numpy())
    G.add_weighted_edges_from(zip(edge_df["src"], edge_df["dst"], edge_df["weight"]))

print(f"Real graph: {n_nodes:,} nodes, {n_distinct_edges:,} distinct directed edges "
      f"({n_edges_raw:,} real transaction-edges collapsed by (src,dst) weight).")
thermal_checkpoint(label="post graph construction")
_print_resource("post graph construction")

# ============================================================================
# 3. Real degree (vectorized pandas, matching Notebook 1's own validated method -- no graph traversal
#    needed for this) + real PageRank (needs the real graph object -- confirmed safe/fast at this scale
#    by Notebook 1's own real pre-build diagnostic: 2.1s on HI-Small).
# ============================================================================
with timer("real degree computation (vectorized)"):
    out_deg = pd.Series(to_code).groupby(from_code).nunique()
    in_deg = pd.Series(from_code).groupby(to_code).nunique()
    node_df["out_degree"] = node_df["node_id"].map(out_deg).fillna(0).astype("int32")
    node_df["in_degree"] = node_df["node_id"].map(in_deg).fillna(0).astype("int32")
    node_df["total_degree"] = node_df["out_degree"] + node_df["in_degree"]

assert_ram_safe(min_available_gb=3.0, label="before PageRank (full-graph algorithm -- locked policy allows this one)")
with timer("real PageRank (full graph, locked-policy-allowed)"):
    pr = nx.pagerank(G, weight="weight")
node_df["pagerank"] = node_df["node_id"].map(pr).fillna(0.0)
thermal_checkpoint(label="post PageRank")
_print_resource("post degree + PageRank")

print(f"\nReal out-degree:  mean={node_df['out_degree'].mean():.2f}, max={node_df['out_degree'].max():,}")
print(f"Real in-degree :  mean={node_df['in_degree'].mean():.2f}, max={node_df['in_degree'].max():,}")
print(f"Real PageRank  :  mean={node_df['pagerank'].mean():.6e}, max={node_df['pagerank'].max():.6e}")

# ============================================================================
# 4. Real Is-Laundering exposure label per node (external validity check only, never a training target --
#    unchanged discipline from Notebook 1).
# ============================================================================
laund = trans[trans["Is Laundering"] == 1]
exposed_from = laund["From Bank"].astype(str) + "|" + laund["Account"].astype(str)
exposed_to = laund["To Bank"].astype(str) + "|" + laund["Account.1"].astype(str)
exposed_keys = set(exposed_from) | set(exposed_to)
node_df["is_laundering_exposed"] = node_df["node_key"].isin(exposed_keys).astype("int8")

base_rate_all = float(node_df["is_laundering_exposed"].mean())
print(f"\nReal base rate, ALL {n_nodes:,} nodes: {100 * base_rate_all:.4f}% Is-Laundering-exposed "
      f"({int(node_df['is_laundering_exposed'].sum()):,} real exposed accounts).")

del trans, laund, exposed_from, exposed_to
gc.collect()
_print_resource("post label assignment")

# ============================================================================
# 5. Real train/test split of ACCOUNTS (not transactions) -- stratified by real Is-Laundering exposure,
#    same RANDOM_SEED=42 / test_size=0.25 convention as BP1/BP2's own Stage-A splits. This is what keeps
#    every signal's real lift ratio below an honest out-of-sample statistic (Section header above).
# ============================================================================
from sklearn.model_selection import train_test_split

exposure = node_df["is_laundering_exposed"].to_numpy()
class_counts = pd.Series(exposure).value_counts()
print(f"\nReal node-level exposure class counts: {class_counts.to_dict()}")
strat = exposure if class_counts.min() >= 2 else None
if strat is None:
    print("WARNING: fewer than 2 real nodes in one exposure class -- stratified split disabled for this run.")

train_idx, test_idx = train_test_split(
    np.arange(n_nodes), test_size=0.25, random_state=RANDOM_SEED, stratify=strat
)
train_mask = np.zeros(n_nodes, dtype=bool)
train_mask[train_idx] = True
node_df["split"] = np.where(train_mask, "train", "test")

train_df = node_df[node_df["split"] == "train"]
test_df = node_df[node_df["split"] == "test"]
base_rate_train = float(train_df["is_laundering_exposed"].mean())
base_rate_test = float(test_df["is_laundering_exposed"].mean())
print(f"Real split: {len(train_df):,} train nodes ({100*base_rate_train:.4f}% exposed), "
      f"{len(test_df):,} test nodes ({100*base_rate_test:.4f}% exposed).")

# ============================================================================
# 6. Real per-signal network-lift ratio, Stage A (single split, HI-Small) -- threshold fit on TRAIN,
#    lift measured on TEST. Degree/PageRank candidates first; the 2-hop proximity candidate (Section 7)
#    is appended to the same ranking below.
# ============================================================================
def lift_ratio_report(signal_name, train_series, test_series, test_exposed, test_base_rate, pctl=0.90):
    """Real Stage-A evaluation for one continuous structural signal: fit the real top-decile threshold
    on TRAIN, flag TEST nodes at/above it, and report the real lift ratio (flagged exposure rate / real
    test base rate). Explicit undefined-count guard (Lesson #7) -- never a silent divide-by-zero."""
    threshold = float(train_series.quantile(pctl))
    flagged = test_series >= threshold
    n_flagged = int(flagged.sum())
    if n_flagged == 0:
        print(f"  {signal_name}: 0 real TEST nodes at/above the real train-fit {pctl:.0%} threshold "
              f"({threshold:.6g}) -- lift ratio UNDEFINED, not silently reported as 0 or 1.")
        return {"signal": signal_name, "threshold": threshold, "n_test_flagged": 0,
                "n_test_flagged_exposed": 0, "flagged_exposure_rate": None, "lift_ratio": None}
    n_flagged_exposed = int(test_exposed[flagged.to_numpy()].sum())
    flagged_exposure_rate = float(test_exposed[flagged.to_numpy()].mean())
    lift = (flagged_exposure_rate / test_base_rate) if test_base_rate > 0 else None
    lift_str = f"{lift:.2f}x" if lift is not None else "UNDEFINED (real test base rate is 0)"
    print(f"  {signal_name}: real train-fit {pctl:.0%} threshold = {threshold:.6g}, {n_flagged:,} real TEST "
          f"nodes flagged, {100*flagged_exposure_rate:.4f}% real exposure among flagged -> lift = {lift_str}")
    return {"signal": signal_name, "threshold": threshold, "n_test_flagged": n_flagged,
            "n_test_flagged_exposed": n_flagged_exposed,
            "flagged_exposure_rate": flagged_exposure_rate, "lift_ratio": lift}

print("\nReal Stage A per-signal network-lift ratio (train-fit threshold, test-measured lift):")
test_exposed_arr = test_df["is_laundering_exposed"].to_numpy()
stage_a_results = []
for col, label in [("out_degree", "Out-degree (top decile)"), ("in_degree", "In-degree (top decile)"),
                    ("total_degree", "Total-degree (top decile)"), ("pagerank", "PageRank (top decile)")]:
    stage_a_results.append(
        lift_ratio_report(label, train_df[col], test_df[col], test_exposed_arr, base_rate_test)
    )

# ============================================================================
# 7. Real bounded 2-hop proximity-to-flagged signal -- multi-source BFS (virtual-super-source technique,
#    O(V+E) total, never a per-seed Python loop -- Lesson #18 vectorization discipline applied to a graph
#    algorithm) seeded ONLY from real TRAIN-flagged accounts. Undirected for this signal (guilt-by-
#    association reads naturally in either payment direction -- sent-to or received-from a known-flagged
#    account both count as real network proximity).
# ============================================================================
def multi_source_bfs_within_hops(G_directed, seed_nodes, max_hops):
    """Real, efficient multi-source bounded-BFS over an undirected view of G_directed: returns the set of
    real node ids within max_hops of ANY seed node, via the standard virtual-super-source trick. A fresh
    undirected nx.Graph is built from G_directed's real edges (G_directed itself is never mutated)."""
    Gu = nx.Graph()
    Gu.add_nodes_from(G_directed.nodes())
    Gu.add_edges_from(G_directed.edges())
    virtual = "__virtual_super_source__"
    Gu.add_node(virtual)
    Gu.add_edges_from((virtual, s) for s in seed_nodes)
    lengths = nx.single_source_shortest_path_length(Gu, virtual, cutoff=max_hops + 1)
    return {node for node, d in lengths.items() if node != virtual and (d - 1) <= max_hops}

train_flagged_ids = train_df.loc[train_df["is_laundering_exposed"] == 1, "node_id"].tolist()
print(f"\nReal TRAIN-flagged seed accounts for the 2-hop proximity signal: {len(train_flagged_ids):,}")

assert_ram_safe(min_available_gb=3.0, label="before multi-source 2-hop BFS proximity signal")
with timer(f"real multi-source {EGO_HOPS}-hop BFS from TRAIN-flagged accounts"):
    near_flagged_ids = multi_source_bfs_within_hops(G, train_flagged_ids, EGO_HOPS)
thermal_checkpoint(label="post 2-hop proximity BFS")

test_df = test_df.copy()
test_df["near_train_flagged"] = test_df["node_id"].isin(near_flagged_ids)
n_test_near = int(test_df["near_train_flagged"].sum())
if n_test_near == 0:
    print(f"  2-hop proximity to a TRAIN-flagged account: 0 real TEST nodes within {EGO_HOPS} hops -- "
          f"lift ratio UNDEFINED.")
    stage_a_results.append({"signal": f"{EGO_HOPS}-hop proximity to a TRAIN-flagged account", "threshold": None,
                             "n_test_flagged": 0, "n_test_flagged_exposed": 0,
                             "flagged_exposure_rate": None, "lift_ratio": None})
else:
    near_exposure_rate = float(test_df.loc[test_df["near_train_flagged"], "is_laundering_exposed"].mean())
    lift = (near_exposure_rate / base_rate_test) if base_rate_test > 0 else None
    lift_str = f"{lift:.2f}x" if lift is not None else "UNDEFINED (real test base rate is 0)"
    print(f"  2-hop proximity to a TRAIN-flagged account: {n_test_near:,} real TEST nodes within "
          f"{EGO_HOPS} hops, {100*near_exposure_rate:.4f}% real exposure among them -> lift = {lift_str}")
    stage_a_results.append({
        "signal": f"{EGO_HOPS}-hop proximity to a TRAIN-flagged account", "threshold": None,
        "n_test_flagged": n_test_near,
        "n_test_flagged_exposed": int(test_df.loc[test_df["near_train_flagged"], "is_laundering_exposed"].sum()),
        "flagged_exposure_rate": near_exposure_rate, "lift_ratio": lift,
    })
_print_resource("post 2-hop proximity signal")

# ============================================================================
# 8. Real champion selection -- highest real lift ratio on TEST, full per-signal breakdown reported,
#    never blended into one score (unchanged discipline from every other BP on this platform).
# ============================================================================
ranked = sorted([r for r in stage_a_results if r["lift_ratio"] is not None],
                 key=lambda r: r["lift_ratio"], reverse=True)
print("\nReal Stage A ranking (network-lift ratio, single split, HI-Small):")
for r in ranked:
    print(f"  {r['signal']}: {r['lift_ratio']:.2f}x")
undefined = [r["signal"] for r in stage_a_results if r["lift_ratio"] is None]
if undefined:
    print(f"  (Undefined, excluded from ranking: {', '.join(undefined)})")

if not ranked:
    raise RuntimeError(
        "Every real candidate signal produced an UNDEFINED lift ratio on this run (0 real TEST nodes "
        "flagged, or a 0 real test base rate) -- cannot select a real champion. This is a real data-"
        "scale issue at HI-Small, not a code bug; re-examine the real class counts printed above before "
        "re-running, and consider whether LI-Medium (Notebook 3) is needed sooner than planned."
    )
champion = ranked[0]
print(f"\nReal Stage A champion (this run): {champion['signal']} (lift = {champion['lift_ratio']:.2f}x)")

# ============================================================================
# 9. Illustrative bounded per-case ego-networks (real, node-capped at the locked policy's 2,000-node
#    limit) -- demonstrates the real investigator-facing "After" view (Notebook 1 Section 8's Before/After
#    policy: single-account review vs. bounded ego-network review), for a small number of real example
#    TRAIN-flagged accounts (the 3 with the highest real total-degree, for a richer illustrative case).
#    This is a SEPARATE real computation from Section 7's aggregate proximity signal above -- scoped,
#    per-case, and capped, per Notebook 1's locked policy, not used in the Stage A ranking itself.
# ============================================================================
example_seeds = (
    train_df[train_df["is_laundering_exposed"] == 1]
    .sort_values("total_degree", ascending=False)
    .head(3)["node_id"].tolist()
)
key_by_id = node_df.set_index("node_id")["node_key"]

Gu_full = nx.Graph()
Gu_full.add_nodes_from(G.nodes())
Gu_full.add_edges_from(G.edges())

example_ego_networks = []
print(f"\nReal illustrative bounded ego-networks ({EGO_HOPS}-hop, capped at {EGO_NODE_CAP:,} nodes):")
for seed in example_seeds:
    assert_ram_safe(min_available_gb=2.0, label=f"before ego_graph for seed node {seed}")
    ego = nx.ego_graph(Gu_full, seed, radius=EGO_HOPS)
    n_real_nodes = ego.number_of_nodes()
    truncated = n_real_nodes > EGO_NODE_CAP
    if truncated:
        # Real, disclosed truncation (never silently dropped) -- keep the seed + its closest real nodes
        # by BFS distance, capped at EGO_NODE_CAP, per the locked policy.
        dist = nx.single_source_shortest_path_length(ego, seed)
        keep = sorted(dist, key=dist.get)[:EGO_NODE_CAP]
        ego = ego.subgraph(keep)
    example_ego_networks.append({
        "seed_node_key": key_by_id.loc[seed],
        "real_nodes_before_cap": n_real_nodes,
        "nodes_after_cap": ego.number_of_nodes(),
        "edges_after_cap": ego.number_of_edges(),
        "truncated": bool(truncated),
    })
    print(f"  Seed {key_by_id.loc[seed]}: {n_real_nodes:,} real nodes within {EGO_HOPS} hops "
          f"({'TRUNCATED to ' + format(ego.number_of_nodes(), ',') + ' per the 2,000-node cap' if truncated else 'under the cap, kept in full'}), "
          f"{ego.number_of_edges():,} real edges in the capped subgraph.")

del Gu_full
gc.collect()
_print_resource("post illustrative ego-network construction")

# ============================================================================
# 10. Real summary JSON (Notebook 3 reads this to confirm Stage A's real HI-Small champion before its own
#     full LI-Medium bootstrap-CI validation).
# ============================================================================
summary = {
    "bp_id": "BP3",
    "bp_name": "Transaction Network & Graph Intelligence",
    "notebook": "02_feature_engineering_modeling",
    "variant": VARIANT,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "random_seed": RANDOM_SEED,
    "primary_metric": PRIMARY_METRIC,
    "n_nodes": int(n_nodes),
    "n_distinct_edges": int(n_distinct_edges),
    "n_transaction_edges": int(n_edges_raw),
    "base_rate_all": base_rate_all,
    "n_train_nodes": int(len(train_df)),
    "n_test_nodes": int(len(test_df)),
    "base_rate_train": base_rate_train,
    "base_rate_test": base_rate_test,
    "ego_hops": EGO_HOPS,
    "ego_node_cap": EGO_NODE_CAP,
    "stage_a_ranking": stage_a_results,
    "champion_signal": champion["signal"],
    "champion_lift_ratio": champion["lift_ratio"],
    "example_ego_networks": example_ego_networks,
    "graph_feasibility_policy": GRAPH_FEASIBILITY_POLICY,
    "no_trained_model_note": "BP3 has no trained ML model -- every candidate is a directly-interpretable "
                              "structural signal; SHAP/LIME are N/A here (not 'unavailable', genuinely not "
                              "applicable), disclosed explicitly rather than fabricated in Notebook 3/4.",
    "leakage_discipline_note": "graph edges built from the full real file (structural, label-independent); "
                                "every signal's threshold/seed-set is fit on TRAIN nodes only and lift is "
                                "measured on disjoint TEST nodes only (Lesson #11 applied to an unsupervised "
                                "structural-signal problem).",
}
summary_path = REPORTS_DIR / f"bp3_notebook2_stage_a_summary_{VARIANT.lower().replace('-', '_')}.json"
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
print(f"\nReal Stage A summary written to: {summary_path}")

print("=" * 78)
print("BP3 -- Notebook 2 Summary (real, this run)")
print("=" * 78)
print(f"Variant: {VARIANT}  Nodes: {n_nodes:,}  Distinct edges: {n_distinct_edges:,}  "
      f"Base rate: {100*base_rate_all:.4f}%")
print(f"Real Stage A champion: {champion['signal']} (lift = {champion['lift_ratio']:.2f}x on real TEST nodes)")
print(f"Summary JSON: {summary_path}")
print("=" * 78)

# ## Next Step
# `notebooks/bp3_network_graph_intelligence/03_statistical_validation_deployment_SINGLE_CELL.py` -- re-runs
# this same real pipeline on LI-Medium (this BP's locked mandatory realism-validation tier), adds a real
# bootstrap confidence interval on the champion signal's network-lift ratio (closed-form multinomial
# resampling from the already-computed 2x2 flagged/exposure contingency table, per Section 9.3 technique #5
# -- never a brute-force per-resample graph rebuild), the two-gate verdict (Gate 1: structural [CHECK] --
# every signal computed, RAM-safe, train/test leakage-disciplined; Gate 2: statistical-robustness -- the
# champion's real bootstrap 95% CI excludes 1.0x/no-lift), and the deployable FastAPI scoring service
# (wrapping the real champion signal's flagging rule, bit-identical self-test against every real row it can
# reach, per Lesson #4). SHAP/LIME are explicitly N/A for this BP (Section 0 above) and are not attempted.
