"""The unified alert schema -- one representation for an alert regardless of which BP's
scoring service produced it. See the casework package docstring for scope.

Every field below is either (a) something a real scoring service response already returns
(probability, threshold, champion_name -- see e.g. bp1_scoring_service.score_transaction's
real return dict), (b) something the live model-registry fingerprint already exposes under
/health (model_sha256 -- see MODEL_REGISTRY.md), or (c) something the caller must supply
because no current service response carries it (entity_ref, transaction_ref, reason_codes).
Nothing here is invented data a real deployment would not actually have access to."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

ALERT_SCHEMA_VERSION = "1.0.0"


class CaseStatus(str, Enum):
    """Case lifecycle states. See case_lifecycle.py for the allowed-transition graph."""

    NEW = "new"
    ASSIGNED = "assigned"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    CLOSED = "closed"
    UNRESOLVED = "unresolved"


class CaseEvent(BaseModel):
    """One recorded transition in an alert's audit history. Immutable once created -- see
    case_lifecycle.transition(), which is the only code path that should ever append one."""

    timestamp: datetime
    actor: str
    from_status: CaseStatus | None
    to_status: CaseStatus
    note: str | None = None


class Alert(BaseModel):
    """A unified alert, regardless of which BP's scoring service (or BP3's rule) produced
    the underlying detection. Immutable-by-convention: case_lifecycle.transition() returns a
    new Alert with an appended history entry rather than mutating one in place, so a prior
    state is never silently overwritten."""

    schema_version: str = ALERT_SCHEMA_VERSION
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Caller-supplied: no current /score request or response carries these (see package
    # docstring's disclosed gap) -- the caller must already track which entity/transaction
    # was scored and pass it through.
    entity_ref: str
    transaction_ref: str | None = None

    # From the real scoring response / model registry -- not invented.
    business_problem: str  # "BP1".."BP5" -- BP3's RULE_CARD.md rule counts as a detection source too
    detection_source: str  # e.g. "xgboost_champion", "2hop_proximity_rule"
    risk_score: float  # the real `probability` (or BP3's rule output) from /score
    selected_threshold: float  # the real `threshold` from /score / the saved validation report
    model_name: str  # the real `champion_name` from /score
    model_sha256: str | None = None  # the real model-registry fingerprint from /health, if available
    dataset_variant: str | None = None  # the real `dataset_variant` from /score

    event_timestamp: datetime | None = None  # when the underlying transaction occurred, if known
    scoring_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    reason_codes: list[str] = Field(default_factory=list)  # caller-supplied; see explainability module
    status: CaseStatus = CaseStatus.NEW
    history: list[CaseEvent] = Field(default_factory=list)


def alert_from_score_response(
    *,
    entity_ref: str,
    business_problem: str,
    detection_source: str,
    score_response: dict,
    transaction_ref: str | None = None,
    model_sha256: str | None = None,
    event_timestamp: datetime | None = None,
    reason_codes: list[str] | None = None,
) -> Alert:
    """Builds an Alert from one real /score response dict (the exact shape each BP1/BP2/BP4/
    BP5 scoring service's score_transaction()/score_endpoint() returns, or BP3's rule
    equivalent). Raises KeyError if the response is missing an expected field rather than
    silently defaulting -- a malformed response should fail loudly, not produce a
    plausible-looking but wrong Alert."""
    risk_score = score_response.get("probability")
    if risk_score is None:
        # BP3's rule-based response uses a differently-named score field -- see RULE_CARD.md.
        risk_score = score_response["rule_score"]
    return Alert(
        entity_ref=entity_ref,
        transaction_ref=transaction_ref,
        business_problem=business_problem,
        detection_source=detection_source,
        risk_score=float(risk_score),
        selected_threshold=float(score_response["threshold"]),
        model_name=str(score_response["champion_name"]),
        model_sha256=model_sha256,
        dataset_variant=score_response.get("dataset_variant"),
        event_timestamp=event_timestamp,
        reason_codes=reason_codes or [],
    )
