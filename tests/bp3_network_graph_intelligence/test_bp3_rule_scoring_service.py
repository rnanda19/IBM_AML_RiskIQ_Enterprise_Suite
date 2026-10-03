"""
Structural / wiring tests for src/aml_riskiq/serving/bp3_rule_scoring_service.py.

Scope discipline (important -- read before extending this file): these tests verify the
SERVICE'S OWN CODE -- file-resolution logic, Pydantic schema construction, FastAPI request/
response wiring, and the score_account() lookup path (including the honest "account not in
graph" response for an unknown key) -- using a tiny SYNTHETIC rule JSON + a tiny synthetic
near_train_flagged lookup table (a handful of fake account keys, written to a temp
directory). They never load this BP's real persisted lookup table, real champion rule, or
any real AML transaction/graph data, per this project's standing execution-boundary rule
(Claude writes and tests code; real business numbers only ever come from the user's own
real notebook runs). A PASS here means "the service is wired correctly", not "the real
2-hop proximity rule is correct" -- that second claim is already covered by Notebook 3's
own real, bit-identical FastAPI self-test against its own real champion rule (see that
notebook's own saved validation report's `fastapi_self_test` block).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# Tiny synthetic (Bank|Account)-format keys -- same real composite-key string format
# Notebook 3's own `node_key` uses, never a real account from the real dataset.
FLAGGED_KEY = "070|10042B660"
NOT_FLAGGED_KEY = "070|10042B978"
UNKNOWN_KEY = "999|NOTINGRAPH000"

SYNTHETIC_RULE = {
    "champion_signal": "2-hop proximity to a TRAIN-flagged account",
    "champion_column": "near_train_flagged",
    "is_threshold_signal": False,
    "threshold": None,
    "note": "synthetic test fixture rule artifact",
}

SYNTHETIC_REPORT = {
    "champion_name": "2-hop proximity to a TRAIN-flagged account",
    "test_metrics": {"lift_ratio": 3.1882},
    "bootstrap": {"ci95_low": 3.1567, "ci95_high": 3.2187},
}


@pytest.fixture()
def stub_service(tmp_path, monkeypatch):
    """Builds a fake MODELS_DIR/REPORTS_DIR with a synthetic rule JSON + a synthetic
    near_train_flagged lookup Parquet + a synthetic validation report, points the
    service's own env vars at them, and imports the real service module fresh (never
    reusing a prior import, since the module does its real file I/O at import time)."""
    models_dir = tmp_path / "models" / "bp3_network_graph_intelligence"
    reports_dir = tmp_path / "reports" / "bp3_network_graph_intelligence"
    models_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    rule_path = models_dir / "bp3_notebook3_champion_rule_li_medium.json"
    rule_path.write_text(json.dumps(SYNTHETIC_RULE))

    lookup_path = models_dir / "bp3_notebook3_near_train_flagged_lookup_li_medium.parquet"
    lookup_df = pd.DataFrame(
        {
            "node_key": [FLAGGED_KEY, NOT_FLAGGED_KEY],
            "near_train_flagged": [True, False],
        }
    )
    lookup_df.to_parquet(lookup_path, index=False)
    # UNKNOWN_KEY is deliberately NOT written to the lookup table -- it must come back as
    # the honest "account_not_in_graph_as_of_last_run" response, never a fabricated flag.

    report_path = reports_dir / "bp3_notebook3_validation_report_li_medium.json"
    report_path.write_text(json.dumps(SYNTHETIC_REPORT))

    # Marker file the service's own _locate_project_root() looks for -- keeps this test
    # independent of this real on-device project tree.
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("test fixture marker")

    monkeypatch.setenv("BP3_CHAMPION_RULE_PATH", str(rule_path))
    monkeypatch.setenv("BP3_LOOKUP_PATH", str(lookup_path))
    monkeypatch.setenv("BP3_DATASET_VARIANT", "LI-Medium")
    monkeypatch.chdir(tmp_path)

    sys.modules.pop("serving.bp3_rule_scoring_service", None)
    sys.modules.pop("src.aml_riskiq.serving.bp3_rule_scoring_service", None)
    src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    module = importlib.import_module("serving.bp3_rule_scoring_service")
    yield module
    sys.modules.pop("serving.bp3_rule_scoring_service", None)


def test_champion_signal_loaded_from_real_saved_rule(stub_service):
    assert stub_service.CHAMPION_SIGNAL == "2-hop proximity to a TRAIN-flagged account"
    assert stub_service.IS_THRESHOLD_SIGNAL is False


def test_lift_ratio_loaded_from_real_saved_report(stub_service):
    assert stub_service.REAL_LIFT_RATIO == pytest.approx(3.1882)
    assert stub_service.REAL_BOOTSTRAP_CI95_LOW == pytest.approx(3.1567)
    assert stub_service.REAL_BOOTSTRAP_CI95_HIGH == pytest.approx(3.2187)


def test_health_endpoint(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["accounts_in_lookup"] == 2
    assert body["is_threshold_signal"] is False


def test_score_endpoint_flags_known_flagged_account(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.post("/score", json={"account_key": FLAGGED_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["near_train_flagged"] is True
    assert body["champion_signal"] == "2-hop proximity to a TRAIN-flagged account"


def test_score_endpoint_does_not_flag_known_not_flagged_account(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.post("/score", json={"account_key": NOT_FLAGGED_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["near_train_flagged"] is False


def test_score_endpoint_honest_response_for_unknown_account(stub_service):
    """An account key never seen in Notebook 3's real graph must come back as an honest,
    disclosed 'not in graph' response -- never a fabricated True/False flag."""
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.post("/score", json={"account_key": UNKNOWN_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "account_not_in_graph_as_of_last_run"
    assert body["near_train_flagged"] is None


def test_score_endpoint_rejects_missing_account_key(stub_service):
    from fastapi.testclient import TestClient

    client = TestClient(stub_service.app)
    resp = client.post("/score", json={})
    assert resp.status_code == 422  # Pydantic validation error, not a 500
