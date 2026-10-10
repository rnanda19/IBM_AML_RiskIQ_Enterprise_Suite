"""Generates docs/architecture/CASEWORK_WORKED_EXAMPLE.md's command transcript for real --
every block below is the real, captured stdout of running this script, not hand-typed."""

import json
import sys

sys.path.insert(0, "src/aml_riskiq")

from casework.alert_schema import CaseStatus, alert_from_score_response  # noqa: E402
from casework.case_lifecycle import transition  # noqa: E402
from casework.evidence_export import export_evidence  # noqa: E402
from casework.reconciliation import build_reconciliation_report  # noqa: E402

print("=" * 70)
print("STEP 1 -- a /score response, in the exact shape bp1_scoring_service.py's")
print("score_transaction() really returns (SYNTHETIC values for this walkthrough --")
print("not a real trained-model output, not real transaction data)")
print("=" * 70)
score_response = {
    "probability": 0.93,
    "is_flagged": True,
    "threshold": 0.5,
    "champion_name": "XGBoostClassifier",
    "dataset_variant": "LI-Medium",
}
print(json.dumps(score_response, indent=2))

print()
print("=" * 70)
print("STEP 2 -- alert_from_score_response() builds a unified Alert from it")
print("=" * 70)
alert = alert_from_score_response(
    entity_ref="ACCT-SYNTHETIC-00042",
    business_problem="BP1",
    detection_source="xgboost_champion",
    score_response=score_response,
    transaction_ref="TXN-SYNTHETIC-00042-01",
    model_sha256="ab12cd34ef56...(truncated, illustrative)",
    reason_codes=["risk_score_above_threshold", "high_amount_velocity_24h"],
)
print(alert.model_dump_json(indent=2))

print()
print("=" * 70)
print("STEP 3 -- an investigator works the case: NEW -> ASSIGNED -> UNDER_REVIEW")
print("-> ESCALATED -> CLOSED, via case_lifecycle.transition()")
print("=" * 70)
alert = transition(alert, CaseStatus.ASSIGNED, actor="investigator_jsmith", note="Picked up from queue.")
print(f"-> {alert.status.value} (history: {len(alert.history)} event)")
alert = transition(
    alert,
    CaseStatus.UNDER_REVIEW,
    actor="investigator_jsmith",
    note="Pulling 90-day transaction history for entity.",
)
print(f"-> {alert.status.value} (history: {len(alert.history)} events)")
alert = transition(
    alert,
    CaseStatus.ESCALATED,
    actor="investigator_jsmith",
    note="Pattern consistent with structuring; escalating to senior analyst.",
)
print(f"-> {alert.status.value} (history: {len(alert.history)} events)")
alert = transition(
    alert,
    CaseStatus.CLOSED,
    actor="senior_analyst_rpatel",
    note="Reviewed escalation; confirmed SAR-worthy, filed externally. Case closed.",
)
print(f"-> {alert.status.value} (history: {len(alert.history)} events)")

print()
print("=" * 70)
print("STEP 4 -- an attempted invalid transition fails loudly (CLOSED is terminal)")
print("=" * 70)
try:
    transition(alert, CaseStatus.ASSIGNED, actor="investigator_jsmith")
except Exception as e:
    print(f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("STEP 5 -- export_evidence() produces the audit-reconstruction bundle")
print("=" * 70)
evidence = export_evidence(alert)
print(json.dumps(evidence, indent=2, default=str))

print()
print("=" * 70)
print("STEP 6 -- build_reconciliation_report() over this (single-alert) batch")
print("=" * 70)
report = build_reconciliation_report([alert], n_transactions_evaluated=50000, n_rejected=0)
print(json.dumps(report, indent=2, default=str))
