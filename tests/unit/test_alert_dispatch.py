"""Tests for src/aml_riskiq/serving/_alert_dispatch.py -- the reliable scoring-to-alert
delivery client added for the end-to-end AML workflow integration phase (2026-10-12).
Covers successful delivery, duplicate-response handling, retry-then-success, exhausted
retries writing to and being readable from the outbox, non-retryable rejection, the
not-configured path, every skip path in maybe_generate_and_dispatch_alert(), idempotency-key
propagation into the result dict, and replay_outbox() draining a populated outbox file.

Uses httpx.MockTransport throughout -- no live network call, no real Case Management
Service process. (The full end-to-end integration tests, which wire a real FastAPI app via
httpx.ASGITransport, live separately.)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

_src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from casework.alert_schema import Alert  # noqa: E402
from serving._alert_dispatch import (  # noqa: E402
    dispatch_alert,
    maybe_generate_and_dispatch_alert,
    outbox_path_for,
    replay_outbox,
)

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def _alert(**overrides) -> Alert:
    defaults = dict(
        entity_ref="acct-001",
        business_problem="BP1",
        detection_source="xgboost_champion",
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
        scoring_timestamp=NOW,
        idempotency_key="deadbeef" * 8,
        severity="high",
        generation_source="automated_scoring",
    )
    defaults.update(overrides)
    return Alert(**defaults)


# -- dispatch_alert: success / duplicate --------------------------------------------------


def test_dispatch_alert_success_first_attempt(tmp_path):
    def handler(request):
        assert request.url.path == "/alerts/ingest"
        assert request.headers.get("x-api-key") == "k1"
        body = json.loads(request.content)
        assert body["idempotency_key"] == "deadbeef" * 8
        return httpx.Response(201, json={"alert_id": body["alert_id"], "duplicate": False})

    alert = _alert()
    result = dispatch_alert(
        alert,
        service_name="bp1",
        case_service_url="http://case-mgmt",
        api_key="k1",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    assert result == {"status": "delivered", "attempts": 1, "alert_id": alert.alert_id}
    assert not outbox_path_for("bp1", outbox_dir=tmp_path).exists()


def test_dispatch_alert_duplicate_response_not_treated_as_failure(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"alert_id": "existing-id", "duplicate": True})

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    assert result["status"] == "duplicate"
    assert result["alert_id"] == "existing-id"
    assert not outbox_path_for("bp1", outbox_dir=tmp_path).exists()


# -- dispatch_alert: retry behavior ----------------------------------------------------------


def test_dispatch_alert_retries_on_timeout_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.TimeoutException("slow", request=request)
        return httpx.Response(201, json={"alert_id": "a1", "duplicate": False})

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=2,
        backoff_base=0.0,
    )
    assert result["status"] == "delivered"
    assert result["attempts"] == 2
    assert attempts["n"] == 2
    assert not outbox_path_for("bp1", outbox_dir=tmp_path).exists()


def test_dispatch_alert_retries_on_5xx_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json={"alert_id": "a1", "duplicate": False})

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=2,
        backoff_base=0.0,
    )
    assert result["status"] == "delivered"
    assert attempts["n"] == 2


def test_dispatch_alert_exhausts_retries_writes_outbox(tmp_path):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    alert = _alert()
    result = dispatch_alert(
        alert,
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=2,
        backoff_base=0.0,
    )
    assert result["status"] == "queued_for_retry"
    assert result["attempts"] == 2
    outbox = outbox_path_for("bp1", outbox_dir=tmp_path)
    assert outbox.exists()
    lines = outbox.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["alert"]["alert_id"] == alert.alert_id
    assert record["reason"] == "delivery_exhausted"


def test_dispatch_alert_non_retryable_status_is_rejected_not_retried(tmp_path):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(422, text="bad request")

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        backoff_base=0.0,
    )
    assert result["status"] == "rejected"
    assert result["http_status"] == 422
    assert attempts["n"] == 1  # never retried
    outbox = outbox_path_for("bp1", outbox_dir=tmp_path)
    assert outbox.exists()
    record = json.loads(outbox.read_text().strip().splitlines()[0])
    assert record["reason"] == "rejected"


def test_dispatch_alert_not_configured_queues_immediately(tmp_path, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_CASE_SERVICE_URL", raising=False)
    alert = _alert()
    result = dispatch_alert(alert, service_name="bp1", outbox_dir=tmp_path)
    assert result == {"status": "queued_for_retry", "reason": "not_configured", "attempts": 0}
    outbox = outbox_path_for("bp1", outbox_dir=tmp_path)
    assert outbox.exists()
    record = json.loads(outbox.read_text().strip().splitlines()[0])
    assert record["reason"] == "case_service_url_not_configured"


def test_dispatch_alert_never_raises_on_persistent_failure(tmp_path):
    """The one hard requirement: a /score response must never fail because alert delivery
    had trouble."""

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    try:
        result = dispatch_alert(
            _alert(),
            service_name="bp1",
            case_service_url="http://case-mgmt",
            outbox_dir=tmp_path,
            transport=httpx.MockTransport(handler),
            max_attempts=1,
            backoff_base=0.0,
        )
    except Exception as exc:  # pragma: no cover -- this must never happen
        pytest.fail(f"dispatch_alert raised instead of returning a result dict: {exc}")
    assert result["status"] == "queued_for_retry"


# -- maybe_generate_and_dispatch_alert: skip paths -------------------------------------------


def test_maybe_generate_skips_missing_entity_ref():
    result = maybe_generate_and_dispatch_alert(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref=None,
        is_flagged=True,
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
    )
    assert result is None


def test_maybe_generate_skips_when_not_flagged():
    result = maybe_generate_and_dispatch_alert(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        is_flagged=False,
        risk_score=0.1,
        selected_threshold=0.5,
        model_name="XGBoost",
    )
    assert result is None


def test_maybe_generate_skips_missing_score_or_threshold():
    result = maybe_generate_and_dispatch_alert(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        is_flagged=True,
        risk_score=None,
        selected_threshold=0.5,
        model_name="XGBoost",
    )
    assert result == {"status": "skipped", "reason": "missing_score_or_threshold"}


def test_maybe_generate_skips_schema_validation_failure():
    result = maybe_generate_and_dispatch_alert(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        is_flagged=True,
        risk_score=float("nan"),
        selected_threshold=0.5,
        model_name="XGBoost",
    )
    assert result == {"status": "skipped", "reason": "schema_validation_failed"}


# -- maybe_generate_and_dispatch_alert: happy path -------------------------------------------


def test_maybe_generate_happy_path_dispatches_and_merges_result_fields(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(201, json={"alert_id": body["alert_id"], "duplicate": False})

    result = maybe_generate_and_dispatch_alert(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        is_flagged=True,
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    assert result["status"] == "delivered"
    assert result["severity"] == "high"  # ratio 1.8
    assert len(result["idempotency_key"]) == 64
    assert result["alert_id"]


def test_maybe_generate_same_event_twice_has_stable_idempotency_key(tmp_path):
    def handler(request):
        return httpx.Response(201, json={"alert_id": "a1", "duplicate": False})

    kwargs = dict(
        service_name="bp1",
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        is_flagged=True,
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    r1 = maybe_generate_and_dispatch_alert(**kwargs)
    r2 = maybe_generate_and_dispatch_alert(**kwargs)
    assert r1["idempotency_key"] == r2["idempotency_key"]


# -- replay_outbox -----------------------------------------------------------------------------


def test_replay_outbox_no_file_returns_zero_summary(tmp_path):
    summary = replay_outbox("bp1", outbox_dir=tmp_path)
    assert summary == {"attempted": 0, "delivered": 0, "duplicate": 0, "rejected": 0, "still_failed": 0}


def test_replay_outbox_drains_populated_outbox_on_success(tmp_path):
    # Queue 2 records the way dispatch_alert() itself would (exhausted retries).
    def failing_handler(request):
        raise httpx.ConnectError("refused", request=request)

    dispatch_alert(
        _alert(idempotency_key="a" * 64),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(failing_handler),
        max_attempts=1,
        backoff_base=0.0,
    )
    dispatch_alert(
        _alert(idempotency_key="b" * 64),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(failing_handler),
        max_attempts=1,
        backoff_base=0.0,
    )
    outbox = outbox_path_for("bp1", outbox_dir=tmp_path)
    assert len(outbox.read_text().strip().splitlines()) == 2

    def succeeding_handler(request):
        body = json.loads(request.content)
        return httpx.Response(201, json={"alert_id": body["alert_id"], "duplicate": False})

    summary = replay_outbox(
        "bp1",
        outbox_dir=tmp_path,
        case_service_url="http://case-mgmt",
        transport=httpx.MockTransport(succeeding_handler),
    )
    assert summary["attempted"] == 2
    assert summary["delivered"] == 2
    assert summary["still_failed"] == 0
    assert not outbox.exists()  # fully drained


def test_replay_outbox_leaves_still_failed_records_queued(tmp_path):
    def failing_handler(request):
        raise httpx.ConnectError("refused", request=request)

    dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(failing_handler),
        max_attempts=1,
        backoff_base=0.0,
    )
    summary = replay_outbox(
        "bp1",
        outbox_dir=tmp_path,
        case_service_url="http://case-mgmt",
        transport=httpx.MockTransport(failing_handler),
    )
    assert summary["attempted"] == 1
    assert summary["still_failed"] == 1
    outbox = outbox_path_for("bp1", outbox_dir=tmp_path)
    assert outbox.exists()
    assert len(outbox.read_text().strip().splitlines()) == 1


def test_replay_outbox_recognizes_duplicate_as_resolved(tmp_path):
    """A record already delivered on a prior replay attempt (service restarted mid-replay,
    say) must be recognized as a duplicate, not redelivered as a second alert, and removed
    from the outbox either way -- it is resolved, not a failure."""

    def failing_handler(request):
        raise httpx.ConnectError("refused", request=request)

    dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(failing_handler),
        max_attempts=1,
        backoff_base=0.0,
    )

    def duplicate_handler(request):
        return httpx.Response(200, json={"alert_id": "a1", "duplicate": True})

    summary = replay_outbox(
        "bp1",
        outbox_dir=tmp_path,
        case_service_url="http://case-mgmt",
        transport=httpx.MockTransport(duplicate_handler),
    )
    assert summary["duplicate"] == 1
    assert summary["still_failed"] == 0
    assert not outbox_path_for("bp1", outbox_dir=tmp_path).exists()


def test_dispatch_alert_401_is_rejected_not_retried(tmp_path):
    """A 401 means this service's own configured case-management API key is wrong -- retrying
    the identical credential against the identical route can never succeed, so it must be
    treated the same as a 422/404 (a definitive rejection), never retried like a transient
    429/5xx."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(401, text="invalid api key")

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        backoff_base=0.0,
    )
    assert result["status"] == "rejected"
    assert result["http_status"] == 401
    assert attempts["n"] == 1


def test_dispatch_alert_403_is_rejected_not_retried(tmp_path):
    def handler(request):
        return httpx.Response(403, text="role not permitted")

    result = dispatch_alert(
        _alert(),
        service_name="bp1",
        case_service_url="http://case-mgmt",
        outbox_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        backoff_base=0.0,
    )
    assert result["status"] == "rejected"
    assert result["http_status"] == 403
