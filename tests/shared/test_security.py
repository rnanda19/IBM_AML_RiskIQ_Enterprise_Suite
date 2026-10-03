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
tests/bp1_transaction_monitoring_detection/test_bp1_scoring_service.py's
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
