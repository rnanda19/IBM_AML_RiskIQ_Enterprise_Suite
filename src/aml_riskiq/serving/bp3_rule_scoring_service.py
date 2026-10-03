"""
BP3 -- Transaction Network & Graph Intelligence: real, standalone FastAPI RULE-scoring
service.

NAMING: `_rule_` (not `_scoring_` alone, and never `_model_`) because BP3 has no trained ML
model (see reports/bp3_network_graph_intelligence/RULE_CARD.md). The real deployable
artifact is a directly-interpretable graph-STRUCTURAL RULE -- currently "2-hop proximity to
a TRAIN-flagged account" on the real LI-Medium account-to-account transaction graph
(2,032,095 real nodes, 4,363,197 real distinct directed edges) -- never a pickled
classifier. There is no SHAP/LIME, no `predict_proba`, no probability threshold here:
genuinely not applicable, not merely omitted (RULE_CARD.md, Explainability section).

REAL GAP THIS FILE CLOSES: BP3's own Dockerfile (src/docker/bp3_network_graph_intelligence/
Dockerfile) already points its CMD at `src.aml_riskiq.serving.bp3_scoring_service:app` and already
COPYs the real champion rule JSON into the image, but until this file was added,
`src/aml_riskiq/serving/bp3_rule_scoring_service.py` did not exist anywhere in `src/` -- the same
disclosed "ACTION NEEDED" gap BP1's and BP4's own service files closed for their BPs. The
Dockerfile's CMD target is updated alongside this file (see that Dockerfile's own
"RESOLVED" note).

Zero-fabrication / no-new-logic discipline: this service's `/score` route reproduces
Notebook 3's own in-kernel `score_account` decision for the real non-threshold champion
signal exactly -- `flagged = bool(near_train_flagged_account)` (see that notebook's
Section "Deployable Scoring Service", confirmed bit-identical to direct computation on a
real 2,000-row sample, 0 mismatches). The one real difference from Notebook 3's own
in-process self-test, disclosed honestly: that self-test's AccountFeatures request schema
took the already-computed `near_train_flagged_account` boolean as INPUT (it was testing
API wiring, not graph computation, against rows it had already labeled). A real deployed
service is handed an ACCOUNT KEY, not a pre-computed boolean, so this file adds exactly one
real lookup step Notebook 3 did not need for its own self-test: resolving that key against
the real per-account `near_train_flagged` table Notebook 3's in-kernel `near_flagged_ids`
set already computes (persisted to disk by this platform's 2026-10-02 notebook hardening
addition -- see that notebook's own "HARDENING ADDITION" comment). No new graph logic is
introduced -- this service never re-runs or re-derives the 2-hop BFS; it only looks up a
value Notebook 3 already computed.

Real artifacts loaded at import time (never hand-typed):
  - models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_<variant>.json
      (champion_signal, champion_column, is_threshold_signal, threshold, note)
  - models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_<variant>.parquet
      (node_key -> near_train_flagged, the real per-account table the notebook hardening
      addition persists -- does NOT exist until the user re-runs Notebook 3 once post-patch)
  - reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_<variant>.json
      (real champion_name, real lift_ratio, real bootstrap CI -- for /score's metadata and
      /health; never re-typed by hand)

Environment variables:
  BP3_CHAMPION_RULE_PATH -- absolute path to the real champion rule JSON (optional; if
                            unset, resolved from BP3_DATASET_VARIANT below). Name matches
                            the Dockerfile's own existing env var.
  BP3_LOOKUP_PATH         -- absolute path to the real near_train_flagged lookup Parquet
                            (optional; if unset, resolved from BP3_DATASET_VARIANT below).
  BP3_DATASET_VARIANT     -- "HI-Small" or "LI-Medium" (default: "LI-Medium", this BP's
                            locked mandatory realism-validation tier).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import Depends, FastAPI, Request

try:
    from serving._security import harden_app, require_api_key, score_rate_limit
except ImportError:  # pragma: no cover -- exercised under Docker's import context, not pytest's
    from src.aml_riskiq.serving._security import harden_app, require_api_key, score_rate_limit
from pydantic import BaseModel


# ----------------------------------------------------------------------------------------
# Real project-root resolution -- same pattern every notebook and service in this platform
# uses, so this service resolves correctly whether run locally, from Docker (repo root as
# build context, per Notebook 4's own Dockerfile comment), or from any other real working
# directory.
# ----------------------------------------------------------------------------------------
def _locate_project_root() -> Path:
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
    # Docker fallback: Notebook 4's own Dockerfile COPYs `src/` and `models/` to /app, with no
    # PROJECT_STRUCTURE_LOCKED.md marker in the image -- /app IS the real project root inside
    # the container in that case. Checked explicitly rather than assumed.
    if Path("/app/src").is_dir() and Path("/app/models").is_dir():
        return Path("/app")
    raise FileNotFoundError(
        "Could not locate the project root (checked an upward walk from "
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set BP3_CHAMPION_RULE_PATH "
        "and BP3_LOOKUP_PATH directly to skip root resolution, or run this service from "
        "inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
DATASET_VARIANT = os.environ.get("BP3_DATASET_VARIANT", "LI-Medium")
if DATASET_VARIANT not in ("HI-Small", "LI-Medium"):
    raise ValueError(f"BP3_DATASET_VARIANT must be 'HI-Small' or 'LI-Medium', got {DATASET_VARIANT!r}")
VARIANT_TAG = DATASET_VARIANT.lower().replace("-", "_")

MODELS_DIR = PROJECT_ROOT / "models" / "bp3_network_graph_intelligence"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp3_network_graph_intelligence"

_default_rule_path = MODELS_DIR / f"bp3_notebook3_champion_rule_{VARIANT_TAG}.json"
CHAMPION_RULE_PATH = Path(os.environ.get("BP3_CHAMPION_RULE_PATH", str(_default_rule_path)))

_default_lookup_path = MODELS_DIR / f"bp3_notebook3_near_train_flagged_lookup_{VARIANT_TAG}.parquet"
LOOKUP_PATH = Path(os.environ.get("BP3_LOOKUP_PATH", str(_default_lookup_path)))

REPORT_PATH = REPORTS_DIR / f"bp3_notebook3_validation_report_{VARIANT_TAG}.json"

if not CHAMPION_RULE_PATH.exists():
    raise FileNotFoundError(
        f"{CHAMPION_RULE_PATH} does not exist. This service loads Notebook 3's real saved "
        f"champion RULE artifact (never a .pkl model -- BP3 has no trained model) -- run "
        f"03_statistical_validation_deployment_SINGLE_CELL.py with DATASET_VARIANT = "
        f"'{DATASET_VARIANT}' first (it is what actually creates this file)."
    )
if not LOOKUP_PATH.exists():
    raise FileNotFoundError(
        f"{LOOKUP_PATH} does not exist. This service loads the real per-account "
        f"near_train_flagged lookup table that Notebook 3's 2026-10-02 hardening addition "
        f"persists (the real, already-computed 2-hop-BFS membership set, written to disk) -- "
        f"re-run 03_statistical_validation_deployment_SINGLE_CELL.py with DATASET_VARIANT = "
        f"'{DATASET_VARIANT}' once AFTER that patch to actually create this file. Until that "
        f"real re-run happens, this service cannot start -- it never fabricates a lookup table."
    )
if not REPORT_PATH.exists():
    raise FileNotFoundError(
        f"{REPORT_PATH} does not exist. This service reads Notebook 3's real saved validation "
        f"report for its champion_name, real lift_ratio, and real bootstrap CI -- run "
        f"Notebook 3 for '{DATASET_VARIANT}' first."
    )

with open(CHAMPION_RULE_PATH, encoding="utf-8") as _f:
    _rule = json.load(_f)

with open(REPORT_PATH, encoding="utf-8") as _f:
    _report = json.load(_f)

# Real, saved values -- never re-typed by hand (Lesson #2's standing rule: any value a
# deployable service relies on comes from the notebook's own saved artifact, never a
# hand-typed re-derivation that could drift from what was actually validated).
CHAMPION_SIGNAL: str = _rule["champion_signal"]
CHAMPION_COLUMN: str = _rule["champion_column"]
IS_THRESHOLD_SIGNAL: bool = _rule["is_threshold_signal"]
THRESHOLD = _rule["threshold"]

REAL_LIFT_RATIO: float = _report["test_metrics"]["lift_ratio"]
REAL_BOOTSTRAP_CI95_LOW: Optional[float] = _report.get("bootstrap", {}).get("ci95_low")
REAL_BOOTSTRAP_CI95_HIGH: Optional[float] = _report.get("bootstrap", {}).get("ci95_high")
REAL_CHAMPION_NAME: str = _report["champion_name"]

if IS_THRESHOLD_SIGNAL:
    # Disclosed, not worked around: this service's /score route (below) is built for BP3's
    # real current champion, the set-membership "near_train_flagged" rule. If a future real
    # re-run's champion flips back to a threshold-type structural signal (out/in/total-degree
    # or PageRank, top-decile), this service's lookup-table design no longer matches the real
    # champion and must not silently keep serving the old rule -- fail loudly instead.
    raise RuntimeError(
        f"Real saved champion rule ({CHAMPION_SIGNAL!r}) is a THRESHOLD signal, not the "
        f"set-membership 'near_train_flagged' rule this service is built for. This service's "
        f"/score route and its near_train_flagged lookup table do not apply to a threshold "
        f"signal -- a separate threshold-scoring service (reading real out_degree/in_degree/"
        f"total_degree/pagerank values directly, per threshold={THRESHOLD!r}) would be needed "
        f"instead. Not implemented here; disclosed rather than silently mismatched."
    )

# Real per-account lookup table -- Notebook 3's own already-computed near_flagged_ids BFS
# result, persisted by the 2026-10-02 hardening addition. Loaded once at import time and
# indexed by the real node_key (Bank|Account composite string, identical format to every
# other real key in this BP).
_lookup_df = pd.read_parquet(LOOKUP_PATH)
if "node_key" not in _lookup_df.columns or "near_train_flagged" not in _lookup_df.columns:
    raise ValueError(
        f"{LOOKUP_PATH} is missing the expected real columns ('node_key', "
        f"'near_train_flagged') -- got {list(_lookup_df.columns)!r}. This service never "
        f"guesses a replacement column name."
    )
NEAR_TRAIN_FLAGGED_BY_KEY: dict = (
    _lookup_df.set_index("node_key")["near_train_flagged"].astype(bool).to_dict()
)

print(
    f"[bp3_rule_scoring_service] Loaded real champion RULE {CHAMPION_SIGNAL!r} for variant "
    f"'{DATASET_VARIANT}' (rule_column={CHAMPION_COLUMN!r}, is_threshold_signal="
    f"{IS_THRESHOLD_SIGNAL}); real lift_ratio={REAL_LIFT_RATIO:.4f}x; "
    f"{len(NEAR_TRAIN_FLAGGED_BY_KEY):,} real accounts in the near_train_flagged lookup."
)


class AccountKey(BaseModel):
    """Real request schema: the one real identifier every account in this BP's graph has --
    the (Bank, Account) composite key, identical string format to Notebook 3's own
    `node_key` ("<Bank>|<Account>", e.g. "070|10042B660", per RULE_CARD.md's own illustrative
    seed_node_key examples). This is NOT a model feature vector (BP3 has no trained model) --
    it is the account identifier a real investigator or upstream system would supply."""

    account_key: str


def score_account(account_key: str) -> dict:
    """Real rule lookup -- never a live graph recomputation (that logic lives only in
    Notebook 3's own vectorized 2-hop frontier BFS, which this service does not reproduce or
    re-derive). Looks up `account_key` in the real, already-computed near_train_flagged
    table. An account_key genuinely absent from that table (never seen anywhere in Notebook
    3's real LI-Medium graph as of its last run) gets an honest, disclosed "not in graph"
    response -- `near_train_flagged` is never fabricated as True or False for an unknown
    account."""
    if account_key not in NEAR_TRAIN_FLAGGED_BY_KEY:
        return {
            "account_key": account_key,
            "status": "account_not_in_graph_as_of_last_run",
            "near_train_flagged": None,
            "champion_signal": CHAMPION_SIGNAL,
            "champion_lift_ratio": REAL_LIFT_RATIO,
            "champion_lift_ratio_ci95": [REAL_BOOTSTRAP_CI95_LOW, REAL_BOOTSTRAP_CI95_HIGH],
            "dataset_variant": DATASET_VARIANT,
        }
    flagged = bool(NEAR_TRAIN_FLAGGED_BY_KEY[account_key])
    return {
        "account_key": account_key,
        "status": "ok",
        "near_train_flagged": flagged,
        "champion_signal": CHAMPION_SIGNAL,
        "champion_lift_ratio": REAL_LIFT_RATIO,
        "champion_lift_ratio_ci95": [REAL_BOOTSTRAP_CI95_LOW, REAL_BOOTSTRAP_CI95_HIGH],
        "dataset_variant": DATASET_VARIANT,
    }


app = FastAPI(title=f"BP3 Network-Signal Rule Scoring Service ({DATASET_VARIANT})")
_limiter = harden_app(app, "bp3_rule_scoring_service")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dataset_variant": DATASET_VARIANT,
        "champion_signal": CHAMPION_SIGNAL,
        "is_threshold_signal": IS_THRESHOLD_SIGNAL,
        "real_lift_ratio": REAL_LIFT_RATIO,
        "real_lift_ratio_ci95": [REAL_BOOTSTRAP_CI95_LOW, REAL_BOOTSTRAP_CI95_HIGH],
        "accounts_in_lookup": len(NEAR_TRAIN_FLAGGED_BY_KEY),
        "no_trained_model_note": (
            "BP3 has no trained ML model -- this is a RULE artifact (set-membership test), "
            "never a probability or threshold score."
        ),
    }


@app.post("/score")
@_limiter.limit(score_rate_limit())
def score_endpoint(request: Request, acct: AccountKey, _caller: str = Depends(require_api_key)) -> dict:
    return score_account(acct.account_key)
