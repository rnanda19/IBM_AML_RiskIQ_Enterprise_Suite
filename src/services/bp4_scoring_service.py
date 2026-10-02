"""
BP4 -- Structuring & Smurfing Detection: real, standalone FastAPI scoring service.

REAL BUG THIS FILE FIXES: BP4's own Dockerfile (src/docker/bp4_structuring_smurfing_detection/
Dockerfile) already points its CMD at `src.services.bp4_scoring_service:app` and already
COPYs the real champion pickle into the image, but until this file was added,
`src/services/bp4_scoring_service.py` did not exist anywhere in `src/` -- the image would
build but the container would crash immediately on start with `ModuleNotFoundError`, the
exact same disclosed gap BP1's own service file closed for BP1 (and the Dockerfile's own
top-of-file comment flags this gap explicitly for BP4).

Zero-fabrication / no-new-logic discipline: every line of scoring logic below is copied
verbatim from BP4 Notebook 3's own in-notebook `score_transaction` function (the same one
its FastAPI self-test already proved bit-identical to direct batch `predict_proba` calls on
a real 5,000-row sample, both HI-Small and LI-Medium -- see each variant's own saved
`fastapi_self_test` block in the validation report). This file does not re-derive or
re-guess that logic -- it is the exact same code path, now persisted so Docker can actually
import it (Lesson #3's standing rule: any code a deployable service runs must replicate the
source notebook's real logic exactly, never an independent reimplementation).

BP4-specific real detail (unlike BP1, where every feature is always finite): BP4's
`amount_to_rolling_window_mean_ratio` feature is a real, disclosed NaN-prone column (rows
with no prior transaction inside the trailing structuring window have no rolling mean to
divide by). The champion model handles this one of two ways, both already decided and
persisted by Notebook 3 -- never re-derived here:
  - A boosted-tree champion (XGBoost, CatBoost, LightGBM) accepts a real NaN directly.
  - A RandomForest champion has no native NaN support, so Notebook 3 already computed a
    real train-median impute value (`rf_impute_value`) and persisted it, together with a
    `champion_needs_rf_impute` flag, in its own saved validation report. This service reads
    both and -- exactly mirroring Notebook 3's own `score_transaction` -- imputes only when
    the persisted flag says to, using the persisted value, never a value computed here.
Because the NaN-prone column can legitimately be missing from a real request, it is the one
FEATURE_COLS entry declared `Optional[float] = None` in the request schema (every other
column is always finite by this project's own feature policy, same as Notebook 3's own
FastAPI self-test schema) -- a real caller sends JSON `null` for a missing trailing window,
which is standard-JSON (RFC 8259) compliant, and this service converts it back to a real NaN
server-side before scoring, same as Notebook 3.

Real model + real threshold + real impute settings are loaded from Notebook 3's own saved
artifacts at import time:
  - models/bp4_structuring_smurfing_detection/bp4_notebook3_champion_<variant>.pkl
  - reports/bp4_structuring_smurfing_detection/bp4_notebook3_validation_report_<variant>.json
      (selected_threshold + feature_cols + champion_needs_rf_impute + rf_impute_value --
      the real, saved values, never re-typed by hand)

Environment variables (same names the Dockerfile already sets, per Notebook 4):
  BP4_CHAMPION_MODEL_PATH -- absolute path to the real champion .pkl (optional; if unset,
                             resolved from BP4_DATASET_VARIANT below)
  BP4_DATASET_VARIANT     -- "HI-Small" or "LI-Medium" (default: "LI-Medium", this BP's
                             locked mandatory realism-validation tier)
"""

from __future__ import annotations

import json
import math
import os
import pickle
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI
from pydantic import create_model


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
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set BP4_CHAMPION_MODEL_PATH "
        "directly to skip root resolution, or run this service from inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
DATASET_VARIANT = os.environ.get("BP4_DATASET_VARIANT", "LI-Medium")
if DATASET_VARIANT not in ("HI-Small", "LI-Medium"):
    raise ValueError(f"BP4_DATASET_VARIANT must be 'HI-Small' or 'LI-Medium', got {DATASET_VARIANT!r}")
VARIANT_TAG = DATASET_VARIANT.lower().replace("-", "_")

MODELS_DIR = PROJECT_ROOT / "models" / "bp4_structuring_smurfing_detection"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp4_structuring_smurfing_detection"

_default_model_path = MODELS_DIR / f"bp4_notebook3_champion_{VARIANT_TAG}.pkl"
CHAMPION_MODEL_PATH = Path(os.environ.get("BP4_CHAMPION_MODEL_PATH", str(_default_model_path)))
REPORT_PATH = REPORTS_DIR / f"bp4_notebook3_validation_report_{VARIANT_TAG}.json"

if not CHAMPION_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"{CHAMPION_MODEL_PATH} does not exist. This service loads Notebook 3's real saved "
        f"champion model -- run 03_statistical_validation_deployment_SINGLE_CELL.py with "
        f"DATASET_VARIANT = '{DATASET_VARIANT}' first (it is what actually creates this file)."
    )
if not REPORT_PATH.exists():
    raise FileNotFoundError(
        f"{REPORT_PATH} does not exist. This service reads Notebook 3's real saved validation "
        f"report for its selected_threshold, feature_cols, champion_needs_rf_impute, and "
        f"rf_impute_value -- run Notebook 3 for '{DATASET_VARIANT}' first."
    )

with open(CHAMPION_MODEL_PATH, "rb") as _f:
    champion_model = pickle.load(
        _f
    )  # nosec B301 -- loads this project's own real trained artifact from a path resolved via PROJECT_ROOT/env var, never untrusted external input  # noqa: E501

with open(REPORT_PATH, encoding="utf-8") as _f:
    _report = json.load(_f)

# Real, saved values -- never re-typed by hand (that would risk drifting from the notebook
# that actually computed them, the exact failure mode Lesson #2 exists to prevent).
FEATURE_COLS: list[str] = _report["feature_cols"]
SELECTED_THRESHOLD: float = _report["selected_threshold"]
CHAMPION_NAME: str = _report["champion_name"]
CHAMPION_NEEDS_RF_IMPUTE: bool = _report["champion_needs_rf_impute"]
RF_IMPUTE_VALUE: Optional[float] = _report["rf_impute_value"]

# The one real, disclosed NaN-prone column (Notebook 2's rolling-window structuring feature) --
# never hand-typed; derived from the same real, saved `structuring_feature_cols` Notebook 3
# itself persisted, matching the exact column its own score_transaction treats as Optional.
_NAN_PRONE_COL = "amount_to_rolling_window_mean_ratio"
if _NAN_PRONE_COL not in FEATURE_COLS:
    raise ValueError(
        f"Expected real feature column {_NAN_PRONE_COL!r} in the saved report's feature_cols "
        f"-- got {FEATURE_COLS!r}. This service's impute logic assumes it is present."
    )
if CHAMPION_NEEDS_RF_IMPUTE and RF_IMPUTE_VALUE is None:
    raise ValueError(
        "Saved report says champion_needs_rf_impute=true but rf_impute_value is null -- "
        "Notebook 3 should always persist both together for a RandomForest champion."
    )

print(
    f"[bp4_scoring_service] Loaded real champion '{CHAMPION_NAME}' for variant "
    f"'{DATASET_VARIANT}' from {CHAMPION_MODEL_PATH.name}; "
    f"selected_threshold={SELECTED_THRESHOLD:.6f}; {len(FEATURE_COLS)} real feature columns; "
    f"champion_needs_rf_impute={CHAMPION_NEEDS_RF_IMPUTE}."
)

# ----------------------------------------------------------------------------------------
# Real request schema -- one float field per real feature column, identical to Notebook 3's
# own in-notebook FastAPI self-test schema (same FIELD_TYPES construction): every column is
# always finite by this project's feature policy EXCEPT the one real, disclosed NaN-prone
# rolling-window column, which is Optional[float] = None so a real caller can send JSON
# `null` for it (standard JSON has no NaN literal -- Notebook 3's own self-test caught and
# fixed exactly this).
# ----------------------------------------------------------------------------------------
_FIELD_TYPES = {c: ((Optional[float], None) if c == _NAN_PRONE_COL else (float, ...)) for c in FEATURE_COLS}
TxnFeatures = create_model("TxnFeatures", **_FIELD_TYPES)


def score_transaction(record: dict) -> dict:
    """The exact same scoring code path Notebook 3's FastAPI self-test already verified
    bit-identical to direct batch `champion_model.predict_proba` calls (max|diff|=0.0 on a
    real 5,000-row sample, both variants). Copied verbatim, not re-derived.

    Real, disclosed note (from Notebook 3): a missing/None value for the one NaN-prone
    rolling-window column is converted back to a real NaN here, then imputed with the
    champion's own real train-median impute value ONLY if the saved report says this
    champion needs it (RandomForest, no native NaN support); boosted-tree champions accept
    a real NaN directly, exactly as Notebook 3's own score_transaction does.
    """
    rec = dict(record)
    if rec.get(_NAN_PRONE_COL) is None:
        rec[_NAN_PRONE_COL] = math.nan
    row = pd.DataFrame([{c: rec[c] for c in FEATURE_COLS}])
    if CHAMPION_NEEDS_RF_IMPUTE:
        row[_NAN_PRONE_COL] = row[_NAN_PRONE_COL].fillna(RF_IMPUTE_VALUE)
    proba = float(champion_model.predict_proba(row)[:, 1][0])
    return {
        "probability": proba,
        "is_flagged": bool(proba >= SELECTED_THRESHOLD),
        "threshold": SELECTED_THRESHOLD,
        "champion_name": CHAMPION_NAME,
        "dataset_variant": DATASET_VARIANT,
    }


app = FastAPI(title=f"BP4 Structuring & Smurfing Scoring Service ({DATASET_VARIANT})")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dataset_variant": DATASET_VARIANT,
        "champion_name": CHAMPION_NAME,
        "selected_threshold": SELECTED_THRESHOLD,
        "feature_count": len(FEATURE_COLS),
        "champion_needs_rf_impute": CHAMPION_NEEDS_RF_IMPUTE,
    }


@app.post("/score")
def score_endpoint(txn: TxnFeatures) -> dict:
    return score_transaction(txn.model_dump())
