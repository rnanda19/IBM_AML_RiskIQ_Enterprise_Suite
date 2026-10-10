"""Case-lifecycle state machine. The allowed-transition graph is deliberately conservative
(a case can only move forward, be closed, or go unresolved-and-reassigned) so an investigator
workflow built on this cannot silently skip review steps. See the casework package docstring
for scope."""

from __future__ import annotations

from datetime import datetime, timezone

from .alert_schema import Alert, CaseEvent, CaseStatus

ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.NEW: {CaseStatus.ASSIGNED, CaseStatus.CLOSED},
    CaseStatus.ASSIGNED: {CaseStatus.UNDER_REVIEW, CaseStatus.UNRESOLVED},
    CaseStatus.UNDER_REVIEW: {CaseStatus.ESCALATED, CaseStatus.CLOSED, CaseStatus.UNRESOLVED},
    CaseStatus.ESCALATED: {CaseStatus.CLOSED, CaseStatus.UNRESOLVED},
    CaseStatus.CLOSED: set(),  # terminal -- reopen via a new Alert, never by transition
    CaseStatus.UNRESOLVED: {CaseStatus.ASSIGNED},  # can be re-picked-up
}


class InvalidTransitionError(ValueError):
    """Raised when a requested status transition is not in ALLOWED_TRANSITIONS for the
    alert's current status."""


def transition(
    alert: Alert,
    to_status: CaseStatus,
    *,
    actor: str,
    note: str | None = None,
    now: datetime | None = None,
) -> Alert:
    """Returns a NEW Alert with status=to_status and one additional CaseEvent appended to
    history -- never mutates the given alert in place, so a caller holding a reference to the
    prior state still sees the prior state (immutable-by-convention, matching the Alert
    docstring). Raises InvalidTransitionError for a transition not in ALLOWED_TRANSITIONS."""
    allowed = ALLOWED_TRANSITIONS.get(alert.status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"{alert.status.value} -> {to_status.value} is not an allowed transition "
            f"(allowed from {alert.status.value}: {sorted(s.value for s in allowed) or 'none (terminal)'})"
        )
    event = CaseEvent(
        timestamp=now or datetime.now(timezone.utc),
        actor=actor,
        from_status=alert.status,
        to_status=to_status,
        note=note,
    )
    return alert.model_copy(update={"status": to_status, "history": [*alert.history, event]})
