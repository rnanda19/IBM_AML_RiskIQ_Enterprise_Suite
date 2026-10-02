"""
BP1 -- Transaction Monitoring & Suspicious Activity Detection: real, standalone FastAPI
scoring service.

REAL BUG THIS FILE FIXES (found 2026-09-30, during a corrections review): BP1 Notebook 4's
Docker packaging step writes a Dockerfile whose CMD points at
`src.services.bp1_scoring_service:app` -- but until this file was added, that module did not
exist anywhere in `src/`. The Dockerfile built successfully but the container would crash
immediately on start with `ModuleNotFoundError`. This file is that missing module.

Zero-fabrication / no-new-logic discipline: every line of scoring logic below is copied
verbatim from Notebook 3's own in-notebook `score_transaction` function (the same one its
FastAPI self-test already proved bit-identical to direct batch `predict_proba` calls on every
row of a real 5,000-row sample, both HI-Small and LI-Medium). This file does not re-derive or
re-guess that logic -- it is the exact same code path, now persisted so Docker can actually
import it (Lesson #3's standing rule: any code a deployable service runs must replicate the
source notebook's real logic exactly, never an independent reimplementation).

Real model + real threshold are loaded from Notebook 3's own saved artifacts at import time:
  - models/bp1_transaction_monitoring_detection/bp1_notebook3_champion_<variant>.pkl
  - reports/bp1_transaction_monitoring_detection/bp1_notebook3_validation_report_<variant>.json
      (selected_threshold + feature_cols -- the real, saved values, never re-typed by hand)

Environment variables (same names the Dockerfile already sets, per Notebook 4):
  BP1_CHAMPION_MODEL_PATH -- absolute path to the real champion .pkl (optional; if unset,
                             resolved from BP1_DATASET_VARIANT below)
  BP1_DATASET_VARIANT     -- "HI-Small" or "LI-Medium" (default: "LI-Medium", this BP's
                             locked mandatory realism-validation tier)
"""
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from pydantic import create_model

# ----------------------------------------------------------------------------------------
# Real project-root resolution -- same pattern every notebook in this platform uses, so this
# service resolves correctly whether run locally, from Docker (repo root as build context,
# per Notebook 4's own Dockerfile comment), or from any other real working directory.
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
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set BP1_CHAMPION_MODEL_PATH "
        "directly to skip root resolution, or run this service from inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
DATASET_VARIANT = os.environ.get("BP1_DATASET_VARIANT", "LI-Medium")
if DATASET_VARIANT not in ("HI-Small", "LI-Medium"):
    raise ValueError(f"BP1_DATASET_VARIANT must be 'HI-Small' or 'LI-Medium', got {DATASET_VARIANT!r}")
VARIANT_TAG = DATASET_VARIANT.lower().replace("-", "_")

MODELS_DIR = PROJECT_ROOT / "models" / "bp1_transaction_monitoring_detection"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp1_transaction_monitoring_detection"

_default_model_path = MODELS_DIR / f"bp1_notebook3_champion_{VARIANT_TAG}.pkl"
CHAMPION_MODEL_PATH = Path(os.environ.get("BP1_CHAMPION_MODEL_PATH", str(_default_model_path)))
REPORT_PATH = REPORTS_DIR / f"bp1_notebook3_validation_report_{VARIANT_TAG}.json"

if not CHAMPION_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"{CHAMPION_MODEL_PATH} does not exist. This service loads Notebook 3's real saved "
        f"champion model -- run 03_statistical_validation_deployment_SINGLE_CELL.py with "
        f"DATASET_VARIANT = '{DATASET_VARIANT}' first (it is what actually creates this file)."
    )
if not REPORT_PATH.exists():
    raise FileNotFoundError(
        f"{REPORT_PATH} does not exist. This service reads Notebook 3's real saved validation "
        f"report for its selected_threshold and feature_cols -- run Notebook 3 for "
        f"'{DATASET_VARIANT}' first."
    )

with open(CHAMPION_MODEL_PATH, "rb") as _f:
    champion_model = pickle.load(_f)  # nosec B301 -- loads this project's own real trained artifact from a path resolved via PROJECT_ROOT/env var, never untrusted external input

with open(REPORT_PATH, encoding="utf-8") as _f:
    _report = json.load(_f)

# Real, saved values -- never re-typed by hand (that would risk drifting from the notebook
# that actually computed them, the exact failure mode Lesson #2 exists to prevent).
FEATURE_COLS: list[str] = _report["feature_cols"]
SELECTED_THRESHOLD: float = _report["selected_threshold"]
CHAMPION_NAME: str = _report["champion_name"]

print(
    f"[bp1_scoring_service] Loaded real champion '{CHAMPION_NAME}' for variant "
    f"'{DATASET_VARIANT}' from {CHAMPION_MODEL_PATH.name}; "
    f"selected_threshold={SELECTED_THRESHOLD:.6f}; {len(FEATURE_COLS)} real feature columns."
)

# ----------------------------------------------------------------------------------------
# Real request schema -- one float field per real feature column, identical to Notebook 3's
# own in-notebook FastAPI self-test schema (same FIELD_TYPES construction).
# ----------------------------------------------------------------------------------------
_FIELD_TYPES = {c: (float, ...) for c in FEATURE_COLS}
TxnFeatures = create_model("TxnFeatures", **_FIELD_TYPES)


def score_transaction(record: dict) -> dict:
    """The exact same scoring code path Notebook 3's FastAPI self-test already verified
    bit-identical to direct batch `champion_model.predict_proba` calls (max|diff|=0.0 on a
    real 5,000-row sample, both variants). Copied verbatim, not re-derived."""
    row = pd.DataFrame([{c: record[c] for c in FEATURE_COLS}])
    proba = float(champion_model.predict_proba(row)[:, 1][0])
    return {
        "probability": proba,
        "is_flagged": bool(proba >= SELECTED_THRESHOLD),
        "threshold": SELECTED_THRESHOLD,
        "champion_name": CHAMPION_NAME,
        "dataset_variant": DATASET_VARIANT,
    }


app = FastAPI(title=f"BP1 Transaction Monitoring Scoring Service ({DATASET_VARIANT})")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dataset_variant": DATASET_VARIANT,
        "champion_name": CHAMPION_NAME,
        "selected_threshold": SELECTED_THRESHOLD,
        "feature_count": len(FEATURE_COLS),
    }


@app.post("/score")
def score_endpoint(txn: TxnFeatures) -> dict:
    return score_transaction(txn.model_dump())
