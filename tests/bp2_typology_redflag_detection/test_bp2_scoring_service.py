"""
Structural / wiring tests for src/services/bp2_scoring_service.py.

Scope discipline (important -- read before extending this file): these tests verify the
SERVICE'S OWN CODE -- file-resolution logic, Pydantic schema construction, FastAPI request/
response wiring, label-encoder-based class-name recovery, and the score_transaction()
code path (including the real, report-persisted RandomForest NaN-impute path) -- using a
tiny SYNTHETIC stub classifier and a tiny synthetic stub label encoder (trivial Python
objects, pickled to a temp directory) standing in for the real champion model and the real
label encoder. They never load this BP's real trained model artifact, real label encoder,
or any real AML transaction data, per this project's standing execution-boundary rule
(Claude writes and tests code; real business numbers only ever come from the user's own
real notebook runs). A PASS here means "the service is wired correctly", not "the real
model scores correctly" -- that second claim is already covered by Notebook 3's own real,
bit-identical FastAPI self-test against the real champion model (see that notebook's own
saved validation report's `fastapi_self_test` block).
"""

from __future__ import annotations

import importlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

FEATURE_COLS = ["hour", "day_of_week", "amount_paid_received_ratio"]
NAN_PRONE_COL = "amount_paid_received_ratio"
CLASS_NAMES = ["CYCLE", "FAN-IN", "FAN-OUT", "GATHER-SCATTER", "RANDOM"]
# Fixed, deterministic probability vector -- argmax is index 2 ("FAN-OUT").
_FIXED_PROBA = np.array([0.05, 0.05, 0.70, 0.10, 0.10])


class _StubChampion:
    """Deterministic, synthetic stand-in for a real trained multi-class classifier. Not
    fitted on any real or synthetic AML data -- just returns a fixed, known probability
    vector so the test can assert the service's own plumbing (not model quality) is
    correct. Implements both predict() and predict_proba() -- the same dual contract every
    real sklearn-style classifier this platform's services rely on exposes -- and records
    the last frame it was asked to score, so the impute test can assert on what actually
    reached the model (real NaN vs. real imputed value)."""

    def __init__(self):
        self.last_X = None

    def predict_proba(self, X):
        self.last_X = X.copy()
        n = len(X)
        return np.tile(_FIXED_PROBA, (n, 1))

    def predict(self, X):
        n = len(X)
        return np.full(n, int(_FIXED_PROBA.argmax()))


class _StubLabelEncoder:
    """Trivial synthetic stand-in for a real sklearn LabelEncoder -- same two-attribute
    contract (`classes_` + `inverse_transform`) the real one exposes, never a real fit."""

    def __init__(self, classes):
        self.classes_ = np.array(classes)

    def inverse_transform(self, indices):
        return np.array([self.classes_[i] for i in indices])


def _write_fixture(tmp_path, *, champion_needs_rf_impute, rf_impute_value):
    models_dir = tmp_path / "models" / "bp2_typology_redflag_detection"
    reports_dir = tmp_path / "reports" / "bp2_typology_redflag_detection"
    models_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    model_path = models_dir / "bp2_notebook3_champion_li_medium.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(_StubChampion(), f)

    encoder_path = models_dir / "bp2_notebook3_label_encoder_li_medium.pkl"
    with open(encoder_path, "wb") as f:
        pickle.dump(_StubLabelEncoder(CLASS_NAMES), f)

    report_path = reports_dir / "bp2_notebook3_validation_report_li_medium.json"
    report_path.write_text(
        json.dumps(
            {
                "feature_cols": FEATURE_COLS,
                "class_names": CLASS_NAMES,
                "champion_name": "StubRandomForest" if champion_needs_rf_impute else "StubChampion",
                "champion_needs_rf_impute": champion_needs_rf_impute,
                "rf_impute_value": rf_impute_value,
            }
        )
    )

    # Marker file the service's own _locate_project_root() looks for -- keeps this test
    # independent of this real on-device project tree.
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("test fixture marker")
    return model_path, encoder_path, report_path


def _import_fresh(tmp_path, monkeypatch, model_path, encoder_path):
    monkeypatch.setenv("BP2_CHAMPION_MODEL_PATH", str(model_path))
    monkeypatch.setenv("BP2_LABEL_ENCODER_PATH", str(encoder_path))
    monkeypatch.setenv("BP2_DATASET_VARIANT", "LI-Medium")
    monkeypatch.chdir(tmp_path)

    sys.modules.pop("services.bp2_scoring_service", None)
    sys.modules.pop("src.services.bp2_scoring_service", None)
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    module = importlib.import_module("services.bp2_scoring_service")
    return module


@pytest.fixture()
def stub_service(tmp_path, monkeypatch):
    """Champion that does NOT need RF impute (e.g. a real boosted-tree champion)."""
    model_path, encoder_path, _ = _write_fixture(
        tmp_path, champion_needs_rf_impute=False, rf_impute_value=None
    )
    module = _import_fresh(tmp_path, monkeypatch, model_path, encoder_path)
    yield module
    sys.modules.pop("services.bp2_scoring_service", None)


@pytest.fixture()
def stub_service_rf_impute(tmp_path, monkeypatch):
    """Champion that DOES need RF impute, with a known real impute value, so the impute
    code path itself is exercised exactly as Notebook 3's own score_transaction does --
    this is BP2's real case (confirmed champion: RandomForest)."""
    model_path, encoder_path, _ = _write_fixture(
        tmp_path, champion_needs_rf_impute=True, rf_impute_value=0.73
    )
    module = _import_fresh(tmp_path, monkeypatch, model_path, encoder_path)
    yield module
    sys.modules.pop("services.bp2_scoring_service", None)


def test_feature_cols_loaded_from_real_saved_report(stub_service):
    assert stub_service.FEATURE_COLS == FEATURE_COLS


def test_class_names_loaded_from_real_saved_report(stub_service):
    assert stub_service.CLASS_NAMES == CLASS_NAMES


def test_health_endpoint(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["feature_count"] == len(FEATURE_COLS)
    assert body["class_names"] == CLASS_NAMES
    assert body["champion_needs_rf_impute"] is False


def test_score_endpoint_returns_predicted_typology_and_class_probabilities(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # stub's fixed proba vector argmaxes at index 2 -> "FAN-OUT"
    assert body["predicted_typology"] == "FAN-OUT"
    assert body["confidence"] == pytest.approx(0.70)
    assert body["class_probabilities"] == {
        name: pytest.approx(float(p)) for name, p in zip(CLASS_NAMES, _FIXED_PROBA)
    }
    # multi-class argmax scoring has no single threshold -- these BP1/BP4 binary-only
    # fields must NOT appear on BP2's response.
    assert "is_flagged" not in body
    assert "threshold" not in body


def test_score_endpoint_rejects_missing_required_feature(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    # drop a required feature that is NOT the optional impute-eligible column
    incomplete = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    incomplete.pop("hour")
    resp = client.post("/score", json=incomplete)
    assert resp.status_code == 422  # Pydantic validation error, not a 500


def test_score_endpoint_omitted_optional_impute_column_still_scores(stub_service):
    """BP2-specific: a request that OMITS the optional, NaN-prone ratio column entirely
    (not even sent as JSON null) must still return 200, not 422."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_typology"] == "FAN-OUT"


def test_rf_impute_path_fills_real_persisted_value(stub_service_rf_impute):
    """When the saved report says champion_needs_rf_impute=true, a missing optional column
    must be imputed with the real, persisted rf_impute_value before predict_proba is called
    -- exactly mirroring Notebook 3's own score_transaction RandomForest branch, and BP4's
    own service's identical pattern for its NaN-prone column."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service_rf_impute.app)
    payload = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200

    stub = stub_service_rf_impute.champion_model
    assert stub.last_X is not None
    # the NaN must have been replaced with the real persisted impute value (0.73), not left
    # as NaN and not replaced with anything else.
    assert stub.last_X[NAN_PRONE_COL].iloc[0] == pytest.approx(0.73)


def test_rf_impute_path_not_applied_when_not_needed(stub_service):
    """When champion_needs_rf_impute=false, a real NaN must reach predict_proba unmodified
    (boosted-tree champions accept NaN natively) -- the impute step must be a no-op."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    client.post("/score", json=payload)

    stub = stub_service.champion_model
    assert stub.last_X is not None
    import math

    assert math.isnan(stub.last_X[NAN_PRONE_COL].iloc[0])
