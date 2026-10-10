# Worked Example: One Alert, Scoring Through Audit Reconstruction

This is a real, captured run of `docs/architecture/examples/casework_worked_example.py` --
every line in the transcript below is actual stdout from actually running the real
`casework` package code (`alert_from_score_response`, `transition`, `export_evidence`,
`build_reconciliation_report`), not hand-written or edited after the fact. Reproduce it
yourself with:

```bash
cd IBM_AML_RiskIQ_Enterprise_Suite
python3 docs/architecture/examples/casework_worked_example.py
```

## What this is, and is not

This demonstrates the **plumbing** this review's P2 item asked for -- "one alert from
scoring through investigation, disposition and audit reconstruction" -- using the real,
tested `casework` package introduced earlier this session
(see [`INVESTIGATOR_WORKFLOW.md`](INVESTIGATOR_WORKFLOW.md)).

It is **not** a real detection. Step 1's `/score` response is a synthetic, hand-picked
dict in the exact shape `bp1_scoring_service.py`'s real `score_transaction()` returns --
it was not produced by calling a running service or a real trained model, and
`ACCT-SYNTHETIC-00042`/`TXN-SYNTHETIC-00042-01` are not real account or transaction
identifiers. This is the same honesty boundary this project has held throughout: real code,
exercised for real, on clearly-labeled synthetic input -- the same pattern the integration
test suite already uses (see e.g. `tests/integration/.../test_bp1_scoring_service.py`'s
`_StubChampion`).

It is also a live demonstration of the real, disclosed architecture gap this package
surfaced: `entity_ref` and `transaction_ref` are supplied by the *caller* in Step 2, because
no current `/score` request or response carries either one (see the `casework` package's
own docstring and `REQUIREMENT_TRACEABILITY_MATRIX.csv`'s `MISSING` row for it). In a real
deployment, whatever calls `/score` would need to already be tracking that identifier itself
and pass it to `alert_from_score_response()` -- this package cannot invent one.

## Captured transcript

```
======================================================================
STEP 1 -- a /score response, in the exact shape bp1_scoring_service.py's
score_transaction() really returns (SYNTHETIC values for this walkthrough --
not a real trained-model output, not real transaction data)
======================================================================
{
  "probability": 0.93,
  "is_flagged": true,
  "threshold": 0.5,
  "champion_name": "XGBoostClassifier",
  "dataset_variant": "LI-Medium"
}

======================================================================
STEP 2 -- alert_from_score_response() builds a unified Alert from it
======================================================================
{
  "schema_version": "1.0.0",
  "alert_id": "3a394786-aeb4-4d47-890d-cc1e7788d39f",
  "entity_ref": "ACCT-SYNTHETIC-00042",
  "transaction_ref": "TXN-SYNTHETIC-00042-01",
  "business_problem": "BP1",
  "detection_source": "xgboost_champion",
  "risk_score": 0.93,
  "selected_threshold": 0.5,
  "model_name": "XGBoostClassifier",
  "model_sha256": "ab12cd34ef56...(truncated, illustrative)",
  "dataset_variant": "LI-Medium",
  "event_timestamp": null,
  "scoring_timestamp": "2026-10-10T11:29:04.043664Z",
  "reason_codes": [
    "risk_score_above_threshold",
    "high_amount_velocity_24h"
  ],
  "status": "new",
  "history": []
}

======================================================================
STEP 3 -- an investigator works the case: NEW -> ASSIGNED -> UNDER_REVIEW
-> ESCALATED -> CLOSED, via case_lifecycle.transition()
======================================================================
-> assigned (history: 1 event)
-> under_review (history: 2 events)
-> escalated (history: 3 events)
-> closed (history: 4 events)

======================================================================
STEP 4 -- an attempted invalid transition fails loudly (CLOSED is terminal)
======================================================================
InvalidTransitionError: closed -> assigned is not an allowed transition (allowed from closed: none (terminal))

======================================================================
STEP 5 -- export_evidence() produces the audit-reconstruction bundle
======================================================================
{
  "schema_version": "1.0.0",
  "alert_id": "3a394786-aeb4-4d47-890d-cc1e7788d39f",
  "subject": {
    "entity_ref": "ACCT-SYNTHETIC-00042",
    "transaction_ref": "TXN-SYNTHETIC-00042-01"
  },
  "detection": {
    "business_problem": "BP1",
    "detection_source": "xgboost_champion",
    "risk_score": 0.93,
    "selected_threshold": 0.5,
    "flagged": true,
    "reason_codes": [
      "risk_score_above_threshold",
      "high_amount_velocity_24h"
    ]
  },
  "model_provenance": {
    "model_name": "XGBoostClassifier",
    "model_sha256": "ab12cd34ef56...(truncated, illustrative)",
    "dataset_variant": "LI-Medium"
  },
  "timestamps": {
    "event_timestamp": null,
    "scoring_timestamp": "2026-10-10T11:29:04.043664+00:00"
  },
  "case": {
    "current_status": "closed",
    "history": [
      {
        "timestamp": "2026-10-10T11:29:04.044029+00:00",
        "actor": "investigator_jsmith",
        "from_status": "new",
        "to_status": "assigned",
        "note": "Picked up from queue."
      },
      {
        "timestamp": "2026-10-10T11:29:04.044103+00:00",
        "actor": "investigator_jsmith",
        "from_status": "assigned",
        "to_status": "under_review",
        "note": "Pulling 90-day transaction history for entity."
      },
      {
        "timestamp": "2026-10-10T11:29:04.044123+00:00",
        "actor": "investigator_jsmith",
        "from_status": "under_review",
        "to_status": "escalated",
        "note": "Pattern consistent with structuring; escalating to senior analyst."
      },
      {
        "timestamp": "2026-10-10T11:29:04.044173+00:00",
        "actor": "senior_analyst_rpatel",
        "from_status": "escalated",
        "to_status": "closed",
        "note": "Reviewed escalation; confirmed SAR-worthy, filed externally. Case closed."
      }
    ]
  }
}

======================================================================
STEP 6 -- build_reconciliation_report() over this (single-alert) batch
======================================================================
{
  "n_transactions_evaluated": 50000,
  "n_rejected": 0,
  "n_alerts_generated": 1,
  "n_exact_duplicates_removed": 0,
  "n_alerts_after_dedup": 1,
  "n_entity_clusters": 1,
  "status_counts": {
    "new": 0,
    "assigned": 0,
    "under_review": 0,
    "escalated": 0,
    "closed": 1,
    "unresolved": 0
  },
  "n_cases_reviewed": 1,
  "n_cases_unresolved": 0,
  "n_cases_not_yet_actioned": 0
}
```

## What each step shows

- **Step 1-2**: a real `/score`-shaped response becomes a real, schema-versioned `Alert` via
  `alert_from_score_response()` -- every detection-related field (`risk_score`,
  `selected_threshold`, `model_name`, `dataset_variant`) is copied straight from the response
  dict, not re-derived or guessed.
- **Step 3**: `case_lifecycle.transition()` walks the alert through a realistic investigator
  workflow. Each call returns a **new** `Alert` (immutable-by-convention) with one more
  `CaseEvent` appended -- nothing is overwritten in place.
- **Step 4**: the conservative transition graph in `ALLOWED_TRANSITIONS` refuses an invalid
  move (closed is terminal) with a real `InvalidTransitionError`, not a silently-ignored
  no-op.
- **Step 5**: `export_evidence()` reconstructs the full case -- detection, model provenance,
  timestamps, and the complete event history with actor + note on every transition -- in one
  JSON-serializable bundle, satisfying this review's "independent reviewer can reconstruct
  why and how" framing.
- **Step 6**: `build_reconciliation_report()` rolls a batch of alerts (here, just the one) up
  into self-checking summary counts -- `status_counts` is asserted to sum to the alert count
  inside the function itself, so a bug here fails loudly rather than silently under-counting.

## Still not done

This script calls the `casework` functions directly, in a standalone process. It does **not**
demonstrate any of the following, because none of them exist yet (see `DEFECT_REGISTER.md`
DEF-003 and the `REQUIREMENT_TRACEABILITY_MATRIX.csv` `MISSING` rows):

- A live HTTP API for case management -- `casework` is a library, not a service.
- Any of the 5 scoring services calling `alert_from_score_response()` themselves.
- Persistent storage -- every `Alert` here lives only in this process's memory for the
  duration of the script.
- `require_role()` protecting any of this -- there is no route yet for it to protect.
