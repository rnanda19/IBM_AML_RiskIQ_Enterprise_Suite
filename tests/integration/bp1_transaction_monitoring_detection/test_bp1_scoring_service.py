"""
Structural / wiring tests for src/aml_riskiq/serving/bp1_scoring_service.py.

Scope discipline (important -- read before extending this file): these tests verify the
SERVICE'S OWN CODE -- file-resolution logic, Pydantic schema construction, FastAPI request/
response wiring, and the score_transaction() code path -- using a tiny SYNTHETIC stub
classifier (a trivial Python object with a predict_proba() method, pickled to a temp
directory) standing in for the real champion model. They never load this BP's real trained
model artifact or any real AML transaction data, per this project's standing execution-
boundary rule (Claude writes and tests code; real business numbers only ever come from the
user's own real notebook runs). A PASS here means "the service is wired correctly", not "the
real model scores correctly" -- that second claim is already covered by Notebook 3's own
real, bit-identical FastAPI self-test against the real champion model (see that notebook's
own saved validation report).
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
    assert the service's own plumbing (not model quality) is correct."""

    def predict_proba(self, X):
        import numpy as np

        n = len(X)
        # column 0 = P(not laundering), column 1 = P(laundering) -- same shape contract as
        # every real sklearn-style classifier this platform's services already rely on.
        return np.tile(np.array([[0.1, 0.9]]), (n, 1))


FEATURE_COLS = ["hour", "day_of_week", "log_amount_paid"]


@pytest.fixture()
def stub_service(tmp_path, monkeypatch):
    """Builds a fake MODELS_DIR/REPORTS_DIR with a synthetic pickled stub model + report
    JSON, points the service's own env vars at them, and imports the real service module
    fresh (never reusing a prior import, since the module does its real file I/O at import
    time)."""
    models_dir = tmp_path / "models" / "bp1_transaction_monitoring_detection"
    reports_dir = tmp_path / "reports" / "bp1_transaction_monitoring_detection"
    models_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    model_path = models_dir / "bp1_notebook3_champion_li_medium.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(_StubChampion(), f)

    report_path = reports_dir / "bp1_notebook3_validation_report_li_medium.json"
    report_path.write_text(
        json.dumps(
            {
                "feature_cols": FEATURE_COLS,
                "selected_threshold": 0.5,
                "champion_name": "StubChampion",
            }
        )
    )

    # Marker file the service's own _locate_project_root() looks for -- keeps this test
    # independent of this real on-device project tree.
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("test fixture marker")

    monkeypatch.setenv("BP1_CHAMPION_MODEL_PATH", str(model_path))
    monkeypatch.setenv("BP1_DATASET_VARIANT", "LI-Medium")
    monkeypatch.chdir(tmp_path)

    sys.modules.pop("serving.bp1_scoring_service", None)
    sys.modules.pop("src.aml_riskiq.serving.bp1_scoring_service", None)
    src_path = str(Path(__file__).resolve().parents[3] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    module = importlib.import_module("serving.bp1_scoring_service")
    yield module
    sys.modules.pop("serving.bp1_scoring_service", None)


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
    assert 'service="bp1_scoring_service"' in resp.text
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


def test_score_endpoint_rejects_missing_feature(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    incomplete = {c: 1.0 for c in FEATURE_COLS[:-1]}  # drop one required feature
    resp = client.post("/score", json=incomplete)
    assert resp.status_code == 422  # Pydantic validation error, not a 500


def test_score_endpoint_open_mode_by_default(stub_service):
    """This project's own test suite never sets AML_RISKIQ_API_KEYS, so every real
    service -- including this one -- runs in the documented open-auth mode and /score
    stays reachable with no X-API-Key header. This is the integration-level proof that
    bp1's real route wiring (src/aml_riskiq/serving/_security.py's require_api_key dependency,
    attached via Depends in the real score_endpoint) behaves exactly like the isolated
    unit coverage in tests/shared/test_security.py says it should."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS}
    resp = client.post("/score", json=payload)
    assert resp.status_code == 200


def test_score_endpoint_requires_api_key_when_configured(stub_service, monkeypatch):
    """Flips the real service into closed mode via the real env var and confirms the
    real /score route -- not a synthetic stand-in -- actually enforces it: no header =
    401, wrong key = 401, correct key = 200."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "bp1-integration-test-key")
    client = TestClient(stub_service.app)
    payload = {c: 1.0 for c in FEATURE_COLS}

    resp_no_key = client.post("/score", json=payload)
    assert resp_no_key.status_code == 401

    resp_wrong_key = client.post("/score", json=payload, headers={"X-API-Key": "nope"})
    assert resp_wrong_key.status_code == 401

    resp_correct_key = client.post("/score", json=payload, headers={"X-API-Key": "bp1-integration-test-key"})
    assert resp_correct_key.status_code == 200
