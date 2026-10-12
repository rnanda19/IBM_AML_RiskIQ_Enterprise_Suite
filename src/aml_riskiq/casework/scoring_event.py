"""The standardized, validated scoring-event contract (requirement 2 of the end-to-end AML
workflow integration phase, 2026-10-12): one normalized representation of "a BP1-BP5 /score
(or BP3's rule) result that might warrant a case-management alert", independent of which
service produced it. Pairs with `alert_schema.Alert` (the *case-management* record) and
`store.AlertStore` (persistence) -- this module is the layer in between: deciding whether a
real scoring outcome is alert-worthy, at what severity, and building the Alert from it.

Deliberately NOT a new ML signal: every field here is either copied verbatim from a real
/score response (risk_score, selected_threshold, model_name, dataset_variant -- see
alert_schema.py's own docstring for the same discipline) or supplied by the calling scoring
service (entity_ref, transaction_ref -- see each BP service's own module docstring for
exactly where each comes from). classify_severity()'s bands are a configurable ROUTING rule
over an already-computed score, not a new model.

HONEST SCOPE NOTE (do not treat a model prediction as proof of money laundering): an
automatically generated Alert represents a model's risk score meeting a configured
operational threshold -- nothing here, and nothing an automated alert produces, constitutes
a finding, confirmation, or evidence of money laundering. See MODEL_PREDICTION_DISCLAIMER
below; every automatically created Alert starts in CaseStatus.NEW and requires human
investigation (case_lifecycle.py's state machine) before any compliance determination, same
as a manually created one -- this module never sets, and cannot set, a terminal status.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .alert_schema import Alert

SCORING_EVENT_SCHEMA_VERSION = "1.0.0"
# Schema versions this build can accept. A real deployment migrating to a new event shape
# bumps SCORING_EVENT_SCHEMA_VERSION and adds the new version here once this module's own
# parsing supports it -- an event asserting an unlisted version is rejected explicitly
# (requirement: "handle ... incompatible schema versions"), never silently coerced.
SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS = {"1.0.0"}

MODEL_PREDICTION_DISCLAIMER = (
    "An automatically generated alert reflects a model's risk score meeting a configured "
    "operational threshold. It is not, by itself, evidence, confirmation, or proof of money "
    "laundering; it requires human investigation (assignment, review, and an explicit "
    "escalation/closure decision by a compliance officer) before any compliance "
    "determination is made."
)

# Risk-based routing bands (requirement 4): how far risk_score sits above selected_threshold,
# expressed as a ratio so the same bands apply whether a BP's score is a continuous
# probability (BP1/BP2/BP4/BP5) or a binary rule normalized to risk_score=1.0/threshold=1.0
# (BP3 -- see bp3_rule_scoring_service.py's own dispatch call). Configurable per-deployment
# via the two env vars documented in docs/architecture/SCORING_ALERT_INTEGRATION.md, not
# hardcoded business logic a real deployment could not tune.
DEFAULT_HIGH_SEVERITY_RATIO = 1.5
DEFAULT_CRITICAL_SEVERITY_RATIO = 2.0


class ScoringEventValidationError(ValueError):
    """Raised when a scoring event fails validation in a way the caller should handle (log +
    skip alert generation) rather than crash the real /score response it is attached to."""


class ScoringEvent(BaseModel):
    """A validated, normalized scoring outcome -- the standardized event contract requirement
    2 asks for. Built by each BP service's own dispatch call (see
    serving/_alert_dispatch.py's maybe_generate_and_dispatch_alert()), never constructed by a
    caller outside this platform: this is an internal contract between a scoring service and
    the Case Management Service, not a public API a third party integrates against."""

    schema_version: str = SCORING_EVENT_SCHEMA_VERSION
    business_problem: str = Field(min_length=1)
    detection_source: str = Field(min_length=1)
    entity_ref: str = Field(min_length=1)
    transaction_ref: str | None = None
    risk_score: float
    selected_threshold: float
    model_name: str = Field(min_length=1)
    model_sha256: str | None = None
    dataset_variant: str | None = None
    event_timestamp: datetime | None = None
    scoring_timestamp: datetime
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema_version(cls, v: str) -> str:
        if v not in SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported scoring-event schema_version {v!r}; this build supports "
                f"{sorted(SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS)}. A caller sending a newer "
                "or older version must be upgraded/migrated -- never silently coerced."
            )
        return v

    @field_validator("risk_score", "selected_threshold")
    @classmethod
    def _finite_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"must be a finite number, got {v!r}")
        return v


def is_alert_worthy(risk_score: float, selected_threshold: float) -> bool:
    """The one, real, non-negotiable gate: a scoring result is alert-worthy if and only if
    the risk score meets or exceeds the operational threshold that was actually used to
    produce it. Kept as its own named function (rather than an inline `>=`) so every call
    site -- 5 scoring services plus this module's own tests -- reads the same intent."""
    return risk_score >= selected_threshold


def classify_severity(
    risk_score: float,
    selected_threshold: float,
    *,
    high_ratio: float = DEFAULT_HIGH_SEVERITY_RATIO,
    critical_ratio: float = DEFAULT_CRITICAL_SEVERITY_RATIO,
) -> str | None:
    """Risk-based routing (requirement 4): classifies an alert-worthy result into "medium" /
    "high" / "critical" by how far risk_score sits above selected_threshold, as a ratio (so
    it is dimensionless and applies identically to a continuous probability or BP3's
    normalized 1.0/1.0 binary rule). Returns None if the result does not even meet the
    threshold -- NOT alert-worthy, never classified, never routed. This is a configurable
    OPERATIONAL bucketing of an already-computed score, never a re-scoring: it does not, and
    must not, change risk_score or selected_threshold themselves."""
    if not is_alert_worthy(risk_score, selected_threshold):
        return None
    if selected_threshold <= 0:
        # A threshold of exactly 0 (any positive score flags) makes "ratio above threshold"
        # undefined (division by zero) -- fall back to the highest band for any flagged
        # result rather than crashing or silently mis-ranking it as "medium".
        return "critical" if risk_score > 0 else "medium"
    ratio = risk_score / selected_threshold
    if ratio >= critical_ratio:
        return "critical"
    if ratio >= high_ratio:
        return "high"
    return "medium"


def compute_idempotency_key(event: ScoringEvent) -> str:
    """Deterministic SHA-256 over the scoring event's STABLE identity fields -- same real
    scoring outcome (same entity/transaction/business-problem/model/score/threshold) always
    hashes to the same key, regardless of how many times delivery is retried or how many
    times the same outcome is resubmitted. Deliberately EXCLUDES scoring_timestamp (wall-
    clock at scoring time, which legitimately differs between the original attempt and a
    retry of the SAME event) and reason_codes/event_timestamp (informational, not part of
    the event's identity). HONEST LIMITATION: when transaction_ref is absent (an
    account-level, not transaction-level, scoring result -- e.g. BP3), two GENUINELY
    different scoring runs that happen to produce an identical risk_score for the same
    entity/business_problem/model/dataset_variant/threshold would collide and be treated as
    one duplicate event. Documented, not silently risked: see
    docs/architecture/SCORING_ALERT_INTEGRATION.md's "Idempotency" section."""
    canonical = json.dumps(
        {
            "schema_version": event.schema_version,
            "business_problem": event.business_problem,
            "entity_ref": event.entity_ref,
            "transaction_ref": event.transaction_ref,
            "model_name": event.model_name,
            "dataset_variant": event.dataset_variant,
            "risk_score": event.risk_score,
            "selected_threshold": event.selected_threshold,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_alert_from_scoring_event(event: ScoringEvent, *, idempotency_key: str, severity: str | None) -> Alert:
    """Builds the case-management Alert from a validated ScoringEvent. Sibling to
    alert_schema.alert_from_score_response() (which builds from a raw /score response dict,
    used by manual/offline callers) -- this one is the automated-dispatch path, so it always
    sets generation_source="automated_scoring" and carries the idempotency_key/severity that
    path computed. Does not decide alert-worthiness itself (call is_alert_worthy() first) and
    never sets a status other than Alert's own default (CaseStatus.NEW) -- see this module's
    docstring MODEL_PREDICTION_DISCLAIMER."""
    return Alert(
        entity_ref=event.entity_ref,
        transaction_ref=event.transaction_ref,
        business_problem=event.business_problem,
        detection_source=event.detection_source,
        risk_score=event.risk_score,
        selected_threshold=event.selected_threshold,
        model_name=event.model_name,
        model_sha256=event.model_sha256,
        dataset_variant=event.dataset_variant,
        event_timestamp=event.event_timestamp,
        scoring_timestamp=event.scoring_timestamp,
        reason_codes=event.reason_codes,
        idempotency_key=idempotency_key,
        severity=severity,
        generation_source="automated_scoring",
    )


def parse_scoring_event(**fields: Any) -> ScoringEvent:
    """Thin wrapper around ScoringEvent(**fields) that re-raises pydantic's ValidationError as
    this module's own ScoringEventValidationError -- so every call site (5 scoring services)
    catches ONE exception type for "this event failed validation, log it and skip alert
    generation" without importing pydantic's exception type directly."""
    from pydantic import ValidationError

    try:
        return ScoringEvent(**fields)
    except ValidationError as exc:
        raise ScoringEventValidationError(str(exc)) from exc


__all__ = [
    "SCORING_EVENT_SCHEMA_VERSION",
    "SUPPORTED_SCORING_EVENT_SCHEMA_VERSIONS",
    "MODEL_PREDICTION_DISCLAIMER",
    "DEFAULT_HIGH_SEVERITY_RATIO",
    "DEFAULT_CRITICAL_SEVERITY_RATIO",
    "ScoringEvent",
    "ScoringEventValidationError",
    "is_alert_worthy",
    "classify_severity",
    "compute_idempotency_key",
    "build_alert_from_scoring_event",
    "parse_scoring_event",
]
