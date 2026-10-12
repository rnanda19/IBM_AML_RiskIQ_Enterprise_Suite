"""
Case Management Service -- real, standalone FastAPI service wiring the `casework` package
(alert schema, case-lifecycle state machine, dedup, reconciliation, evidence export, and the
new SQLite-backed `store.py`) into live, RBAC-protected routes.

This closes DEF-003 ("No RBAC at the API layer") from `docs/audit/DEFECT_REGISTER.md`, whose
own "Recommended fix (remaining)" said exactly this: "wire a case-management API (built on the
casework package) in as actual routes, and protect them with require_role()." It also finishes
what `docs/architecture/INVESTIGATOR_WORKFLOW.md` disclosed as not-yet-done when `casework/`
was first built (no live wiring, no persistent store, no RBAC applied).

Deliberately NOT changed to make this possible: none of the 5 scoring services' `/score`
request/response schemas. `docs/architecture/INVESTIGATOR_WORKFLOW.md` already disclosed that
adding an identifier field to all 5 would be a breaking API change across every one of them --
out of scope for this phase. This service instead accepts the same caller-supplied fields
`alert_from_score_response()` already required (the caller already has a `/score` response in
hand and already knows which entity/transaction it scored -- that has not changed).

RBAC permission matrix (see docs/security/RBAC.md for the full table and rationale):
  analyst            -- create + read alerts only (raises detections, cannot work them)
  investigator        -- + assign, notes, evidence, transition to UNDER_REVIEW/UNRESOLVED
  compliance_officer   -- + transition to ESCALATED/CLOSED (sign-off authority),
                          reconciliation reports, audit-integrity verification
  admin (="administrator" in the business language) -- satisfies every role check
                          (require_any_role()'s existing admin bypass, unchanged)

Secured per the same standards as BP1-BP5 (`src/aml_riskiq/serving/_security.py`, reused
unchanged, not reimplemented): rate limiting (`case_rate_limit()`, its own separate budget/
env-var from `/score`'s), structured audit logging (every request, `AuditLogMiddleware`),
`/metrics` (Prometheus), and the identical open-mode-by-default / `AML_RISKIQ_REQUIRE_AUTH`
fail-closed-production-gate behavior. Every mutating route runs through Pydantic request
models, so a malformed body is a real 422, not a crash or a silent no-op.

Identity model, honestly stated: there is no user directory in this platform -- "who did
this" in every audit record (CaseEvent.actor, CaseNote.actor, EvidenceReference.actor) is the
authenticated caller's API-key fingerprint (the same non-reversible 8-hex-char SHA-256 prefix
`_security.py` already uses for its own audit log), never a human name. A real deployment
mapping keys to named users is future work, not fabricated here.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    from casework.alert_schema import Alert, CaseStatus
    from casework.evidence_export import export_evidence
    from casework.store import AlertNotFoundError, AlertStore, InvalidTransitionError
    from serving._security import (
        ADMIN_ROLE,
        ANALYST_ROLE,
        COMPLIANCE_OFFICER_ROLE,
        INVESTIGATOR_ROLE,
        case_rate_limit,
        harden_app,
        record_custom_metric,
        require_any_role,
        resolve_caller_role,
        set_custom_gauge,
        wire_metrics_endpoint,
    )
except ImportError:  # pragma: no cover -- exercised under Docker's import context, not pytest's
    from src.aml_riskiq.casework.alert_schema import Alert, CaseStatus
    from src.aml_riskiq.casework.evidence_export import export_evidence
    from src.aml_riskiq.casework.store import AlertNotFoundError, AlertStore, InvalidTransitionError
    from src.aml_riskiq.serving._security import (
        ADMIN_ROLE,
        ANALYST_ROLE,
        COMPLIANCE_OFFICER_ROLE,
        INVESTIGATOR_ROLE,
        case_rate_limit,
        harden_app,
        record_custom_metric,
        require_any_role,
        resolve_caller_role,
        set_custom_gauge,
        wire_metrics_endpoint,
    )


# ----------------------------------------------------------------------------------------
# Real project-root resolution -- identical pattern to every BP1-BP5 scoring service (copied
# verbatim, not re-derived, per this platform's standing Lesson #3 rule), so this service
# resolves correctly whether run locally, from Docker, or from any other real working dir.
# ----------------------------------------------------------------------------------------
def _locate_project_root() -> Path:
    cur = Path.cwd()
    for _ in range(8):
        if (cur / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    known = Path.home() / "Documents" / "IBM_AML_RiskIQ_Enterprise_Suite"
    if (known / "PROJECT_STRUCTURE_LOCKED.md").exists():
        return known
    if Path("/app/src").is_dir():
        return Path("/app")
    raise FileNotFoundError(
        "Could not locate the project root (checked an upward walk from "
        f"{Path.cwd()}, {known}, and the Docker /app fallback). Set AML_RISKIQ_CASE_DB_PATH "
        "directly to skip root resolution, or run this service from inside the real project tree."
    )


PROJECT_ROOT = _locate_project_root()
_default_db_path = PROJECT_ROOT / "data" / "case_management" / "casework.db"
DB_PATH = Path(os.environ.get("AML_RISKIQ_CASE_DB_PATH", str(_default_db_path)))

store = AlertStore(DB_PATH)


# ----------------------------------------------------------------------------------------
# Request models -- real Pydantic validation on every mutating route (FastAPI returns 422 on
# a malformed body automatically; this is what makes "validate inputs" a real, testable
# control rather than an assertion in a docstring).
# ----------------------------------------------------------------------------------------
class AlertCreateRequest(BaseModel):
    entity_ref: str
    transaction_ref: str | None = None
    business_problem: str
    detection_source: str
    risk_score: float
    selected_threshold: float
    model_name: str
    model_sha256: str | None = None
    dataset_variant: str | None = None
    event_timestamp: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list)


class AssignRequest(BaseModel):
    assignee: str
    note: str | None = None


class NoteCreateRequest(BaseModel):
    text: str


class EvidenceCreateRequest(BaseModel):
    description: str
    external_ref: str | None = None


class TransitionRequest(BaseModel):
    to_status: CaseStatus
    note: str | None = None


# Target statuses that require compliance-officer (or admin) sign-off -- checked dynamically
# inside transition_endpoint() below, since the required role depends on the request body, not
# just the route -- a single static Depends(require_role(...)) cannot express this.
_COMPLIANCE_ONLY_TARGETS = {CaseStatus.ESCALATED, CaseStatus.CLOSED}


app = FastAPI(title="AML RiskIQ Case Management Service")
_limiter = harden_app(app, "case_management_service")
wire_metrics_endpoint(app)


def _not_found(alert_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Alert {alert_id} not found.")


def _refresh_unresolved_gauge() -> None:
    """Observability (requirement 7): refreshes the real, store-computed count of every
    alert not yet CLOSED (store.count_unresolved() -- a single SELECT COUNT(*), not an
    estimate) as a Prometheus gauge on this service's own /metrics. Called after every route
    that can change which alerts are unresolved (ingest, manual create, transition) and on
    every /health probe, so the gauge never goes stale for longer than the time between two
    real requests."""
    set_custom_gauge("case_management_service", "unresolved_alerts_total", store.count_unresolved())


@app.get("/health")
def health() -> dict:
    total = len(store.list_alerts(limit=1))  # cheap liveness probe of the real DB connection
    _refresh_unresolved_gauge()
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "db_reachable": True if total >= 0 else False,
        "unresolved_alerts": store.count_unresolved(),
    }


@app.post("/alerts", status_code=201)
@_limiter.limit(case_rate_limit())
def create_alert_endpoint(
    request: Request,
    body: AlertCreateRequest,
    _caller: str = Depends(require_any_role(ANALYST_ROLE, INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    alert = Alert(**body.model_dump())
    store.create_alert(alert)
    _refresh_unresolved_gauge()
    return alert.model_dump(mode="json")


@app.post("/alerts/ingest")
@_limiter.limit(case_rate_limit())
def ingest_alert_endpoint(
    request: Request,
    response: Response,
    body: Alert,
    _caller: str = Depends(require_any_role(ANALYST_ROLE, INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    """Reliable alert delivery (requirements 1 and 3): the one route
    serving/_alert_dispatch.py's dispatch_alert() POSTs every automated-scoring alert to.
    Unlike POST /alerts (which builds a fresh Alert from caller-supplied fields and always
    inserts it), this route accepts a COMPLETE, already-built Alert -- alert_id,
    idempotency_key, severity, and generation_source all already set by
    casework/scoring_event.py's build_alert_from_scoring_event(), on the calling BP service's
    side, not regenerated here -- and inserts it IDEMPOTENTLY via
    store.create_alert_idempotent(), which is enforced by a real SQLite UNIQUE index on
    idempotency_key (store.py), not application-level checking. A retry or a replay of the
    exact same scoring event (same idempotency_key) returns the ORIGINAL alert_id with
    duplicate=True rather than creating a second case -- this is what makes "retries do not
    create duplicate alerts" a database-enforced guarantee. RBAC is unchanged from POST
    /alerts: the same three roles (never a separate "service" role) -- each BP's own
    configured case-service API key must be one of analyst/investigator/compliance_officer
    (or admin), per docs/security/RBAC.md.

    Authenticated-but-malformed-body handling (requirement 2): a body that fails Alert's own
    Pydantic validation never reaches this function body -- FastAPI returns a real 422
    automatically, which dispatch_alert() already treats as a non-retryable rejection (see
    that module's _NON_RETRYABLE_STATUS_CODES), not a transient failure to retry forever."""
    created_alert, was_created = store.create_alert_idempotent(body)
    record_custom_metric(
        "case_management_service",
        "alert_ingest_created_total" if was_created else "alert_ingest_duplicate_total",
    )
    _refresh_unresolved_gauge()
    response.status_code = 201 if was_created else 200
    return {
        "alert_id": created_alert.alert_id,
        "duplicate": not was_created,
        "status": created_alert.status.value,
    }


@app.get("/alerts")
@_limiter.limit(case_rate_limit())
def list_alerts_endpoint(
    request: Request,
    status: CaseStatus | None = None,
    business_problem: str | None = None,
    assigned_to: str | None = None,
    entity_ref: str | None = None,
    limit: int = 200,
    _caller: str = Depends(require_any_role(ANALYST_ROLE, INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> list[dict]:
    alerts = store.list_alerts(
        status=status,
        business_problem=business_problem,
        assigned_to=assigned_to,
        entity_ref=entity_ref,
        limit=limit,
    )
    return [a.model_dump(mode="json") for a in alerts]


@app.get("/alerts/{alert_id}")
@_limiter.limit(case_rate_limit())
def get_alert_endpoint(
    request: Request,
    alert_id: str,
    _caller: str = Depends(require_any_role(ANALYST_ROLE, INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        return store.get_alert(alert_id).model_dump(mode="json")
    except AlertNotFoundError:
        raise _not_found(alert_id)


@app.post("/alerts/{alert_id}/assign")
@_limiter.limit(case_rate_limit())
def assign_endpoint(
    request: Request,
    alert_id: str,
    body: AssignRequest,
    _caller: str = Depends(require_any_role(INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        updated = store.assign(alert_id, assignee=body.assignee, actor=_caller, note=body.note)
    except AlertNotFoundError:
        raise _not_found(alert_id)
    return updated.model_dump(mode="json")


@app.post("/alerts/{alert_id}/notes", status_code=201)
@_limiter.limit(case_rate_limit())
def add_note_endpoint(
    request: Request,
    alert_id: str,
    body: NoteCreateRequest,
    _caller: str = Depends(require_any_role(INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        updated = store.add_note(alert_id, actor=_caller, text=body.text)
    except AlertNotFoundError:
        raise _not_found(alert_id)
    return updated.model_dump(mode="json")


@app.post("/alerts/{alert_id}/evidence", status_code=201)
@_limiter.limit(case_rate_limit())
def add_evidence_endpoint(
    request: Request,
    alert_id: str,
    body: EvidenceCreateRequest,
    _caller: str = Depends(require_any_role(INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        updated = store.add_evidence(
            alert_id, actor=_caller, description=body.description, external_ref=body.external_ref
        )
    except AlertNotFoundError:
        raise _not_found(alert_id)
    return updated.model_dump(mode="json")


@app.get("/alerts/{alert_id}/evidence_export")
@_limiter.limit(case_rate_limit())
def evidence_export_endpoint(
    request: Request,
    alert_id: str,
    _caller: str = Depends(require_any_role(INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        alert = store.get_alert(alert_id)
    except AlertNotFoundError:
        raise _not_found(alert_id)
    return export_evidence(alert)


@app.post("/alerts/{alert_id}/transition")
@_limiter.limit(case_rate_limit())
def transition_endpoint(
    request: Request,
    alert_id: str,
    body: TransitionRequest,
    x_api_key: str | None = Header(default=None),
    _caller: str = Depends(require_any_role(INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    # The coarse Depends() above already proved the caller is at least an investigator. For
    # the two sign-off target statuses, additionally require compliance_officer (or admin) --
    # this is the one route whose required role depends on the request BODY, not just the
    # route, so it cannot be expressed as a single static Depends(require_role(...)). Skipped
    # entirely in open mode (role == "anonymous"), matching every other route's open-mode
    # no-op behavior.
    if body.to_status in _COMPLIANCE_ONLY_TARGETS:
        role, _ = resolve_caller_role(x_api_key)
        if role != "anonymous" and role != COMPLIANCE_OFFICER_ROLE and role != ADMIN_ROLE:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Transitioning to '{body.to_status.value}' requires role "
                    f"'{COMPLIANCE_OFFICER_ROLE}' (caller has '{role}')."
                ),
            )
    try:
        updated = store.apply_transition(alert_id, body.to_status, actor=_caller, note=body.note)
    except AlertNotFoundError:
        raise _not_found(alert_id)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _refresh_unresolved_gauge()
    return updated.model_dump(mode="json")


@app.get("/alerts/{alert_id}/integrity")
@_limiter.limit(case_rate_limit())
def integrity_endpoint(
    request: Request,
    alert_id: str,
    _caller: str = Depends(require_any_role(COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    try:
        return store.verify_integrity(alert_id)
    except AlertNotFoundError:
        raise _not_found(alert_id)


@app.get("/reconciliation")
@_limiter.limit(case_rate_limit())
def reconciliation_endpoint(
    request: Request,
    n_transactions_evaluated: int,
    n_rejected: int = 0,
    business_problem: str | None = None,
    _caller: str = Depends(require_any_role(COMPLIANCE_OFFICER_ROLE)),
) -> dict:
    return store.reconciliation_report(
        n_transactions_evaluated=n_transactions_evaluated,
        n_rejected=n_rejected,
        business_problem=business_problem,
    )
