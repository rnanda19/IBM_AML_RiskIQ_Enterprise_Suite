"""
BP2 -- Typology & Red-Flag Pattern Detection: real, standalone FastAPI scoring service.

REAL BUG THIS FILE FIXES: BP2's own Dockerfile (src/docker/bp2_typology_redflag_detection/
Dockerfile) already points its CMD at `src.aml_riskiq.serving.bp2_scoring_service:app` and already
COPYs the real champion pickle + real label-encoder pickle into the image, but until this
file was added, `src/aml_riskiq/serving/bp2_scoring_service.py` did not exist anywhere in `src/` --
the image would build but the container would crash immediately on start with
`ModuleNotFoundError`, the exact same disclosed gap BP1's and BP4's own service files closed
for those BPs (the Dockerfile's own top-of-file comment flags this gap explicitly for BP2).

Zero-fabrication / no-new-logic discipline: every line of scoring logic below is copied
verbatim from BP2 Notebook 3's own in-notebook `score_transaction` function (the same one
its FastAPI self-test already proved bit-identical to direct batch `predict_proba` calls on
a real 2,000-row sample -- see this BP's own saved `fastapi_self_test` block in the
validation report). This file does not re-derive or re-guess that logic -- it is the exact
same code path, now persisted so Docker can actually import it (Lesson #3's standing rule:
any code a deployable service runs must replicate the source notebook's real logic exactly,
never an independent reimplementation).

Multi-class note (unlike BP1/BP4, which are binary with a single selected_threshold): BP2 is
a real 5-class typology classifier (CYCLE, FAN-IN, FAN-OUT, GATHER-SCATTER, RANDOM) scored on
macro-F1 via argmax -- there is no single probability threshold to apply, so this service has
no `is_flagged`/`threshold` field. Instead `/score` returns `predicted_typology` (the real
class name, recovered from the model's numeric output via the real saved LabelEncoder's
`inverse_transform`), `confidence` (the predicted class's own probability), and
`class_probabilities` (the full real per-class probability vector as a dict), exactly
mirroring Notebook 3's own `score_transaction`.

BP2-specific real detail (confirmed 2026-10-02 by reading Notebook 3 directly -- see this
platform's hardening note dated the same day in that notebook's own saved report dict):
BP2's `amount_paid_received_ratio` feature is a real, disclosed NaN-prone column (rows where
`Amount Received == 0` have an undefined paid/received ratio, left as a real NaN rather than
silently imputed at feature-engineering time -- Lesson #7). The champion model handles this
one of two ways, both already decided and persisted by Notebook 3 -- never re-derived here:
  - A boosted-tree champion (XGBoost, CatBoost, LightGBM) accepts a real NaN directly.
  - A RandomForest champion (BP2's real, confirmed champion for the LI-Medium variant) has no
    native NaN support, so Notebook 3 already computed a real train-median impute value
    (`rf_impute_value`) and persisted it, together with a `champion_needs_rf_impute` flag, in
    its own saved validation report (same key names BP4 already established on this
    platform for the identical concept, reused verbatim here for naming consistency). This
    service reads both and -- exactly mirroring Notebook 3's own `score_transaction` --
    imputes only when the persisted flag says to, using the persisted value, never a value
    computed here.
Because the NaN-prone column can legitimately be missing from a real request, it is the one
FEATURE_COLS entry declared `Optional[float] = None` in the request schema -- a real caller
sends JSON `null` for an undefined ratio, which is standard-JSON (RFC 8259) compliant, and
this service converts it back to a real NaN server-side before scoring, same as BP4's own
service does for its own NaN-prone column.

Real model + real label encoder + real impute settings are loaded from Notebook 3's own
saved artifacts at import time:
  - models/bp2_typology_redflag_detection/bp2_notebook3_champion_<variant>.pkl
  - models/bp2_typology_redflag_detection/bp2_notebook3_label_encoder_<variant>.pkl
  - reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_<variant>.json
      (feature_cols + champion_name + champion_needs_rf_impute + rf_impute_value -- the real,
      saved values, never re-typed by hand)

NOTE on the two new report keys above: they only exist in a validation report JSON produced
by a Notebook 3 run AFTER the 2026-10-02 hardening edit to that notebook. A report generated
before that date will not have them, and this module will raise a clear KeyError at import
time rather than silently defaulting -- re-run Notebook 3 for the dataset variant you intend
to serve before starting this service, per this platform's zero-fabrication rule (never
assume a persisted value that was not actually produced by a real run).

Environment variables (same names the Dockerfile already sets, per Notebook 4):
  BP2_CHAMPION_MODEL_PATH -- absolute path to the real champion .pkl (optional; if unset,
                             resolved from BP2_DATASET_VARIANT below)
  BP2_LABEL_ENCODER_PATH  -- absolute path to the real label-encoder .pkl (optional; if
                             unset, resolved from BP2_DATASET_VARIANT below)
  BP2_DATASET_VARIANT     -- "HI-Small" or "LI-Medium" (default: "LI-Medium", this BP's
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
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set BP2_CHAMPION_MODEL_PATH "
        "directly to skip root resolution, or run this service from inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
DATASET_VARIANT = os.environ.get("BP2_DATASET_VARIANT", "LI-Medium")
if DATASET_VARIANT not in ("HI-Small", "LI-Medium"):
    raise ValueError(f"BP2_DATASET_VARIANT must be 'HI-Small' or 'LI-Medium', got {DATASET_VARIANT!r}")
VARIANT_TAG = DATASET_VARIANT.lower().replace("-", "_")

MODELS_DIR = PROJECT_ROOT / "models" / "bp2_typology_redflag_detection"
REPORTS_DIR = PROJECT_ROOT / "reports" / "bp2_typology_redflag_detection"

_default_model_path = MODELS_DIR / f"bp2_notebook3_champion_{VARIANT_TAG}.pkl"
_default_encoder_path = MODELS_DIR / f"bp2_notebook3_label_encoder_{VARIANT_TAG}.pkl"
CHAMPION_MODEL_PATH = Path(os.environ.get("BP2_CHAMPION_MODEL_PATH", str(_default_model_path)))
LABEL_ENCODER_PATH = Path(os.environ.get("BP2_LABEL_ENCODER_PATH", str(_default_encoder_path)))
REPORT_PATH = REPORTS_DIR / f"bp2_notebook3_validation_report_{VARIANT_TAG}.json"

if not CHAMPION_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"{CHAMPION_MODEL_PATH} does not exist. This service loads Notebook 3's real saved "
        f"champion model -- run 03_statistical_validation_deployment_SINGLE_CELL.py with "
        f"DATASET_VARIANT = '{DATASET_VARIANT}' first (it is what actually creates this file)."
    )
if not LABEL_ENCODER_PATH.exists():
    raise FileNotFoundError(
        f"{LABEL_ENCODER_PATH} does not exist. This service loads Notebook 3's real saved "
        f"label encoder (to map the model's numeric class output back to real typology name "
        f"strings) -- run Notebook 3 for '{DATASET_VARIANT}' first."
    )
if not REPORT_PATH.exists():
    raise FileNotFoundError(
        f"{REPORT_PATH} does not exist. This service reads Notebook 3's real saved validation "
        f"report for its feature_cols, champion_name, champion_needs_rf_impute, and "
        f"rf_impute_value -- run Notebook 3 for '{DATASET_VARIANT}' first."
    )

with open(CHAMPION_MODEL_PATH, "rb") as _model_f:
    champion_model = pickle.load(
        _model_f
    )  # nosec B301 -- loads this project's own real trained artifact from a path resolved via PROJECT_ROOT/env var, never untrusted external input  # noqa: E501

with open(LABEL_ENCODER_PATH, "rb") as _encoder_f:
    label_encoder = pickle.load(
        _encoder_f
    )  # nosec B301 -- loads this project's own real label encoder artifact, same trust boundary as the champion model above  # noqa: E501

with open(REPORT_PATH, encoding="utf-8") as _report_f:
    _report = json.load(_report_f)

# Real, saved values -- never re-typed by hand (that would risk drifting from the notebook
# that actually computed them, the exact failure mode Lesson #2 exists to prevent).
FEATURE_COLS: list[str] = _report["feature_cols"]
CHAMPION_NAME: str = _report["champion_name"]
CLASS_NAMES: list[str] = _report["class_names"]
# Hardening addition (2026-10-02): these two keys only exist in a validation report produced
# by Notebook 3 AFTER that same-dated edit -- see the module docstring's NOTE above. Read
# with plain dict indexing (not .get(..., default)) so a stale, pre-hardening report fails
# loudly at import time instead of silently serving with no impute logic.
CHAMPION_NEEDS_RF_IMPUTE: bool = _report["champion_needs_rf_impute"]
RF_IMPUTE_VALUE: Optional[float] = _report["rf_impute_value"]

# The one real, disclosed NaN-prone column (Notebook 2's amount_paid_received_ratio feature,
# undefined whenever a real row has Amount Received == 0) -- never hand-typed; this service
# asserts it is present in the real saved feature_cols, matching the exact column Notebook
# 3's own score_transaction treats as impute-eligible.
_NAN_PRONE_COL = "amount_paid_received_ratio"
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
    f"[bp2_scoring_service] Loaded real champion '{CHAMPION_NAME}' for variant "
    f"'{DATASET_VARIANT}' from {CHAMPION_MODEL_PATH.name}; {len(FEATURE_COLS)} real feature "
    f"columns; {len(CLASS_NAMES)} real typology classes; "
    f"champion_needs_rf_impute={CHAMPION_NEEDS_RF_IMPUTE}."
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
# Real request schema -- one float field per real feature column, identical in shape to
# Notebook 3's own in-notebook FastAPI self-test schema, except the one real, disclosed
# NaN-prone ratio column is Optional[float] = None here so a real caller can send JSON
# `null` for an undefined ratio (standard JSON has no NaN literal -- the same real fix BP4's
# own service already applies for its own NaN-prone column).
# ----------------------------------------------------------------------------------------
_FIELD_TYPES = {c: ((Optional[float], None) if c == _NAN_PRONE_COL else (float, ...)) for c in FEATURE_COLS}
TxnFeatures = create_model(
    "TxnFeatures", **_FIELD_TYPES
)  # type: ignore[call-overload]  # pydantic's mypy plugin only validates create_model()
# calls that use literal field definitions; here the fields are built dynamically from
# FEATURE_COLS (loaded from the real saved validation report at runtime, per Lesson #2 --
# never hardcode feature names), which mypy cannot statically verify. This is pydantic's
# own documented limitation for dynamic create_model() usage, not a real type error.


def score_transaction(record: dict) -> dict:
    """The exact same scoring code path Notebook 3's FastAPI self-test already verified
    bit-identical to direct batch `predict_proba` calls (max|diff|~0.0 on a real 2,000-row
    sample). Copied verbatim, not re-derived -- the only addition is recovering the real
    typology name via the real saved LabelEncoder's `inverse_transform`, since Notebook 3's
    own in-kernel self-test already has direct access to `class_names` in scope and this
    standalone service does not.

    Real, disclosed note (mirroring BP4's own service): a missing/None value for the one
    NaN-prone ratio column is converted back to a real NaN here, then imputed with the
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
    proba = champion_model.predict_proba(row)[0]
    pred_idx = int(proba.argmax())
    predicted_typology = str(label_encoder.inverse_transform([pred_idx])[0])
    return {
        "predicted_typology": predicted_typology,
        "confidence": float(proba[pred_idx]),
        "class_probabilities": {CLASS_NAMES[i]: float(p) for i, p in enumerate(proba)},
        "champion_name": CHAMPION_NAME,
        "dataset_variant": DATASET_VARIANT,
    }


app = FastAPI(title=f"BP2 Typology & Red-Flag Pattern Scoring Service ({DATASET_VARIANT})")
_limiter = harden_app(app, "bp2_scoring_service")
wire_metrics_endpoint(app)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dataset_variant": DATASET_VARIANT,
        "champion_name": CHAMPION_NAME,
        "class_names": CLASS_NAMES,
        "feature_count": len(FEATURE_COLS),
        "champion_needs_rf_impute": CHAMPION_NEEDS_RF_IMPUTE,
        "model_registry": MODEL_REGISTRY_ENTRY,
    }


@app.post("/score")
@_limiter.limit(score_rate_limit())
def score_endpoint(request: Request, txn: TxnFeatures, _caller: str = Depends(require_api_key)) -> dict:
    return score_transaction(txn.model_dump())
