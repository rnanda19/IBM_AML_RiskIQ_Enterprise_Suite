"""
Tests for src/aml_riskiq/serving/_security.py -- the shared API-key auth / rate-limiting / audit-
logging module every BP1-BP5 FastAPI scoring service imports (HYPER pattern: written once,
verified once here, rather than five separate ad hoc partial tests).

Scope: this file tests _security.py's OWN logic in isolation (env-var-driven open/closed
auth mode, constant-time key comparison, fingerprinting, rate-limit string resolution) and
one small real FastAPI app built just for these tests, exercising the exact same
`require_api_key` / `harden_app` / `score_rate_limit` wiring every real service uses. It does
not import a real BP scoring service -- that integration-level coverage (the real services
actually mounting this module correctly) is in each service's own test file, e.g.
tests/integration/bp1_transaction_monitoring_detection/test_bp1_scoring_service.py's
test_score_requires_api_key_when_configured.
"""

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def security_module(monkeypatch):
    """Fresh import of _security.py with no env vars set (open mode is the default state
    for every other test in this suite, so each test here sets only what it needs)."""
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    monkeypatch.delenv("AML_RISKIQ_SCORE_RATE_LIMIT", raising=False)
    sys.modules.pop("serving._security", None)
    src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    module = importlib.import_module("serving._security")
    yield module
    sys.modules.pop("serving._security", None)


def test_open_mode_when_env_var_unset(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    assert security_module._configured_api_keys() is None


def test_closed_mode_when_env_var_set(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "key-one, key-two")
    assert security_module._configured_api_keys() == {"key-one", "key-two"}


def test_require_api_key_open_mode_returns_anonymous(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    assert security_module.require_api_key(x_api_key=None) == "anonymous"


def test_require_api_key_closed_mode_missing_header_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "real-key")
    with pytest.raises(HTTPException) as exc_info:
        security_module.require_api_key(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_require_api_key_closed_mode_wrong_key_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "real-key")
    with pytest.raises(HTTPException) as exc_info:
        security_module.require_api_key(x_api_key="wrong-key")
    assert exc_info.value.status_code == 401


def test_require_api_key_closed_mode_correct_key_returns_fingerprint(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "real-key")
    result = security_module.require_api_key(x_api_key="real-key")
    assert result == security_module._key_fingerprint("real-key")
    assert result != "real-key"  # never returns the raw key


def test_key_fingerprint_is_deterministic_and_non_reversible(security_module):
    fp1 = security_module._key_fingerprint("some-secret-key")
    fp2 = security_module._key_fingerprint("some-secret-key")
    assert fp1 == fp2
    assert len(fp1) == 8
    assert "some-secret-key" not in fp1


def test_score_rate_limit_default(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_SCORE_RATE_LIMIT", raising=False)
    assert security_module.score_rate_limit() == security_module.DEFAULT_SCORE_RATE_LIMIT


def test_score_rate_limit_override(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_SCORE_RATE_LIMIT", "5/second")
    assert security_module.score_rate_limit() == "5/second"


def test_harden_app_wires_limiter_and_audit_middleware(security_module):
    """End-to-end on a small real FastAPI app -- confirms harden_app() actually attaches a
    working limiter + audit middleware + exception handler, not just that the helper
    functions above are individually correct."""
    from fastapi import Depends, FastAPI, Request
    from fastapi.testclient import TestClient

    app = FastAPI()
    limiter = security_module.harden_app(app, "test_service")
    require_api_key = security_module.require_api_key

    @app.get("/protected")
    @limiter.limit("2/minute")
    def protected(request: Request, _caller: str = Depends(require_api_key)):
        return {"ok": True}

    client = TestClient(app)

    # Open mode (no AML_RISKIQ_API_KEYS set by this test) -- no auth required.
    resp1 = client.get("/protected")
    assert resp1.status_code == 200

    resp2 = client.get("/protected")
    assert resp2.status_code == 200

    # Third call within the same minute exceeds the 2/minute limit configured above.
    resp3 = client.get("/protected")
    assert resp3.status_code == 429


def test_harden_app_enforces_api_key_when_configured(security_module, monkeypatch):
    from fastapi import Depends, FastAPI, Request
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "test-key-123")

    app = FastAPI()
    limiter = security_module.harden_app(app, "test_service")
    require_api_key = security_module.require_api_key

    @app.get("/protected")
    @limiter.limit("100/minute")
    def protected(request: Request, _caller: str = Depends(require_api_key)):
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"X-API-Key": "wrong"}).status_code == 401
    resp = client.get("/protected", headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200


def test_warn_if_open_mode_prints_warning_when_require_auth_unset(security_module, monkeypatch, capsys):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    monkeypatch.delenv("AML_RISKIQ_REQUIRE_AUTH", raising=False)
    security_module.warn_if_open_mode("test_service")
    assert "WARNING" in capsys.readouterr().err


def test_warn_if_open_mode_raises_when_require_auth_true_and_no_keys(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    monkeypatch.setenv("AML_RISKIQ_REQUIRE_AUTH", "true")
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        security_module.warn_if_open_mode("test_service")


def test_warn_if_open_mode_does_not_raise_when_require_auth_true_and_keys_set(
    security_module, monkeypatch, capsys
):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "real-key")
    monkeypatch.setenv("AML_RISKIQ_REQUIRE_AUTH", "true")
    security_module.warn_if_open_mode("test_service")  # should not raise
    assert "WARNING" not in capsys.readouterr().err


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_require_auth_enabled_truthy_values(security_module, monkeypatch, value):
    monkeypatch.setenv("AML_RISKIQ_REQUIRE_AUTH", value)
    assert security_module._require_auth_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", None])
def test_require_auth_enabled_falsy_values(security_module, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("AML_RISKIQ_REQUIRE_AUTH", raising=False)
    else:
        monkeypatch.setenv("AML_RISKIQ_REQUIRE_AUTH", value)
    assert security_module._require_auth_enabled() is False


def test_harden_app_raises_when_require_auth_true_and_no_keys(security_module, monkeypatch):
    """harden_app() must propagate the fail-closed RuntimeError rather than swallow it --
    confirms the gate actually blocks real service startup, not just the helper in isolation."""
    from fastapi import FastAPI

    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    monkeypatch.setenv("AML_RISKIQ_REQUIRE_AUTH", "true")

    app = FastAPI()
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        security_module.harden_app(app, "test_service")


# -- Role-aware API keys / require_role --------------------------------------------------


def test_configured_api_keys_with_roles_bare_key_gets_default_role(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "plain-key")
    assert security_module._configured_api_keys_with_roles() == {"plain-key": "service"}


def test_configured_api_keys_with_roles_parses_role_prefix(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a, admin:key-b, key-c")
    assert security_module._configured_api_keys_with_roles() == {
        "key-a": "investigator",
        "key-b": "admin",
        "key-c": "service",
    }


def test_configured_api_keys_still_returns_bare_key_set(security_module, monkeypatch):
    """_configured_api_keys() (used by require_api_key, unaffected by roles) must still
    return the same bare key set as before role support existed."""
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a,key-b")
    assert security_module._configured_api_keys() == {"key-a", "key-b"}


def test_require_role_open_mode_returns_anonymous(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    dep = security_module.require_role("investigator")
    assert dep(x_api_key=None) == "anonymous"


def test_require_role_missing_header_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_role("investigator")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_require_role_correct_role_succeeds(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_role("investigator")
    result = dep(x_api_key="key-a")
    assert result == security_module._key_fingerprint("key-a")


def test_require_role_wrong_role_raises_403(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_role("admin")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key="key-a")
    assert exc_info.value.status_code == 403


def test_require_role_admin_key_satisfies_any_role(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "admin:key-a")
    dep = security_module.require_role("investigator")
    result = dep(x_api_key="key-a")
    assert result == security_module._key_fingerprint("key-a")


def test_require_role_invalid_key_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_role("investigator")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key="wrong-key")
    assert exc_info.value.status_code == 401


# -- Metrics -------------------------------------------------------------------------------


def test_record_metric_and_render_metrics(security_module):
    security_module._request_counts.clear()
    security_module._latency_sums.clear()
    security_module._record_metric("svc", "GET", "/health", 200, 12.5)
    security_module._record_metric("svc", "GET", "/health", 200, 7.5)
    rendered = security_module.render_metrics()
    assert 'aml_riskiq_requests_total{service="svc",method="GET",path="/health",status="200"} 2' in rendered
    assert "aml_riskiq_request_latency_seconds_sum" in rendered


def test_wire_metrics_endpoint_serves_real_counts(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    security_module._request_counts.clear()
    security_module._latency_sums.clear()

    app = FastAPI()
    security_module.harden_app(app, "metrics_test_service")
    security_module.wire_metrics_endpoint(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)
    client.get("/health")
    client.get("/health")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert 'service="metrics_test_service"' in resp.text
    assert 'path="/health"' in resp.text


# -- resolve_caller_role / require_any_role (RBAC phase, 2026-10-12) -----------------------


def test_resolve_caller_role_open_mode(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    assert security_module.resolve_caller_role(None) == ("anonymous", "anonymous")
    assert security_module.resolve_caller_role("anything") == ("anonymous", "anonymous")


def test_resolve_caller_role_no_header_closed_mode(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    assert security_module.resolve_caller_role(None) == ("none", "anonymous")


def test_resolve_caller_role_invalid_key(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    assert security_module.resolve_caller_role("wrong-key") == ("invalid", "anonymous")


def test_resolve_caller_role_matches_configured_role(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "compliance_officer:key-c")
    role, caller_id = security_module.resolve_caller_role("key-c")
    assert role == "compliance_officer"
    assert caller_id == security_module._key_fingerprint("key-c")


def test_require_any_role_open_mode_returns_anonymous(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_API_KEYS", raising=False)
    dep = security_module.require_any_role("investigator", "compliance_officer")
    assert dep(x_api_key=None) == "anonymous"


def test_require_any_role_missing_header_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_require_any_role_invalid_key_raises_401(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key="wrong-key")
    assert exc_info.value.status_code == 401


def test_require_any_role_accepts_first_listed_role(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "investigator:key-a")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    assert dep(x_api_key="key-a") == security_module._key_fingerprint("key-a")


def test_require_any_role_accepts_second_listed_role(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "compliance_officer:key-b")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    assert dep(x_api_key="key-b") == security_module._key_fingerprint("key-b")


def test_require_any_role_rejects_role_not_in_set(security_module, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "analyst:key-z")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    with pytest.raises(HTTPException) as exc_info:
        dep(x_api_key="key-z")
    assert exc_info.value.status_code == 403


def test_require_any_role_admin_satisfies_any_set(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "admin:key-admin")
    dep = security_module.require_any_role("investigator", "compliance_officer")
    assert dep(x_api_key="key-admin") == security_module._key_fingerprint("key-admin")


def test_require_role_still_works_after_refactor(security_module, monkeypatch):
    """require_role() is now sugar for require_any_role(role) -- this re-confirms its
    single-role behavior end to end after the refactor, on top of the pre-existing
    require_role tests above (which also still pass unmodified)."""
    from fastapi import HTTPException

    monkeypatch.setenv("AML_RISKIQ_API_KEYS", "analyst:key-a")
    dep = security_module.require_role("analyst")
    assert dep(x_api_key="key-a") == security_module._key_fingerprint("key-a")
    with pytest.raises(HTTPException) as exc_info:
        security_module.require_role("investigator")(x_api_key="key-a")
    assert exc_info.value.status_code == 403


def test_case_rate_limit_default(security_module, monkeypatch):
    monkeypatch.delenv("AML_RISKIQ_CASE_RATE_LIMIT", raising=False)
    assert security_module.case_rate_limit() == security_module.DEFAULT_CASE_RATE_LIMIT
    assert security_module.DEFAULT_CASE_RATE_LIMIT == "120/minute"


def test_case_rate_limit_override(security_module, monkeypatch):
    monkeypatch.setenv("AML_RISKIQ_CASE_RATE_LIMIT", "10/second")
    assert security_module.case_rate_limit() == "10/second"


def test_platform_roles_constant_contains_all_four(security_module):
    assert security_module.PLATFORM_ROLES == (
        security_module.ANALYST_ROLE,
        security_module.INVESTIGATOR_ROLE,
        security_module.COMPLIANCE_OFFICER_ROLE,
        security_module.ADMIN_ROLE,
    )
    assert security_module.ANALYST_ROLE == "analyst"
    assert security_module.INVESTIGATOR_ROLE == "investigator"
    assert security_module.COMPLIANCE_OFFICER_ROLE == "compliance_officer"


# -- custom business metrics (record_custom_metric / set_custom_gauge) ------------------------
# Added for the end-to-end AML workflow integration phase (2026-10-12): the scoring-to-alert
# dispatch client and the Case Management Service's /alerts/ingest route both need business-
# level counters/gauges the generic per-request metrics (section 6) cannot express on their
# own -- see _security.py's own section-7 docstring for why.


def test_record_custom_metric_increments_and_renders(security_module):
    security_module.record_custom_metric("bp1_scoring_service", "alert_dispatch_delivered_total")
    security_module.record_custom_metric("bp1_scoring_service", "alert_dispatch_delivered_total")
    text = security_module.render_metrics()
    assert "aml_riskiq_alert_dispatch_delivered_total" in text
    assert 'service="bp1_scoring_service"' in text
    assert 'aml_riskiq_alert_dispatch_delivered_total{service="bp1_scoring_service"} 2.0' in text


def test_record_custom_metric_with_labels(security_module):
    security_module.record_custom_metric(
        "bp1_scoring_service", "alert_dispatch_failed_total", labels={"reason": "timeout"}
    )
    text = security_module.render_metrics()
    assert 'reason="timeout"' in text


def test_record_custom_metric_distinct_label_sets_are_separate_series(security_module):
    security_module.record_custom_metric("bp1_scoring_service", "x", labels={"reason": "timeout"})
    security_module.record_custom_metric("bp1_scoring_service", "x", labels={"reason": "rejected"})
    text = security_module.render_metrics()
    assert text.count("aml_riskiq_x{") == 2


def test_set_custom_gauge_sets_not_increments(security_module):
    security_module.set_custom_gauge("case_management_service", "unresolved_alerts", 5)
    security_module.set_custom_gauge("case_management_service", "unresolved_alerts", 3)
    text = security_module.render_metrics()
    assert 'aml_riskiq_unresolved_alerts{service="case_management_service"} 3' in text
    assert "# TYPE aml_riskiq_unresolved_alerts gauge" in text


def test_custom_counter_type_line_is_counter(security_module):
    security_module.record_custom_metric("case_management_service", "alerts_ingested_total")
    text = security_module.render_metrics()
    assert "# TYPE aml_riskiq_alerts_ingested_total counter" in text


def test_render_metrics_includes_both_generic_and_custom_sections(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "svc")
    security_module.wire_metrics_endpoint(app)
    security_module.record_custom_metric("svc", "widgets_total")

    @app.get("/ping")
    def _ping():
        return {"ok": True}

    client = TestClient(app)
    client.get("/ping")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "aml_riskiq_requests_total" in resp.text
    assert "aml_riskiq_widgets_total" in resp.text


# -- _json_safe / RequestValidationError handler (Improvement 3 production-readiness pass,
# 2026-10-12): a NaN/Infinity feature value rejected by FiniteFloatFieldsModel was crashing
# with an unhandled 500 instead of a clean 422, because FastAPI's default validation-error
# handler tries to JSON-serialize the raw offending value (and, for a model-level validator,
# a raw exception object inside pydantic's error ctx) using strict JSON encoding. Confirmed
# against a real running service before this fix; these are the isolated unit-level tests
# for the sanitizer itself. --


def test_json_safe_passes_through_ordinary_values(security_module):
    assert security_module._json_safe({"a": 1, "b": "x", "c": [1, 2, 3]}) == {
        "a": 1,
        "b": "x",
        "c": [1, 2, 3],
    }


def test_json_safe_replaces_nan(security_module):
    assert security_module._json_safe(float("nan")) == "NaN"


def test_json_safe_replaces_positive_infinity(security_module):
    assert security_module._json_safe(float("inf")) == "Infinity"


def test_json_safe_replaces_negative_infinity(security_module):
    assert security_module._json_safe(float("-inf")) == "-Infinity"


def test_json_safe_replaces_exception_objects_with_their_string(security_module):
    exc = ValueError("boom")
    assert security_module._json_safe(exc) == "boom"


def test_json_safe_recurses_into_nested_dicts_and_lists(security_module):
    payload = {
        "detail": [
            {
                "loc": ["body", "hour"],
                "msg": "bad",
                "ctx": {"error": ValueError("nope")},
                "input": float("nan"),
            }
        ]
    }
    sanitized = security_module._json_safe(payload)
    assert sanitized["detail"][0]["ctx"]["error"] == "nope"
    assert sanitized["detail"][0]["input"] == "NaN"


def test_validation_error_handler_returns_422_with_sanitized_body(security_module):
    import json

    from fastapi.exceptions import RequestValidationError

    exc = RequestValidationError(
        errors=[
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, bad",
                "input": {"hour": float("nan")},
                "ctx": {"error": ValueError("bad")},
            }
        ]
    )
    response = security_module._validation_error_handler(request=None, exc=exc)
    assert response.status_code == 422
    body = json.loads(bytes(response.body))
    assert body["detail"][0]["ctx"]["error"] == "bad"
    assert body["detail"][0]["input"]["hour"] == "NaN"


def test_harden_app_wires_validation_error_handler(security_module):
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError

    app = FastAPI()
    security_module.harden_app(app, "test-service")
    assert RequestValidationError in app.exception_handlers


# -- request correlation IDs (Improvement 3 production-readiness pass, 2026-10-12) --


def test_response_gets_a_generated_request_id_when_caller_sends_none(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "corr-test")

    @app.get("/ping")
    def _ping() -> dict:
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert security_module.REQUEST_ID_HEADER in resp.headers
    assert len(resp.headers[security_module.REQUEST_ID_HEADER]) == 36  # a real UUID4 string


def test_response_echoes_back_the_callers_own_request_id(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "corr-test")

    @app.get("/ping")
    def _ping() -> dict:
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/ping", headers={"X-Request-ID": "caller-supplied-id-123"})
    assert resp.headers[security_module.REQUEST_ID_HEADER] == "caller-supplied-id-123"


def test_audit_log_line_includes_the_same_request_id(security_module, caplog):
    import json
    import logging

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "corr-test")

    @app.get("/ping")
    def _ping() -> dict:
        return {"ok": True}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="aml_riskiq.audit"):
        resp = client.get("/ping", headers={"X-Request-ID": "trace-xyz"})
    response_request_id = resp.headers[security_module.REQUEST_ID_HEADER]
    assert response_request_id == "trace-xyz"
    record = json.loads(caplog.records[-1].message)
    assert record["request_id"] == "trace-xyz"


def test_audit_log_defaults_request_id_when_not_supplied(security_module):
    """audit_log() itself is reused outside the middleware (route handlers call it ad hoc);
    confirm it still produces a usable, non-empty request_id when none is passed in."""
    import json
    import logging

    logger = logging.getLogger("aml_riskiq.audit")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    try:
        security_module.audit_log(
            service_name="svc",
            method="GET",
            path="/x",
            status_code=200,
            latency_ms=1.0,
            client_ip="1.2.3.4",
            caller_id="anonymous",
        )
    finally:
        logger.removeHandler(handler)
    payload = json.loads(records[-1].getMessage())
    assert len(payload["request_id"]) == 36


# -- /ready readiness endpoint (Improvement 3 production-readiness pass, 2026-10-12) --


def test_wire_readiness_endpoint_returns_200_when_all_checks_pass(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "ready-test")
    security_module.wire_readiness_endpoint(app, lambda: {"db_ok": True, "model_ok": True})
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"db_ok": True, "model_ok": True}}


def test_wire_readiness_endpoint_returns_503_when_a_check_fails(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "ready-test")
    security_module.wire_readiness_endpoint(app, lambda: {"db_ok": False, "model_ok": True})
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_wire_readiness_endpoint_returns_503_when_check_fn_raises(security_module):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def _boom() -> dict:
        raise RuntimeError("db connection refused")

    app = FastAPI()
    security_module.harden_app(app, "ready-test")
    security_module.wire_readiness_endpoint(app, _boom)
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
    assert "db connection refused" in resp.json()["checks"]["_error"]


def test_wire_readiness_endpoint_returns_503_when_no_checks_at_all(security_module):
    """An empty checks dict must not be vacuously 'ready' (all([]) is True in Python, which
    would be the wrong default here)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    security_module.harden_app(app, "ready-test")
    security_module.wire_readiness_endpoint(app, lambda: {})
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
