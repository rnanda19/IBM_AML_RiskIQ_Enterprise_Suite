"""Evidence export -- a single JSON-serializable bundle for one alert, recording input
provenance, scoring model, model version, reason codes, and full case history, so an
independent reviewer can reconstruct why an alert was created and how it was handled
afterward (the external review's Prompt 5 acceptance criterion). See the casework package
docstring for scope."""

from __future__ import annotations

from .alert_schema import Alert


def export_evidence(alert: Alert) -> dict:
    """Returns a plain-dict evidence bundle for `alert`. Every field traces directly to the
    Alert object passed in -- this function adds no new data, it only reshapes what is
    already real into the export document's layout."""
    return {
        "schema_version": alert.schema_version,
        "alert_id": alert.alert_id,
        "subject": {
            "entity_ref": alert.entity_ref,
            "transaction_ref": alert.transaction_ref,
        },
        "detection": {
            "business_problem": alert.business_problem,
            "detection_source": alert.detection_source,
            "risk_score": alert.risk_score,
            "selected_threshold": alert.selected_threshold,
            "flagged": alert.risk_score >= alert.selected_threshold,
            "reason_codes": list(alert.reason_codes),
        },
        "model_provenance": {
            "model_name": alert.model_name,
            "model_sha256": alert.model_sha256,
            "dataset_variant": alert.dataset_variant,
        },
        "timestamps": {
            "event_timestamp": alert.event_timestamp.isoformat() if alert.event_timestamp else None,
            "scoring_timestamp": alert.scoring_timestamp.isoformat(),
        },
        "case": {
            "current_status": alert.status.value,
            "history": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "actor": e.actor,
                    "from_status": e.from_status.value if e.from_status else None,
                    "to_status": e.to_status.value,
                    "note": e.note,
                }
                for e in alert.history
            ],
        },
    }
