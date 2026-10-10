"""
BP5 -- Correspondent Banking & Cross-Border Wire Risk: real, standalone FastAPI scoring service.

REAL GAP THIS FILE CLOSES: BP5's Dockerfile (src/docker/bp5_correspondent_banking_crossborder_risk/
Dockerfile) and docker-compose.yml already existed and already pointed their CMD at
`src.aml_riskiq.serving.bp5_scoring_service:app`, but until this file was added,
`src/aml_riskiq/serving/bp5_scoring_service.py` did not exist anywhere in `src/` -- the image would
build but the container would crash immediately on start with `ModuleNotFoundError`. Notebook
4's own packaging cell flagged this explicitly as a "DISCLOSED GAP ... ACTION NEEDED" and
printed "No hardening pass has touched BP5 yet" -- this is that hardening pass, mirroring the
same extraction already done for BP1/BP2/BP3/BP4.

Zero-fabrication / no-new-logic discipline: every line of scoring logic below is copied
verbatim from BP5 Notebook 3's own in-notebook `score_transaction` function (the same one its
FastAPI self-test already proved bit-identical to direct batch `predict_proba` calls on a real
5,000-row sample, both variants -- max_abs_diff=0.0, 0 mismatches, confirmed from each
variant's own saved `fastapi_self_test` block). This file does not re-derive or re-guess that
logic -- it is the exact same code path, now persisted so Docker can actually import it
(Lesson #3's standing rule: any code a deployable service runs must replicate the source
notebook's real logic exactly, never an independent reimplementation).

BP5-specific real detail (simpler than BP4, NOT copy-pasted blind): BP5 Notebook 3's own
in-kernel FastAPI self-test comment states explicitly that "BP5 has no disclosed-NaN column
anywhere in FEATURE_COLS" (unlike BP4's rolling-window ratio column) -- every one of BP5's 27
real feature columns is `(float, ...)`, required, no NaN/impute handling needed at all. This
service's request schema and `score_transaction` therefore have no Optional[float] field and
no impute branch, matching Notebook 3's own simpler schema exactly.

Real model + real threshold are loaded from Notebook 3's own saved artifacts at import time:
  - models/bp5_correspondent_banking_crossborder_risk/bp5_<variant>_model_v1.pkl
      (BP5's own real filename convention -- confirmed from Notebook 3's own save code and the
      real on-disk listing: bp5_hi_small_model_v1.pkl / bp5_li_medium_model_v1.pkl. This is a
      DIFFERENT naming pattern from BP4's "bp4_notebook3_champion_<variant>.pkl" -- BP5's own
      real filenames are used here, never BP4's pattern copy-pasted blind.)
  - reports/bp5_correspondent_banking_crossborder_risk/bp5_notebook3_validation_report_<variant>.json
      (selected_threshold + feature_cols -- the real, saved values, never re-typed by hand)

Environment variables (same names the existing Dockerfile already sets, per Notebook 4):
  BP5_CHAMPION_MODEL_PATH -- absolute path to the real champion .pkl (optional; if unset,
                             resolved from BP5_DATASET_VARIANT below)
  BP5_DATASET_VARIANT     -- "HI-Small" or "LI-Medium" (default: "LI-Medium", this BP's
                             locked mandatory realism-validation tier)
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Request

try:
    from serving._security import (
        harden_app,
        require_api_key,
        score_rate_limit,
        wire_metrics_endpoint,
    )
except ImportError:  # pragma: no cover -- exercised under Docker's import context, not pytest's
    from src.aml_riskiq.serving._security import (
        harden_app,
        require_api_key,
        score_rate_limit,
        wire_metrics_endpoint,
    )
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
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set BP5_CHAMPION_MODEL_PATH "
        "directly to skip root resolution, or run this service from inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
DATASET_VARIANT = os.environ.get("BP5_DATASET_VARIANT", "LI-Medium")
if DATASET_VARIANT not in ("HI-Small", "LI-Medium"):
    raise ValueError(f"BP5_DATASET_VARIANT must be 'HI-Small' or 'LI-Medium', got {DATASET_VARIANT!r}")
VARIANT_TAG = DATASET_VARIANT.lower().replace("-", "_")

MODELS_DIR = PROJECT_ROOT / "models" / "bp5_correspondent_banking_crossborder_risk"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp5_correspondent_banking_crossborder_risk"

# BP5's own real filename convention (confirmed from Notebook 3's own save code and the real
# on-disk listing) -- NOT BP4's "bp4_notebook3_champion_<variant>.pkl" pattern.
_default_model_path = MODELS_DIR / f"bp5_{VARIANT_TAG}_model_v1.pkl"
CHAMPION_MODEL_PATH = Path(os.environ.get("BP5_CHAMPION_MODEL_PATH", str(_default_model_path)))
REPORT_PATH = REPORTS_DIR / f"bp5_notebook3_validation_report_{VARIANT_TAG}.json"

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

with open(CHAMPION_MODEL_PATH, "rb") as _model_f:
    champion_model = pickle.load(
        _model_f
    )  # nosec B301 -- loads this project's own real trained artifact from a path resolved via PROJECT_ROOT/env var, never untrusted external input  # noqa: E501

with open(REPORT_PATH, encoding="utf-8") as _report_f:
    _report = json.load(_report_f)

# Real, saved values -- never re-typed by hand (that would risk drifting from the notebook
# that actually computed them, the exact failure mode Lesson #2 exists to prevent).
FEATURE_COLS: list[str] = _report["feature_cols"]
SELECTED_THRESHOLD: float = _report["selected_threshold"]
CHAMPION_NAME: str = _report["champion_name"]

print(
    f"[bp5_scoring_service] Loaded real champion '{CHAMPION_NAME}' for variant "
    f"'{DATASET_VARIANT}' from {CHAMPION_MODEL_PATH.name}; "
    f"selected_threshold={SELECTED_THRESHOLD:.6f}; {len(FEATURE_COLS)} real feature columns."
)

# Real model-registry fingerprint -- computed once at import time from the actual on-disk
# model file (never cached across different files, never guessed); exposed via /health so a
# caller can verify exactly which model artifact this running process loaded.
try:
    from serving._model_registry import build_registry_entry
except ImportError:  # pragma: no cover -- exercised under Docker's import context, not pytest's
    from src.aml_riskiq.serving._model_registry import build_registry_entry

MODEL_REGISTRY_ENTRY = build_registry_entry(
    model_path=CHAMPION_MODEL_PATH,
    champion_name=CHAMPION_NAME,
    dataset_variant=DATASET_VARIANT,
    report_generated_at_utc=_report.get("generated_at_utc"),
)

# ----------------------------------------------------------------------------------------
# Real request schema -- one float field per real feature column, identical to Notebook 3's
# own in-notebook FastAPI self-test schema (same FIELD_TYPES construction). Unlike BP4, BP5
# has no disclosed-NaN column anywhere in FEATURE_COLS, so every field is simply
# (float, ...), required -- no Optional[float] special case needed.
# ----------------------------------------------------------------------------------------
_FIELD_TYPES = {c: (float, ...) for c in FEATURE_COLS}
TxnFeatures = create_model(
    "TxnFeatures", **_FIELD_TYPES
)  # type: ignore[call-overload]  # pydantic's mypy plugin only validates create_model()
# calls that use literal field definitions; here the fields are built dynamically from
# FEATURE_COLS (loaded from the real saved validation report at runtime, per Lesson #2 --
# never hardcode feature names), which mypy cannot statically verify. This is pydantic's
# own documented limitation for dynamic create_model() usage, not a real type error.


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


app = FastAPI(title=f"BP5 Correspondent Banking & Cross-Border Wire Risk Scoring Service ({DATASET_VARIANT})")
_limiter = harden_app(app, "bp5_scoring_service")
wire_metrics_endpoint(app)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dataset_variant": DATASET_VARIANT,
        "champion_name": CHAMPION_NAME,
        "selected_threshold": SELECTED_THRESHOLD,
        "feature_count": len(FEATURE_COLS),
        "model_registry": MODEL_REGISTRY_ENTRY,
    }


@app.post("/score")
@_limiter.limit(score_rate_limit())
def score_endpoint(request: Request, txn: TxnFeatures, _caller: str = Depends(require_api_key)) -> dict:
    return score_transaction(txn.model_dump())
