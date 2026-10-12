"""Tests for src/aml_riskiq/casework/ -- the unified alert schema, case-lifecycle state
machine, cross-BP dedup, reconciliation, and evidence export. Scope: this package's own
logic against synthetic Alert fixtures built directly in this file -- it does not call any
real scoring service (that integration is each service's own test file's job, same split as
tests/unit/test_security.py's own docstring describes)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Same sys.path convention as tests/unit/test_security.py -- src/aml_riskiq is not an
# installed package in every environment this suite runs in (only `pip install -e .` in CI
# puts it on sys.path as "aml_riskiq"; locally it is not), so every test file inserts
# src/aml_riskiq itself and imports its submodules as top-level packages.
_src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from casework.alert_schema import Alert, CaseStatus, alert_from_score_response  # noqa: E402
from casework.case_lifecycle import InvalidTransitionError, transition  # noqa: E402
from casework.dedup import cluster_alerts, exact_duplicates  # noqa: E402
from casework.evidence_export import export_evidence  # noqa: E402
from casework.reconciliation import build_reconciliation_report  # noqa: E402

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


def _alert(**overrides) -> Alert:
    defaults = dict(
        entity_ref="acct-001",
        business_problem="BP1",
        detection_source="xgboost_champion",
        risk_score=0.87,
        selected_threshold=0.5,
        model_name="xgboost_v1",
        scoring_timestamp=NOW,
    )
    defaults.update(overrides)
    return Alert(**defaults)


# -- alert_schema --------------------------------------------------------------------------


def test_alert_defaults():
    a = _alert()
    assert a.status == CaseStatus.NEW
    assert a.history == []
    assert a.alert_id  # auto-generated, non-empty


def test_alert_from_score_response_maps_real_fields():
    score_response = {
        "probability": 0.91,
        "is_flagged": True,
        "threshold": 0.42,
        "champion_name": "xgboost_v3",
        "dataset_variant": "LI-Medium",
    }
    a = alert_from_score_response(
        entity_ref="acct-777",
        business_problem="BP1",
        detection_source="xgboost_champion",
        score_response=score_response,
        model_sha256="abc123",
    )
    assert a.risk_score == 0.91
    assert a.selected_threshold == 0.42
    assert a.model_name == "xgboost_v3"
    assert a.dataset_variant == "LI-Medium"
    assert a.model_sha256 == "abc123"


def test_alert_from_score_response_missing_field_raises():
    with pytest.raises(KeyError):
        alert_from_score_response(
            entity_ref="acct-1",
            business_problem="BP1",
            detection_source="xgboost_champion",
            score_response={"probability": 0.5},  # missing threshold/champion_name
        )


def test_alert_from_score_response_bp3_rule_score_field():
    score_response = {"rule_score": 3.2, "threshold": 1.0, "champion_name": "2hop_proximity_rule"}
    a = alert_from_score_response(
        entity_ref="acct-9",
        business_problem="BP3",
        detection_source="2hop_proximity_rule",
        score_response=score_response,
    )
    assert a.risk_score == 3.2


# -- case_lifecycle -------------------------------------------------------------------------


def test_transition_new_to_assigned():
    a = _alert()
    a2 = transition(a, CaseStatus.ASSIGNED, actor="investigator-1", now=NOW)
    assert a2.status == CaseStatus.ASSIGNED
    assert len(a2.history) == 1
    assert a2.history[0].from_status == CaseStatus.NEW
    assert a2.history[0].to_status == CaseStatus.ASSIGNED
    # original alert unchanged (immutable-by-convention)
    assert a.status == CaseStatus.NEW
    assert a.history == []


def test_transition_full_lifecycle_path():
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    a = transition(a, CaseStatus.UNDER_REVIEW, actor="x", now=NOW)
    a = transition(a, CaseStatus.ESCALATED, actor="x", now=NOW)
    a = transition(a, CaseStatus.CLOSED, actor="x", now=NOW)
    assert a.status == CaseStatus.CLOSED
    assert len(a.history) == 4


def test_transition_invalid_raises():
    a = _alert()  # status=NEW; ESCALATED is not in ALLOWED_TRANSITIONS[NEW]
    with pytest.raises(InvalidTransitionError):
        transition(a, CaseStatus.ESCALATED, actor="x")


def test_transition_closed_is_terminal():
    a = _alert(status=CaseStatus.CLOSED)
    with pytest.raises(InvalidTransitionError):
        transition(a, CaseStatus.ASSIGNED, actor="x")


def test_transition_unresolved_can_be_reassigned():
    a = _alert(status=CaseStatus.UNRESOLVED)
    a2 = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    assert a2.status == CaseStatus.ASSIGNED


# -- dedup ------------------------------------------------------------------------------------


def test_cluster_alerts_groups_same_entity_within_window():
    a1 = _alert(entity_ref="acct-1", scoring_timestamp=NOW)
    a2 = _alert(entity_ref="acct-1", scoring_timestamp=NOW + timedelta(hours=2), business_problem="BP4")
    clusters = cluster_alerts([a1, a2], window_hours=24)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_cluster_alerts_splits_outside_window():
    a1 = _alert(entity_ref="acct-1", scoring_timestamp=NOW)
    a2 = _alert(entity_ref="acct-1", scoring_timestamp=NOW + timedelta(hours=48))
    clusters = cluster_alerts([a1, a2], window_hours=24)
    assert len(clusters) == 2


def test_cluster_alerts_different_entities_never_merge():
    a1 = _alert(entity_ref="acct-1", scoring_timestamp=NOW)
    a2 = _alert(entity_ref="acct-2", scoring_timestamp=NOW)
    clusters = cluster_alerts([a1, a2], window_hours=24)
    assert len(clusters) == 2


def test_exact_duplicates_detects_identical_key():
    a1 = _alert(entity_ref="acct-1", transaction_ref="txn-1")
    a2 = _alert(entity_ref="acct-1", transaction_ref="txn-1")  # same key, different alert_id
    dupes = exact_duplicates([a1, a2])
    assert len(dupes) == 1
    assert dupes[0].alert_id == a2.alert_id


def test_exact_duplicates_distinct_bp_not_a_duplicate():
    a1 = _alert(entity_ref="acct-1", transaction_ref="txn-1", business_problem="BP1")
    a2 = _alert(entity_ref="acct-1", transaction_ref="txn-1", business_problem="BP4")
    assert exact_duplicates([a1, a2]) == []


# -- reconciliation ----------------------------------------------------------------------------


def test_reconciliation_counts_reconcile():
    a1 = _alert(entity_ref="acct-1", transaction_ref="txn-1")
    a2 = _alert(entity_ref="acct-1", transaction_ref="txn-1")  # exact duplicate of a1
    a3 = transition(_alert(entity_ref="acct-2"), CaseStatus.ASSIGNED, actor="x", now=NOW)
    report = build_reconciliation_report([a1, a2, a3], n_transactions_evaluated=1000, n_rejected=3)
    assert report["n_transactions_evaluated"] == 1000
    assert report["n_rejected"] == 3
    assert report["n_alerts_generated"] == 3
    assert report["n_exact_duplicates_removed"] == 1
    assert report["n_alerts_after_dedup"] == 2
    assert report["status_counts"]["new"] == 2
    assert report["status_counts"]["assigned"] == 1
    assert sum(report["status_counts"].values()) == 3


def test_reconciliation_empty_alerts():
    report = build_reconciliation_report([], n_transactions_evaluated=500)
    assert report["n_alerts_generated"] == 0
    assert report["n_alerts_after_dedup"] == 0
    assert sum(report["status_counts"].values()) == 0


# -- evidence_export ----------------------------------------------------------------------------


def test_export_evidence_structure():
    a = _alert(
        entity_ref="acct-5", transaction_ref="txn-5", reason_codes=["high_velocity", "new_counterparty"]
    )
    a = transition(a, CaseStatus.ASSIGNED, actor="investigator-1", note="initial triage", now=NOW)
    bundle = export_evidence(a)
    assert bundle["alert_id"] == a.alert_id
    assert bundle["subject"]["entity_ref"] == "acct-5"
    assert bundle["detection"]["flagged"] is True
    assert bundle["detection"]["reason_codes"] == ["high_velocity", "new_counterparty"]
    assert bundle["case"]["current_status"] == "assigned"
    assert len(bundle["case"]["history"]) == 1
    assert bundle["case"]["history"][0]["actor"] == "investigator-1"


def test_export_evidence_is_json_serializable():
    import json

    a = _alert()
    json.dumps(export_evidence(a))  # raises if not serializable


# -- case_lifecycle: hash chain / assign / add_note / add_evidence (RBAC phase, 2026-10-12) --

from casework.case_lifecycle import add_evidence, add_note, assign, verify_history_integrity  # noqa: E402


def test_transition_computes_hash_chain():
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    a = transition(a, CaseStatus.UNDER_REVIEW, actor="y", now=NOW + timedelta(hours=1))
    assert a.history[0].prev_event_hash is None
    assert a.history[0].event_hash
    assert a.history[1].prev_event_hash == a.history[0].event_hash
    assert a.history[1].event_hash != a.history[0].event_hash


def test_verify_history_integrity_passes_on_untouched_chain():
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    a = transition(a, CaseStatus.UNDER_REVIEW, actor="y", now=NOW + timedelta(hours=1))
    a = transition(a, CaseStatus.CLOSED, actor="z", now=NOW + timedelta(hours=2))
    ok, reason = verify_history_integrity(a)
    assert ok is True
    assert reason is None


def test_verify_history_integrity_empty_history_passes():
    ok, reason = verify_history_integrity(_alert())
    assert ok is True
    assert reason is None


def test_verify_history_integrity_detects_tampered_note():
    """Simulates an out-of-band edit (e.g. a hand-edited database row) by mutating one
    history event's note directly -- the hash chain must catch this."""
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", note="original note", now=NOW)
    tampered_event = a.history[0].model_copy(update={"note": "TAMPERED"})
    tampered_alert = a.model_copy(update={"history": [tampered_event]})
    ok, reason = verify_history_integrity(tampered_alert)
    assert ok is False
    assert "event_hash" in reason


def test_verify_history_integrity_detects_reordered_events():
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    a = transition(a, CaseStatus.UNDER_REVIEW, actor="y", now=NOW + timedelta(hours=1))
    reordered = a.model_copy(update={"history": [a.history[1], a.history[0]]})
    ok, reason = verify_history_integrity(reordered)
    assert ok is False
    assert "prev_event_hash" in reason


def test_verify_history_integrity_detects_deleted_middle_event():
    a = _alert()
    a = transition(a, CaseStatus.ASSIGNED, actor="x", now=NOW)
    a = transition(a, CaseStatus.UNDER_REVIEW, actor="y", now=NOW + timedelta(hours=1))
    a = transition(a, CaseStatus.CLOSED, actor="z", now=NOW + timedelta(hours=2))
    truncated = a.model_copy(update={"history": [a.history[0], a.history[2]]})
    ok, reason = verify_history_integrity(truncated)
    assert ok is False
    assert "prev_event_hash" in reason


def test_assign_new_alert_transitions_to_assigned():
    a = _alert()
    a2 = assign(a, assignee="inv-1", actor="supervisor", now=NOW)
    assert a2.status == CaseStatus.ASSIGNED
    assert a2.assigned_to == "inv-1"
    assert len(a2.history) == 1


def test_assign_already_assigned_alert_only_reassigns():
    a = _alert(status=CaseStatus.UNDER_REVIEW)
    a2 = assign(a, assignee="inv-2", actor="supervisor", now=NOW)
    assert a2.status == CaseStatus.UNDER_REVIEW  # unchanged
    assert a2.assigned_to == "inv-2"
    assert a2.history == []  # reassignment alone is not a status transition


def test_add_note_appends_without_changing_status():
    a = _alert()
    a2 = add_note(a, actor="inv-1", text="reviewed counterparty history", now=NOW)
    assert len(a2.notes) == 1
    assert a2.notes[0].text == "reviewed counterparty history"
    assert a2.notes[0].actor == "inv-1"
    assert a2.status == CaseStatus.NEW
    assert a.notes == []  # original unchanged


def test_add_evidence_appends_without_changing_status():
    a = _alert()
    a2 = add_evidence(
        a, actor="inv-1", description="SAR filing from 2024", external_ref="sar://12345", now=NOW
    )
    assert len(a2.evidence) == 1
    assert a2.evidence[0].description == "SAR filing from 2024"
    assert a2.evidence[0].external_ref == "sar://12345"
    assert a2.status == CaseStatus.NEW


def test_evidence_export_includes_notes_and_evidence_and_assignment():
    a = _alert()
    a = assign(a, assignee="inv-1", actor="supervisor", now=NOW)
    a = add_note(a, actor="inv-1", text="triage complete", now=NOW)
    a = add_evidence(a, actor="inv-1", description="wire confirmation", now=NOW)
    bundle = export_evidence(a)
    assert bundle["case"]["assigned_to"] == "inv-1"
    assert bundle["case"]["notes"][0]["text"] == "triage complete"
    assert bundle["case"]["evidence"][0]["description"] == "wire confirmation"
