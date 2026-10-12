"""End-to-end automated tests for the scoring-to-alert workflow (requirement 6 of the
end-to-end AML workflow integration phase, 2026-10-12): normal scoring, threshold-triggered
alerts, duplicate submissions, service failures, retries, authorization failures, and
audit-history verification.

What makes these END-TO-END rather than unit tests: every call here goes through the REAL
`serving/_alert_dispatch.py` client (dispatch_alert() / maybe_generate_and_dispatch_alert() /
replay_outbox(), unmocked) talking to the REAL, in-process `case_management_service.py`
FastAPI app -- RBAC, idempotent SQLite persistence (store.py's real UNIQUE index), the real
case-lifecycle state machine, and the real hash-chain audit trail all actually run. The only
thing replaced is the network socket: a real, synchronous ASGI-backed httpx transport (see
the `transport` fixture below) drives the real ASGI app directly in-process, so there is no
live port, no Docker, and no flakiness from real networking, while
every other layer is the real code path a live deployment would execute.

Scope discipline: this file never imports a real BP1-BP5 scoring service module (that would
require a real trained model artifact, out of scope for "do not introduce a new ML model").
It calls `maybe_generate_and_dispatch_alert()` directly with hand-supplied scoring results --
exactly the call every BP's own `/score` route now makes (see e.g.
tests/integration/bp1_transaction_monitoring_detection/test_bp1_scoring_service.py's own,
narrower, mocked-transport wiring tests) -- so what is proven here is the INTEGRATION, not
any BP's model quality.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import httpx
import pytest

_SRC_PATH = str(Path(__file__).resolve().parents[3] / "src" / "aml_riskiq")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

from serving._alert_dispatch import (  # noqa: E402
    dispatch_alert,
    maybe_generate_and_dispatch_alert,
    outbox_path_for,
    replay_outbox,
)

ANALYST_KEY = "e2e-analyst-key"
INVESTIGATOR_KEY = "e2e-inv-key"
COMPLIANCE_KEY = "e2e-comp-key"


@pytest.fixture()
def case_service(tmp_path, monkeypatch):
    """Fresh import of the REAL case_management_service.py, pointed at a temporary SQLite
    file, with a real 3-role API-key set configured -- identical fixture discipline to
    tests/integration/case_management/test_case_management_service.py's own `service`
    fixture, so this file's app instance is not a stand-in, it is the same real module."""
    db_path = tmp_path / "casework_e2e.db"
    monkeypatch.setenv("AML_RISKIQ_CASE_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "AML_RISKIQ_API_KEYS",
        f"analyst:{ANALYST_KEY},investigator:{INVESTIGATOR_KEY},compliance_officer:{COMPLIANCE_KEY}",
    )
    monkeypatch.delenv("AML_RISKIQ_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("AML_RISKIQ_CASE_RATE_LIMIT", raising=False)

    sys.modules.pop("serving.case_management_service", None)
    sys.modules.pop("serving._security", None)
    sys.modules.pop("casework.store", None)
    module = importlib.import_module("serving.case_management_service")
    yield module
    sys.modules.pop("serving.case_management_service", None)


@pytest.fixture()
def transport(case_service):
    """The real Case Management Service ASGI app, driven in-process -- no live port.

    httpx.ASGITransport only implements the ASYNC transport protocol
    (handle_async_request), but serving/_alert_dispatch.py's dispatch_alert() uses a plain
    synchronous httpx.Client (a deliberate design choice -- see that module's own docstring
    on why alert delivery must not block /score behind an async event loop). Starlette's
    own TestClient solves exactly this mismatch for its own synchronous test usage via a
    private `_TestClientTransport` (a real httpx.BaseTransport with a working, synchronous
    handle_request() that runs the real ASGI app through an anyio portal) -- reusing that
    object (TestClient(app)._transport) rather than raw ASGITransport is what makes it
    possible to drive the real app from a synchronous client in this end-to-end test."""
    from fastapi.testclient import TestClient

    return TestClient(case_service.app)._transport


@pytest.fixture()
def direct_client(transport):
    """A plain httpx.Client wired to the same transport, for test assertions that read back
    through the real HTTP+RBAC layer (not the store object directly) -- proving the alert is
    genuinely reachable via the real API, not just present in the DB file."""
    return httpx.Client(transport=transport, base_url="http://case-mgmt")


class _FlakyTransport(httpx.BaseTransport):
    """Wraps a real transport and fails the first `fail_times` requests with a connection
    error before delegating to the real one -- simulates a real transient Case Management
    Service outage (a pod restarting, a brief network blip) without touching any real
    socket. Delegating to the REAL transport on eventual success is what makes this an
    end-to-end test of the retry path, not a mock of it."""

    def __init__(self, real_transport: httpx.BaseTransport, fail_times: int):
        self._real = real_transport
        self._fail_times = fail_times
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise httpx.ConnectError("simulated transient Case Management Service outage", request=request)
        return self._real.handle_request(request)


def _score_kwargs(**overrides) -> dict:
    defaults = dict(
        service_name="bp1_scoring_service",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-e2e-1",
        is_flagged=True,
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="xgboost_v1",
        api_key=ANALYST_KEY,
    )
    defaults.update(overrides)
    return defaults


# -- normal scoring / threshold-triggered alerts ----------------------------------------------


def test_e2e_flagged_scoring_result_creates_real_case_management_alert(transport, direct_client, tmp_path):
    result = maybe_generate_and_dispatch_alert(
        **_score_kwargs(),
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=transport,
    )
    assert result["status"] == "delivered"
    alert_id = result["alert_id"]

    fetched = direct_client.get(f"/alerts/{alert_id}", headers={"X-API-Key": ANALYST_KEY})
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["entity_ref"] == "acct-e2e-1"
    assert body["risk_score"] == 0.9
    assert body["selected_threshold"] == 0.5
    assert body["model_name"] == "xgboost_v1"
    assert body["generation_source"] == "automated_scoring"
    assert body["severity"] == result["severity"]
    assert body["idempotency_key"] == result["idempotency_key"]
    assert body["status"] == "new"  # never created pre-resolved


def test_e2e_below_threshold_scoring_result_creates_no_alert(transport, direct_client, tmp_path):
    result = maybe_generate_and_dispatch_alert(
        **_score_kwargs(is_flagged=False, risk_score=0.1),
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=transport,
    )
    assert result is None

    listed = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY})
    assert listed.json() == []


# -- duplicate submissions ----------------------------------------------------------------------


def test_e2e_duplicate_submission_does_not_create_a_second_case(transport, direct_client, tmp_path):
    kwargs = dict(
        **_score_kwargs(),
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=transport,
    )
    first = maybe_generate_and_dispatch_alert(**kwargs)
    second = maybe_generate_and_dispatch_alert(**kwargs)

    assert first["status"] == "delivered"
    assert second["status"] == "duplicate"
    assert first["alert_id"] == second["alert_id"]
    assert first["idempotency_key"] == second["idempotency_key"]

    listed = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY}).json()
    matching = [a for a in listed if a["entity_ref"] == "acct-e2e-1"]
    assert len(matching) == 1  # the real store, read back through the real API


# -- service failures / retries -----------------------------------------------------------------


def test_e2e_transient_outage_then_recovery_delivers_on_retry(case_service, transport, direct_client, tmp_path):
    flaky = _FlakyTransport(transport, fail_times=1)
    result = maybe_generate_and_dispatch_alert(
        **_score_kwargs(entity_ref="acct-e2e-flaky"),
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=flaky,
        max_attempts=2,
    )
    assert result["status"] == "delivered"
    assert flaky.calls == 2  # 1 simulated failure, then a real successful delivery

    listed = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY}).json()
    assert any(a["entity_ref"] == "acct-e2e-flaky" for a in listed)


def test_e2e_persistent_outage_queues_then_replay_recovers(case_service, transport, direct_client, tmp_path):
    """Requirement: "do not silently lose alerts when the case-management service is
    unavailable" + "failures are visible and recoverable". Exercises the FULL outage ->
    outbox -> replay_outbox() -> real delivery loop against the real app."""
    always_down = _FlakyTransport(transport, fail_times=999)
    outbox_dir = tmp_path / "outbox"
    result = maybe_generate_and_dispatch_alert(
        **_score_kwargs(entity_ref="acct-e2e-outage"),
        case_service_url="http://case-mgmt",
        outbox_dir=outbox_dir,
        transport=always_down,
        max_attempts=1,
    )
    assert result["status"] == "queued_for_retry"
    outbox_file = outbox_path_for("bp1_scoring_service", outbox_dir=outbox_dir)
    assert outbox_file.exists()

    listed_before = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY}).json()
    assert not any(a["entity_ref"] == "acct-e2e-outage" for a in listed_before)

    # Case Management Service is back -- replay against the REAL transport this time.
    summary = replay_outbox(
        "bp1_scoring_service",
        outbox_dir=outbox_dir,
        case_service_url="http://case-mgmt",
        api_key=ANALYST_KEY,
        transport=transport,
    )
    assert summary["delivered"] == 1
    assert not outbox_file.exists()  # fully drained

    listed_after = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY}).json()
    assert any(a["entity_ref"] == "acct-e2e-outage" for a in listed_after)


# -- authorization failures ---------------------------------------------------------------------


def test_e2e_wrong_case_service_api_key_is_rejected_and_creates_no_alert(transport, direct_client, tmp_path):
    outbox_dir = tmp_path / "outbox"
    result = maybe_generate_and_dispatch_alert(
        **{**_score_kwargs(entity_ref="acct-e2e-badkey"), "api_key": "totally-wrong-key"},
        case_service_url="http://case-mgmt",
        outbox_dir=outbox_dir,
        transport=transport,
        max_attempts=3,
    )
    assert result["status"] == "rejected"
    assert result["http_status"] == 401
    outbox_file = outbox_path_for("bp1_scoring_service", outbox_dir=outbox_dir)
    assert outbox_file.exists()  # visible, not silently dropped

    listed = direct_client.get("/alerts", headers={"X-API-Key": ANALYST_KEY}).json()
    assert not any(a["entity_ref"] == "acct-e2e-badkey" for a in listed)


def test_e2e_case_service_key_with_insufficient_role_is_rejected(
    case_service, transport, direct_client, tmp_path, monkeypatch
):
    """A real key configured with a role /alerts/ingest does not accept (bare, unprefixed ->
    'service') gets a real 403 from the real RBAC layer -- confirmed end to end, not
    assumed."""
    monkeypatch.setenv(
        "AML_RISKIQ_API_KEYS",
        f"analyst:{ANALYST_KEY},investigator:{INVESTIGATOR_KEY},compliance_officer:{COMPLIANCE_KEY},bare-bp-key",
    )
    reloaded = importlib.reload(case_service)
    from fastapi.testclient import TestClient

    fresh_transport = TestClient(reloaded.app)._transport

    result = maybe_generate_and_dispatch_alert(
        **{**_score_kwargs(entity_ref="acct-e2e-wrongrole"), "api_key": "bare-bp-key"},
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=fresh_transport,
        max_attempts=3,
    )
    assert result["status"] == "rejected"
    assert result["http_status"] == 403


# -- audit-history verification -----------------------------------------------------------------


def test_e2e_full_lifecycle_and_audit_history_verification(transport, direct_client, tmp_path):
    """The complete real pipeline in one test: a scoring result dispatches a real alert into
    the real Case Management Service; an investigator works it (assign, note, transition);
    a compliance officer closes it; the real hash-chain audit trail verifies clean. Proves
    requirement 5 (investigation lifecycle wired to alert creation, RBAC enforced
    throughout) end to end against the real app, not a unit-level assumption."""
    result = maybe_generate_and_dispatch_alert(
        **_score_kwargs(entity_ref="acct-e2e-lifecycle"),
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path / "outbox",
        transport=transport,
    )
    assert result["status"] == "delivered"
    alert_id = result["alert_id"]

    assign = direct_client.post(
        f"/alerts/{alert_id}/assign",
        json={"assignee": "inv-1"},
        headers={"X-API-Key": INVESTIGATOR_KEY},
    )
    assert assign.status_code == 200

    note = direct_client.post(
        f"/alerts/{alert_id}/notes",
        json={"text": "reviewed the underlying scoring result"},
        headers={"X-API-Key": INVESTIGATOR_KEY},
    )
    assert note.status_code == 201

    under_review = direct_client.post(
        f"/alerts/{alert_id}/transition",
        json={"to_status": "under_review"},
        headers={"X-API-Key": INVESTIGATOR_KEY},
    )
    assert under_review.status_code == 200

    # RBAC still enforced on the automated-origin alert: investigator cannot sign off.
    blocked = direct_client.post(
        f"/alerts/{alert_id}/transition",
        json={"to_status": "closed"},
        headers={"X-API-Key": INVESTIGATOR_KEY},
    )
    assert blocked.status_code == 403

    closed = direct_client.post(
        f"/alerts/{alert_id}/transition",
        json={"to_status": "closed"},
        headers={"X-API-Key": COMPLIANCE_KEY},
    )
    assert closed.status_code == 200

    integrity = direct_client.get(f"/alerts/{alert_id}/integrity", headers={"X-API-Key": COMPLIANCE_KEY})
    assert integrity.status_code == 200
    body = integrity.json()
    assert body["verified"] is True

    final = direct_client.get(f"/alerts/{alert_id}", headers={"X-API-Key": COMPLIANCE_KEY}).json()
    assert final["status"] == "closed"
    assert final["generation_source"] == "automated_scoring"  # provenance preserved throughout
    assert len(final["history"]) >= 2  # under_review + closed, at minimum
