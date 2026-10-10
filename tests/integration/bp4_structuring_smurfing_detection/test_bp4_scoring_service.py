"""
Structural / wiring tests for src/aml_riskiq/serving/bp4_scoring_service.py.

Scope discipline (important -- read before extending this file): these tests verify the
SERVICE'S OWN CODE -- file-resolution logic, Pydantic schema construction, FastAPI request/
response wiring, and the score_transaction() code path (including the real,
report-persisted RandomForest NaN-impute path) -- using a tiny SYNTHETIC stub classifier (a
trivial Python object with a predict_proba() method, pickled to a temp directory) standing
in for the real champion model. They never load this BP's real trained model artifact or
any real AML transaction data, per this project's standing execution-boundary rule (Claude
writes and tests code; real business numbers only ever come from the user's own real
notebook runs). A PASS here means "the service is wired correctly", not "the real model
scores correctly" -- that second claim is already covered by Notebook 3's own real,
bit-identical FastAPI self-test against the real champion model (see that notebook's own
saved validation report's `fastapi_self_test` block).
"""

from __future__ import annotations

import importlib
import json
import pickle
import sys
from pathlib import Path

import pytest


class _StubChampion:
    """Deterministic, synthetic stand-in for a real trained classifier. Not fitted on any
    real or synthetic AML data -- just returns a fixed, known probability so the test can
    assert the service's own plumbing (not model quality) is correct. Also records the last
    frame it was asked to score, so the impute test can assert on what actually reached the
    model (real NaN vs. real imputed value)."""

    def __init__(self):
        self.last_X = None

    def predict_proba(self, X):
        import numpy as np

        self.last_X = X.copy()
        n = len(X)
        # column 0 = P(not laundering), column 1 = P(laundering) -- same shape contract as
        # every real sklearn-style classifier this platform's services already rely on.
        return np.tile(np.array([[0.1, 0.9]]), (n, 1))


FEATURE_COLS = ["hour", "day_of_week", "amount_to_rolling_window_mean_ratio"]
NAN_PRONE_COL = "amount_to_rolling_window_mean_ratio"


def _write_fixture(tmp_path, *, champion_needs_rf_impute, rf_impute_value):
    models_dir = tmp_path / "models" / "bp4_structuring_smurfing_detection"
    reports_dir = tmp_path / "reports" / "bp4_structuring_smurfing_detection"
    models_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    model_path = models_dir / "bp4_notebook3_champion_li_medium.pkl"
    stub = _StubChampion()
    with open(model_path, "wb") as f:
        pickle.dump(stub, f)

    report_path = reports_dir / "bp4_notebook3_validation_report_li_medium.json"
    report_path.write_text(
        json.dumps(
            {
                "feature_cols": FEATURE_COLS,
                "selected_threshold": 0.5,
                "champion_name": "StubRandomForest" if champion_needs_rf_impute else "StubChampion",
                "champion_needs_rf_impute": champion_needs_rf_impute,
                "rf_impute_value": rf_impute_value,
            }
        )
    )

    # Marker file the service's own _locate_project_root() looks for -- keeps this test
    # independent of this real on-device project tree.
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("test fixture marker")
    return model_path, report_path


def _import_fresh(tmp_path, monkeypatch, model_path):
    monkeypatch.setenv("BP4_CHAMPION_MODEL_PATH", str(model_path))
    monkeypatch.setenv("BP4_DATASET_VARIANT", "LI-Medium")
    monkeypatch.chdir(tmp_path)

    sys.modules.pop("serving.bp4_scoring_service", None)
    sys.modules.pop("src.aml_riskiq.serving.bp4_scoring_service", None)
    src_path = str(Path(__file__).resolve().parents[3] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    module = importlib.import_module("serving.bp4_scoring_service")
    return module


@pytest.fixture()
def stub_service(tmp_path, monkeypatch):
    """Champion that does NOT need RF impute (e.g. a real boosted-tree champion) -- the
    common real case for this project's two persisted variants today."""
    model_path, _ = _write_fixture(tmp_path, champion_needs_rf_impute=False, rf_impute_value=None)
    module = _import_fresh(tmp_path, monkeypatch, model_path)
    yield module
    sys.modules.pop("serving.bp4_scoring_service", None)


@pytest.fixture()
def stub_service_rf_impute(tmp_path, monkeypatch):
    """Champion that DOES need RF impute, with a known real impute value, so the impute
    code path itself is exercised exactly as Notebook 3's own score_transaction does."""
    model_path, _ = _write_fixture(tmp_path, champion_needs_rf_impute=True, rf_impute_value=0.42)
    module = _import_fresh(tmp_path, monkeypatch, model_path)
    yield module
    sys.modules.pop("serving.bp4_scoring_service", None)


def test_feature_cols_loaded_from_real_saved_report(stub_service):
    assert stub_service.FEATURE_COLS == FEATURE_COLS


def test_threshold_loaded_from_real_saved_report(stub_service):
    assert stub_service.SELECTED_THRESHOLD == 0.5


def test_health_endpoint(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["feature_count"] == len(FEATURE_COLS)
    assert body["champion_needs_rf_impute"] is False


def test_metrics_endpoint_wired(stub_service):
    """wire_metrics_endpoint(app) is called in the real service module (not just defined in
    _security.py) -- this asserts a real GET /metrics on the real app object returns the
    real counter for the GET /health call just made, not a mocked or hand-written value."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "aml_riskiq_requests_total" in resp.text
    assert 'service="bp4_scoring_service"' in resp.text
    assert 'path="/health"' in resp.text


def test_score_endpoint_flags_above_threshold(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # stub always returns P(laundering)=0.9, threshold=0.5 -- must flag
    assert body["probability"] == pytest.approx(0.9)
    assert body["is_flagged"] is True
    assert body["threshold"] == 0.5


def test_score_endpoint_rejects_missing_required_feature(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    # drop a required feature that is NOT the optional impute-eligible column
    incomplete = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    incomplete.pop("hour")
    resp = client.post("/score", json=incomplete)
    assert resp.status_code == 422  # Pydantic validation error, not a 500


def test_score_endpoint_omitted_optional_impute_column_still_scores(stub_service):
    """BP4-specific: a request that OMITS the optional, NaN-prone rolling-window column
    entirely (not even sent as JSON null) must still return 200, not 422 -- proving the
    Optional[float] = None schema field and the impute path both work for the stub."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["probability"] == pytest.approx(0.9)
    assert body["is_flagged"] is True


def test_rf_impute_path_fills_real_persisted_value(stub_service_rf_impute):
    """When the saved report says champion_needs_rf_impute=true, a missing optional column
    must be imputed with the real, persisted rf_impute_value before predict_proba is called
    -- exactly mirroring Notebook 3's own score_transaction RandomForest branch."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service_rf_impute.app)
    payload = {c: 1.0 for c in FEATURE_COLS if c != NAN_PRONE_COL}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200

    stub = stub_service_rf_impute.champion_model
    assert stub.last_X is not None
    # the NaN must have been replaced with the real persisted impute value (0.42), not left
    # as NaN and not replaced with anything else.
    assert stub.last_X[NAN_PRONE_COL].iloc[0] == pytest.approx(0.42)


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
