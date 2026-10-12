"""Case-lifecycle state machine. The allowed-transition graph is deliberately conservative
(a case can only move forward, be closed, or go unresolved-and-reassigned) so an investigator
workflow built on this cannot silently skip review steps. See the casework package docstring
for scope.

RBAC/case-management phase (2026-10-12) additions: assign()/add_note()/add_evidence() --
the other three case-management actions alongside transition(), same immutable-by-convention
shape (return a new Alert, never mutate in place) -- and the CaseEvent hash chain
(_compute_event_hash() / verify_history_integrity()) that makes the audit trail
tamper-evident. These are pure functions over in-memory Alert objects, same as transition()
always was; src/aml_riskiq/casework/store.py is what persists their results."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .alert_schema import Alert, CaseEvent, CaseNote, CaseStatus, EvidenceReference

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


def _compute_event_hash(
    *,
    prev_event_hash: str | None,
    timestamp: datetime,
    actor: str,
    from_status: CaseStatus | None,
    to_status: CaseStatus,
    note: str | None,
) -> str:
    """SHA-256 over a canonical JSON encoding of the event's own fields PLUS the prior event's
    hash (None for the first event in a history) -- the hash-chain link. Deterministic field
    order (sort_keys=True) so the same logical event always hashes identically regardless of
    how it was constructed."""
    canonical = json.dumps(
        {
            "prev_event_hash": prev_event_hash,
            "timestamp": timestamp.isoformat(),
            "actor": actor,
            "from_status": from_status.value if from_status else None,
            "to_status": to_status.value,
            "note": note,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    event_timestamp = now or datetime.now(timezone.utc)
    prev_hash = alert.history[-1].event_hash if alert.history else None
    event_hash = _compute_event_hash(
        prev_event_hash=prev_hash,
        timestamp=event_timestamp,
        actor=actor,
        from_status=alert.status,
        to_status=to_status,
        note=note,
    )
    event = CaseEvent(
        timestamp=event_timestamp,
        actor=actor,
        from_status=alert.status,
        to_status=to_status,
        note=note,
        prev_event_hash=prev_hash,
        event_hash=event_hash,
    )
    return alert.model_copy(update={"status": to_status, "history": [*alert.history, event]})


def verify_history_integrity(alert: Alert) -> tuple[bool, str | None]:
    """Recomputes the hash chain over `alert.history` from scratch and confirms it matches
    the stored event_hash/prev_event_hash values at every link. Returns (True, None) if the
    chain is intact, or (False, reason) naming the first broken link -- a wrong prev_event_hash
    pointer, or an event_hash that does not match its own recomputed fields (either case means
    something in `history` was added, edited, or reordered outside transition()'s own append
    path). This is tamper-EVIDENCE: it proves the chain is self-consistent, which a record
    edited directly (e.g. a hand-edited database row) will not be -- it cannot prove the FIRST
    event in a chain is the true original event, only that every event after it is consistent
    with it."""
    prev_hash: str | None = None
    for i, event in enumerate(alert.history):
        if event.prev_event_hash != prev_hash:
            return False, f"history[{i}].prev_event_hash does not match the preceding event's hash"
        recomputed = _compute_event_hash(
            prev_event_hash=event.prev_event_hash,
            timestamp=event.timestamp,
            actor=event.actor,
            from_status=event.from_status,
            to_status=event.to_status,
            note=event.note,
        )
        if recomputed != event.event_hash:
            return False, f"history[{i}].event_hash does not match its own recomputed fields"
        prev_hash = event.event_hash
    return True, None


def assign(
    alert: Alert, *, assignee: str, actor: str, note: str | None = None, now: datetime | None = None
) -> Alert:
    """Sets assigned_to=assignee. If the alert is still NEW, also transitions it to ASSIGNED
    (the natural real-world meaning of "assigning" a fresh alert) in the same call -- for an
    alert that is already ASSIGNED/UNDER_REVIEW/ESCALATED/UNRESOLVED, this only reassigns the
    owner and does not change status (re-assigning a case already being worked is not itself a
    status transition). Raises InvalidTransitionError only in the NEW case, via transition()."""
    if alert.status == CaseStatus.NEW:
        alert = transition(alert, CaseStatus.ASSIGNED, actor=actor, note=note, now=now)
    return alert.model_copy(update={"assigned_to": assignee})


def add_note(alert: Alert, *, actor: str, text: str, now: datetime | None = None) -> Alert:
    """Returns a NEW Alert with one additional CaseNote appended to `notes` -- never mutates
    the given alert in place, same immutable-by-convention shape as transition(). A note never
    changes `status` (see CaseNote's own docstring)."""
    note_obj = CaseNote(timestamp=now or datetime.now(timezone.utc), actor=actor, text=text)
    return alert.model_copy(update={"notes": [*alert.notes, note_obj]})


def add_evidence(
    alert: Alert,
    *,
    actor: str,
    description: str,
    external_ref: str | None = None,
    now: datetime | None = None,
) -> Alert:
    """Returns a NEW Alert with one additional EvidenceReference appended to `evidence` --
    never mutates the given alert in place, same immutable-by-convention shape as
    transition(). An evidence reference never changes `status`."""
    ref = EvidenceReference(
        timestamp=now or datetime.now(timezone.utc),
        actor=actor,
        description=description,
        external_ref=external_ref,
    )
    return alert.model_copy(update={"evidence": [*alert.evidence, ref]})
