"""Tests for src/aml_riskiq/casework/scoring_event.py -- the standardized scoring-event
contract added for the end-to-end AML workflow integration phase (2026-10-12). Covers
validation (missing identifiers, invalid scores, incompatible schema versions), the
alert-worthiness gate, risk-based severity routing, and idempotency-key determinism."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

_src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from casework.scoring_event import (  # noqa: E402
    SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS,
    ScoringEvent,
    ScoringEventValidationError,
    build_alert_from_scoring_event,
    classify_severity,
    compute_idempotency_key,
    is_alert_worthy,
    parse_scoring_event,
)

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def _fields(**overrides):
    defaults = dict(
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-001",
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
        scoring_timestamp=NOW,
    )
    defaults.update(overrides)
    return defaults


# -- validation: missing identifiers, invalid scores, schema versions -------------------------


def test_missing_entity_ref_is_rejected():
    with pytest.raises(ValidationError):
        ScoringEvent(**{k: v for k, v in _fields().items() if k != "entity_ref"})


def test_empty_entity_ref_is_rejected():
    with pytest.raises(ValidationError):
        ScoringEvent(**_fields(entity_ref=""))


def test_nan_risk_score_is_rejected():
    with pytest.raises(ValidationError):
        ScoringEvent(**_fields(risk_score=float("nan")))


def test_infinite_risk_score_is_rejected():
    with pytest.raises(ValidationError):
        ScoringEvent(**_fields(risk_score=float("inf")))


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        ScoringEvent(**_fields(schema_version="99.0.0"))


def test_supported_schema_version_accepted():
    event = ScoringEvent(**_fields(schema_version="1.0.0"))
    assert event.schema_version in SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS


def test_parse_scoring_event_wraps_validation_error():
    with pytest.raises(ScoringEventValidationError):
        parse_scoring_event(**{k: v for k, v in _fields().items() if k != "entity_ref"})


def test_parse_scoring_event_success():
    event = parse_scoring_event(**_fields())
    assert event.entity_ref == "acct-001"


def test_transaction_ref_optional():
    event = ScoringEvent(**_fields())
    assert event.transaction_ref is None
    event2 = ScoringEvent(**_fields(transaction_ref="txn-5"))
    assert event2.transaction_ref == "txn-5"


# -- is_alert_worthy / classify_severity (risk-based routing) ---------------------------------


def test_is_alert_worthy_true_at_exact_threshold():
    assert is_alert_worthy(0.5, 0.5) is True


def test_is_alert_worthy_false_below_threshold():
    assert is_alert_worthy(0.49, 0.5) is False


def test_classify_severity_none_when_not_alert_worthy():
    assert classify_severity(0.2, 0.5) is None


def test_classify_severity_medium_at_threshold():
    assert classify_severity(0.5, 0.5) == "medium"


def test_classify_severity_high_band():
    assert classify_severity(0.8, 0.5) == "high"  # ratio 1.6


def test_classify_severity_critical_band():
    assert classify_severity(1.0, 0.5) == "critical"  # ratio 2.0


def test_classify_severity_custom_bands():
    assert classify_severity(0.7, 0.5, high_ratio=1.2, critical_ratio=1.3) == "critical"


def test_classify_severity_zero_threshold_flagged_is_critical():
    assert classify_severity(0.1, 0.0) == "critical"


def test_classify_severity_zero_threshold_zero_score_is_medium():
    assert classify_severity(0.0, 0.0) == "medium"


# -- idempotency key ----------------------------------------------------------------------------


def test_idempotency_key_deterministic_for_identical_events():
    e1 = ScoringEvent(**_fields())
    e2 = ScoringEvent(**_fields())
    assert compute_idempotency_key(e1) == compute_idempotency_key(e2)


def test_idempotency_key_stable_across_different_scoring_timestamps():
    """A retry of the SAME real event legitimately has a different wall-clock
    scoring_timestamp -- the key must not change because of that."""
    e1 = ScoringEvent(**_fields(scoring_timestamp=NOW))
    e2 = ScoringEvent(**_fields(scoring_timestamp=datetime(2026, 10, 12, 12, 5, 0, tzinfo=timezone.utc)))
    assert compute_idempotency_key(e1) == compute_idempotency_key(e2)


def test_idempotency_key_differs_for_different_entities():
    e1 = ScoringEvent(**_fields(entity_ref="acct-001"))
    e2 = ScoringEvent(**_fields(entity_ref="acct-002"))
    assert compute_idempotency_key(e1) != compute_idempotency_key(e2)


def test_idempotency_key_differs_for_different_transaction_refs():
    e1 = ScoringEvent(**_fields(transaction_ref="txn-1"))
    e2 = ScoringEvent(**_fields(transaction_ref="txn-2"))
    assert compute_idempotency_key(e1) != compute_idempotency_key(e2)


def test_idempotency_key_differs_for_different_risk_scores():
    e1 = ScoringEvent(**_fields(risk_score=0.9))
    e2 = ScoringEvent(**_fields(risk_score=0.91))
    assert compute_idempotency_key(e1) != compute_idempotency_key(e2)


def test_idempotency_key_is_a_sha256_hex_digest():
    e1 = ScoringEvent(**_fields())
    key = compute_idempotency_key(e1)
    assert len(key) == 64
    int(key, 16)  # raises ValueError if not valid hex


# -- build_alert_from_scoring_event -------------------------------------------------------------


def test_build_alert_sets_automated_provenance():
    event = ScoringEvent(**_fields())
    key = compute_idempotency_key(event)
    alert = build_alert_from_scoring_event(event, idempotency_key=key, severity="high")
    assert alert.generation_source == "automated_scoring"
    assert alert.idempotency_key == key
    assert alert.severity == "high"
    assert alert.entity_ref == "acct-001"
    assert alert.risk_score == 0.9
    assert alert.status.value == "new"
    assert alert.history == []  # never pre-populated -- case_lifecycle owns all transitions


def test_build_alert_preserves_model_provenance():
    event = ScoringEvent(**_fields(model_sha256="deadbeef", dataset_variant="LI-Medium"))
    alert = build_alert_from_scoring_event(event, idempotency_key="k", severity=None)
    assert alert.model_sha256 == "deadbeef"
    assert alert.dataset_variant == "LI-Medium"
    assert alert.model_name == "XGBoost"
