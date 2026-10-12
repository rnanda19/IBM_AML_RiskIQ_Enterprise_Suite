"""
Security/RBAC integration tests for src/aml_riskiq/serving/case_management_service.py.

Scope: this is the automated security-test deliverable this phase asked for --
authentication (missing/invalid key), role enforcement (positive AND negative per route),
input validation (malformed body -> 422), audit logging (a real structured record is emitted
per request), and the dynamic compliance-only transition check. Same stub-model-free
discipline as every other integration test file in this suite: this service has no trained
model to stub, it is pure request/role/persistence wiring over a real (temporary) SQLite
file, never touching any real case data.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def service(tmp_path, monkeypatch):
    """Fresh import of case_management_service.py pointed at a temporary SQLite file, with
    the 4-role API-key set the RBAC matrix below exercises. Role assignment:
      key-analyst    -> analyst
      key-inv        -> investigator
      key-comp       -> compliance_officer
      key-admin      -> admin
    """
    db_path = tmp_path / "casework_test.db"
    monkeypatch.setenv("AML_RISKIQ_CASE_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "AML_RISKIQ_API_KEYS",
        "analyst:key-analyst,investigator:key-inv,compliance_officer:key-comp,admin:key-admin",
    )
    monkeypatch.delenv("AML_RISKIQ_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("AML_RISKIQ_CASE_RATE_LIMIT", raising=False)

    src_path = str(Path(__file__).resolve().parents[3] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    sys.modules.pop("serving.case_management_service", None)
    sys.modules.pop("serving._security", None)
    sys.modules.pop("casework.store", None)
    module = importlib.import_module("serving.case_management_service")
    yield module
    sys.modules.pop("serving.case_management_service", None)


@pytest.fixture()
def client(service):
    from fastapi.testclient import TestClient

    return TestClient(service.app)


H_ANALYST = {"X-API-Key": "key-analyst"}
H_INV = {"X-API-Key": "key-inv"}
H_COMP = {"X-API-Key": "key-comp"}
H_ADMIN = {"X-API-Key": "key-admin"}

_ALERT_BODY = {
    "entity_ref": "acct-1",
    "business_problem": "BP1",
    "detection_source": "xgboost_champion",
    "risk_score": 0.9,
    "selected_threshold": 0.5,
    "model_name": "xgboost_v1",
}


def _create_alert(client, headers=H_ANALYST, **overrides):
    body = {**_ALERT_BODY, **overrides}
    resp = client.post("/alerts", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["alert_id"]


# -- health -----------------------------------------------------------------------------------


def test_health_is_public_even_in_closed_mode(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# -- create alert: role matrix + input validation --------------------------------------------


@pytest.mark.parametrize("headers", [H_ANALYST, H_INV, H_COMP, H_ADMIN])
def test_create_alert_allowed_for_every_role(client, headers):
    resp = client.post("/alerts", json=_ALERT_BODY, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "new"


def test_create_alert_requires_authentication_when_closed(client):
    resp = client.post("/alerts", json=_ALERT_BODY)
    assert resp.status_code == 401


def test_create_alert_rejects_invalid_key(client):
    resp = client.post("/alerts", json=_ALERT_BODY, headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401


def test_create_alert_malformed_body_rejected_with_422(client):
    resp = client.post("/alerts", json={"entity_ref": "acct-1"}, headers=H_ANALYST)  # missing required fields
    assert resp.status_code == 422


def test_create_alert_wrong_type_rejected_with_422(client):
    body = {**_ALERT_BODY, "risk_score": "not-a-number"}
    resp = client.post("/alerts", json=body, headers=H_ANALYST)
    assert resp.status_code == 422


# -- list / get: role matrix -------------------------------------------------------------------


@pytest.mark.parametrize("headers", [H_ANALYST, H_INV, H_COMP, H_ADMIN])
def test_list_and_get_allowed_for_every_role(client, headers):
    alert_id = _create_alert(client)
    resp = client.get("/alerts", headers=headers)
    assert resp.status_code == 200
    assert any(a["alert_id"] == alert_id for a in resp.json())
    resp2 = client.get(f"/alerts/{alert_id}", headers=headers)
    assert resp2.status_code == 200


def test_get_nonexistent_alert_returns_404(client):
    resp = client.get("/alerts/does-not-exist", headers=H_ANALYST)
    assert resp.status_code == 404


def test_list_alerts_filters_by_business_problem(client):
    _create_alert(client, business_problem="BP1")
    _create_alert(client, business_problem="BP4", entity_ref="acct-2")
    resp = client.get("/alerts", params={"business_problem": "BP4"}, headers=H_ANALYST)
    assert resp.status_code == 200
    assert all(a["business_problem"] == "BP4" for a in resp.json())


# -- assign: analyst is EXCLUDED (negative authorization) -------------------------------------


def test_assign_rejected_for_analyst(client):
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_ANALYST)
    assert resp.status_code == 403


@pytest.mark.parametrize("headers", [H_INV, H_COMP, H_ADMIN])
def test_assign_allowed_for_investigator_and_above(client, headers):
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_to"] == "inv-1"
    assert resp.json()["status"] == "assigned"


def test_assign_nonexistent_alert_returns_404(client):
    resp = client.post("/alerts/ghost/assign", json={"assignee": "inv-1"}, headers=H_INV)
    assert resp.status_code == 404


# -- notes / evidence: analyst excluded --------------------------------------------------------


def test_add_note_rejected_for_analyst(client):
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/notes", json={"text": "x"}, headers=H_ANALYST)
    assert resp.status_code == 403


def test_add_note_allowed_for_investigator(client):
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/notes", json={"text": "reviewed history"}, headers=H_INV)
    assert resp.status_code == 201, resp.text
    assert resp.json()["notes"][-1]["text"] == "reviewed history"


def test_add_evidence_rejected_for_analyst(client):
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/evidence", json={"description": "x"}, headers=H_ANALYST)
    assert resp.status_code == 403


def test_add_evidence_allowed_for_compliance_officer(client):
    alert_id = _create_alert(client)
    resp = client.post(
        f"/alerts/{alert_id}/evidence",
        json={"description": "wire record", "external_ref": "wire://123"},
        headers=H_COMP,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["evidence"][-1]["external_ref"] == "wire://123"


def test_evidence_export_rejected_for_analyst(client):
    alert_id = _create_alert(client)
    resp = client.get(f"/alerts/{alert_id}/evidence_export", headers=H_ANALYST)
    assert resp.status_code == 403


def test_evidence_export_allowed_for_investigator(client):
    alert_id = _create_alert(client)
    resp = client.get(f"/alerts/{alert_id}/evidence_export", headers=H_INV)
    assert resp.status_code == 200
    assert resp.json()["alert_id"] == alert_id


# -- transition: investigator can do routine moves, NOT escalate/close ------------------------


def test_transition_to_under_review_allowed_for_investigator(client):
    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    resp = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_INV)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "under_review"


def test_transition_analyst_cannot_even_reach_route(client):
    alert_id = _create_alert(client)
    resp = client.post(
        f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_ANALYST
    )
    assert resp.status_code == 403


def test_transition_to_closed_rejected_for_investigator(client):
    """The key negative-authorization test: investigator passes the route-level Depends()
    (investigator OR compliance_officer) but must still be blocked from the compliance-only
    target status by the dynamic in-handler check."""
    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    client.post(f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_INV)
    resp = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "closed"}, headers=H_INV)
    assert resp.status_code == 403
    # and the status must NOT have changed
    get_resp = client.get(f"/alerts/{alert_id}", headers=H_INV)
    assert get_resp.json()["status"] == "under_review"


def test_transition_to_closed_allowed_for_compliance_officer(client):
    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    client.post(f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_INV)
    resp = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "closed"}, headers=H_COMP)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"


def test_transition_to_escalated_allowed_for_admin_bypass(client):
    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    client.post(f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_INV)
    resp = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "escalated"}, headers=H_ADMIN)
    assert resp.status_code == 200, resp.text


def test_transition_invalid_target_status_returns_422(client):
    alert_id = _create_alert(client)
    resp = client.post(
        f"/alerts/{alert_id}/transition", json={"to_status": "not_a_real_status"}, headers=H_INV
    )
    assert resp.status_code == 422


def test_transition_disallowed_by_state_machine_returns_409(client):
    """NEW -> ESCALATED skips ASSIGNED/UNDER_REVIEW -- the role check passes (compliance
    officer may target ESCALATED) but case_lifecycle's own state machine must still refuse
    it as an invalid transition."""
    alert_id = _create_alert(client)
    resp = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "escalated"}, headers=H_COMP)
    assert resp.status_code == 409


def test_transition_nonexistent_alert_returns_404(client):
    resp = client.post("/alerts/ghost/transition", json={"to_status": "assigned"}, headers=H_INV)
    assert resp.status_code == 404


# -- integrity / reconciliation: compliance_officer only --------------------------------------


def test_integrity_rejected_for_investigator(client):
    alert_id = _create_alert(client)
    resp = client.get(f"/alerts/{alert_id}/integrity", headers=H_INV)
    assert resp.status_code == 403


def test_integrity_allowed_for_compliance_officer_and_clean(client):
    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    resp = client.get(f"/alerts/{alert_id}/integrity", headers=H_COMP)
    assert resp.status_code == 200
    assert resp.json()["verified"] is True


def test_integrity_detects_tampering_via_store(client, service):
    """Exercises the real tamper-detection path through the HTTP layer: tamper the DB
    directly (bypassing the API entirely, as DEF-003's audit-protection requirement
    anticipates), then confirm the integrity ROUTE surfaces the detection, not just the
    store's own unit test."""
    import sqlite3

    alert_id = _create_alert(client)
    client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)

    conn = sqlite3.connect(service.DB_PATH)
    conn.execute("UPDATE case_events SET actor = 'attacker' WHERE alert_id = ?", (alert_id,))
    conn.commit()
    conn.close()

    resp = client.get(f"/alerts/{alert_id}/integrity", headers=H_COMP)
    assert resp.status_code == 200
    assert resp.json()["verified"] is False


def test_reconciliation_rejected_for_investigator(client):
    resp = client.get("/reconciliation", params={"n_transactions_evaluated": 100}, headers=H_INV)
    assert resp.status_code == 403


def test_reconciliation_allowed_for_compliance_officer(client):
    _create_alert(client)
    resp = client.get(
        "/reconciliation", params={"n_transactions_evaluated": 500, "n_rejected": 3}, headers=H_COMP
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_transactions_evaluated"] == 500
    assert body["n_alerts_generated"] == 1


def test_reconciliation_missing_required_query_param_returns_422(client):
    resp = client.get("/reconciliation", headers=H_COMP)  # n_transactions_evaluated omitted
    assert resp.status_code == 422


# -- open mode: no AML_RISKIQ_API_KEYS set -> every route is a no-op (matches every other -----
# -- service's documented open-mode behavior; still gated behind rate limiting / audit log) ---


@pytest.fixture()
def open_mode_client(tmp_path, monkeypatch):
    db_path = tmp_path / "open_mode.db"
    monkeypatch.setenv("AML_RISKIQ_CASE_DB_PATH", str(db_path))
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    monkeypatch.delenv("AML_RISKIQ_REQUIRE_AUTH", raising=False)

    src_path = str(Path(__file__).resolve().parents[3] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    sys.modules.pop("serving.case_management_service", None)
    sys.modules.pop("serving._security", None)
    sys.modules.pop("casework.store", None)
    module = importlib.import_module("serving.case_management_service")

    from fastapi.testclient import TestClient

    yield TestClient(module.app)
    sys.modules.pop("serving.case_management_service", None)


def test_open_mode_allows_every_route_without_a_key(open_mode_client):
    resp = open_mode_client.post("/alerts", json=_ALERT_BODY)
    assert resp.status_code == 201
    alert_id = resp.json()["alert_id"]
    assert open_mode_client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}).status_code == 200
    assert (
        open_mode_client.post(f"/alerts/{alert_id}/transition", json={"to_status": "closed"}).status_code
        == 409  # ASSIGNED -> CLOSED is not in the allowed graph -- real state-machine rule, not auth
    )
    assert open_mode_client.get("/reconciliation", params={"n_transactions_evaluated": 1}).status_code == 200


# -- audit logging: a real structured record is emitted per request ---------------------------


def test_requests_emit_structured_audit_log_lines(client, caplog):
    """Uses caplog (hooks the logging layer directly) rather than capsys: the audit
    logger's StreamHandler is created once, the first time _security.py is imported in this
    whole test session, bound to whatever sys.stdout was at THAT moment -- a later test's
    capsys-redirected stdout can race with that binding. caplog has no such ordering
    dependency."""
    import logging

    alert_id = _create_alert(client, headers=H_INV)
    with caplog.at_level(logging.INFO, logger="aml_riskiq.audit"):
        caplog.clear()
        client.get(f"/alerts/{alert_id}", headers=H_INV)
        records = [r for r in caplog.records if r.name == "aml_riskiq.audit"]
    assert len(records) >= 1
    record = json.loads(records[-1].message)
    assert record["service"] == "case_management_service"
    assert record["method"] == "GET"
    assert record["path"] == f"/alerts/{alert_id}"
    assert record["status_code"] == 200
    assert record["caller_id"] != "anonymous"  # real key fingerprint, never the raw key
    assert "key-inv" not in json.dumps(record)  # the raw API key must never appear in the audit log


def test_metrics_endpoint_reflects_real_request_counts(client):
    _create_alert(client)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert 'service="case_management_service"' in resp.text
    assert 'path="/alerts"' in resp.text


# -- POST /alerts/ingest: scoring-to-alert integration (end-to-end AML workflow integration ---
# -- phase, 2026-10-12) -- idempotent ingestion, RBAC, observability -------------------------


_INGEST_BODY = {
    "entity_ref": "acct-99",
    "business_problem": "BP1",
    "detection_source": "xgboost_champion",
    "risk_score": 0.9,
    "selected_threshold": 0.5,
    "model_name": "xgboost_v1",
    "idempotency_key": "a" * 64,
    "severity": "high",
    "generation_source": "automated_scoring",
}


def test_ingest_creates_new_alert_returns_201(client):
    resp = client.post("/alerts/ingest", json=_INGEST_BODY, headers=H_ANALYST)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["duplicate"] is False
    assert body["status"] == "new"
    assert body["alert_id"]


def test_ingest_same_idempotency_key_returns_200_same_alert_id_not_duplicated(client):
    first = client.post("/alerts/ingest", json=_INGEST_BODY, headers=H_ANALYST)
    assert first.status_code == 201
    first_alert_id = first.json()["alert_id"]

    # A second, independently-built Alert (fresh alert_id would be generated client-side --
    # simulated here by a body with NO alert_id field, so the server generates its own) but
    # the SAME idempotency_key -- the real retry/duplicate-submission scenario.
    second = client.post("/alerts/ingest", json=_INGEST_BODY, headers=H_ANALYST)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["duplicate"] is True
    assert body["alert_id"] == first_alert_id  # the ORIGINAL alert, never a second case

    listed = client.get("/alerts", headers=H_ANALYST).json()
    matching = [a for a in listed if a["idempotency_key"] == "a" * 64]
    assert len(matching) == 1  # never duplicated in the store


def test_ingest_without_idempotency_key_always_creates_separately(client):
    body = {k: v for k, v in _INGEST_BODY.items() if k != "idempotency_key"}
    first = client.post("/alerts/ingest", json=body, headers=H_ANALYST)
    second = client.post("/alerts/ingest", json=body, headers=H_ANALYST)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["alert_id"] != second.json()["alert_id"]
    assert second.json()["duplicate"] is False


def test_ingest_rejects_malformed_body(client):
    bad = {k: v for k, v in _INGEST_BODY.items() if k != "model_name"}  # drop a required field
    resp = client.post("/alerts/ingest", json=bad, headers=H_ANALYST)
    assert resp.status_code == 422


def test_ingest_requires_authentication(client):
    resp = client.post("/alerts/ingest", json=_INGEST_BODY)
    assert resp.status_code == 401


def test_ingest_rejects_service_role_key(client, service, monkeypatch):
    """A bare, unprefixed key defaults to role 'service' (per RBAC.md), which satisfies no
    case-management route -- confirms /alerts/ingest enforces the same role matrix as
    POST /alerts, never a bypass for scoring-service callers."""
    monkeypatch.setenv(
        "AML_RISKIQ_API_KEYS",
        "analyst:key-analyst,investigator:key-inv,compliance_officer:key-comp,"
        "admin:key-admin,bare-service-key",
    )
    import importlib
    import sys

    sys.modules.pop("serving.case_management_service", None)
    sys.modules.pop("serving._security", None)
    module = importlib.reload(importlib.import_module("serving.case_management_service"))
    from fastapi.testclient import TestClient

    fresh_client = TestClient(module.app)
    resp = fresh_client.post("/alerts/ingest", json=_INGEST_BODY, headers={"X-API-Key": "bare-service-key"})
    assert resp.status_code == 403


def test_ingest_accepted_for_investigator_and_compliance_officer_too(client):
    body1 = {**_INGEST_BODY, "idempotency_key": "b" * 64}
    body2 = {**_INGEST_BODY, "idempotency_key": "c" * 64}
    resp1 = client.post("/alerts/ingest", json=body1, headers=H_INV)
    resp2 = client.post("/alerts/ingest", json=body2, headers=H_COMP)
    assert resp1.status_code == 201
    assert resp2.status_code == 201


def test_health_reports_unresolved_alerts_count(client):
    before = client.get("/health").json()["unresolved_alerts"]
    client.post("/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "d" * 64}, headers=H_ANALYST)
    after = client.get("/health").json()["unresolved_alerts"]
    assert after == before + 1


def test_ingest_observability_metrics_recorded(client):
    client.post("/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "e" * 64}, headers=H_ANALYST)
    client.post("/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "e" * 64}, headers=H_ANALYST)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "alert_ingest_created_total" in resp.text
    assert "alert_ingest_duplicate_total" in resp.text


def test_ingest_preserves_model_provenance_and_severity(client):
    resp = client.post(
        "/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "f" * 64}, headers=H_ANALYST
    )
    alert_id = resp.json()["alert_id"]
    fetched = client.get(f"/alerts/{alert_id}", headers=H_ANALYST).json()
    assert fetched["severity"] == "high"
    assert fetched["generation_source"] == "automated_scoring"
    assert fetched["risk_score"] == 0.9
    assert fetched["selected_threshold"] == 0.5
    assert fetched["model_name"] == "xgboost_v1"


# -- RBAC/audit-trail/lifecycle integrity unaffected by the new ingestion path (requirement ---
# -- 5, verified explicitly rather than assumed from the generic middleware coverage above) --


def test_ingest_emits_structured_audit_log_line(client, caplog):
    """The real AuditLogMiddleware wraps every route, including the new one -- confirmed
    directly rather than assumed, same discipline as
    test_requests_emit_structured_audit_log_lines above."""
    import logging

    with caplog.at_level(logging.INFO, logger="aml_riskiq.audit"):
        caplog.clear()
        resp = client.post(
            "/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "g" * 64}, headers=H_ANALYST
        )
        records = [r for r in caplog.records if r.name == "aml_riskiq.audit"]
    assert resp.status_code == 201
    assert len(records) >= 1
    record = json.loads(records[-1].message)
    assert record["service"] == "case_management_service"
    assert record["method"] == "POST"
    assert record["path"] == "/alerts/ingest"
    assert record["status_code"] == 201
    assert record["caller_id"] != "anonymous"
    assert "key-analyst" not in json.dumps(record)


def test_ingest_created_alert_has_full_investigation_lifecycle_available(client):
    """An alert created via /alerts/ingest is not a second-class record -- it goes through
    the exact same store.create_alert_idempotent() -> _insert_alert_row() code path as a
    manually created one, so assignment, notes, evidence, transitions, and hash-chain
    integrity verification all work on it identically. Exercises the whole chain end to
    end, not just one call."""
    resp = client.post(
        "/alerts/ingest", json={**_INGEST_BODY, "idempotency_key": "h" * 64}, headers=H_ANALYST
    )
    alert_id = resp.json()["alert_id"]
    assert resp.json()["status"] == "new"  # requirement: never created pre-resolved

    assign = client.post(f"/alerts/{alert_id}/assign", json={"assignee": "inv-1"}, headers=H_INV)
    assert assign.status_code == 200

    note = client.post(f"/alerts/{alert_id}/notes", json={"text": "reviewing"}, headers=H_INV)
    assert note.status_code == 201

    evidence = client.post(f"/alerts/{alert_id}/evidence", json={"description": "txn log"}, headers=H_INV)
    assert evidence.status_code == 201

    transition = client.post(
        f"/alerts/{alert_id}/transition", json={"to_status": "under_review"}, headers=H_INV
    )
    assert transition.status_code == 200

    # Investigator cannot close -- compliance-officer sign-off is still required, same as
    # for a manually created alert (requirement: "Enforce the existing role-based
    # permissions").
    closed_by_investigator = client.post(
        f"/alerts/{alert_id}/transition", json={"to_status": "closed"}, headers=H_INV
    )
    assert closed_by_investigator.status_code == 403

    closed = client.post(f"/alerts/{alert_id}/transition", json={"to_status": "closed"}, headers=H_COMP)
    assert closed.status_code == 200

    integrity = client.get(f"/alerts/{alert_id}/integrity", headers=H_COMP)
    assert integrity.status_code == 200
    assert integrity.json()["verified"] is True
