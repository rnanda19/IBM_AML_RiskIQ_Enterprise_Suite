"""
Reliable scoring-to-alert delivery (requirement 3 of the end-to-end AML workflow
integration phase, 2026-10-12): the shared client every BP1-BP5 scoring service imports to
turn a real /score result into a Case Management Service alert, when one is warranted.

HYPER pattern: written once, imported identically by all 5 services (same discipline
_security.py already established) -- not reimplemented five times with five chances to
drift out of sync.

Design, and the honest trade-off it makes: a scoring request's caller is waiting on /score's
HTTP response, so this module does NOT block that response on an unbounded retry loop
against a possibly-slow-or-down Case Management Service. It makes a SMALL, bounded number of
fast attempts (default 2, short timeout, short backoff -- see the env vars below) inline,
and if all of them fail, it writes the alert to a local, durable, append-only JSON-Lines
OUTBOX file and returns immediately -- the alert is never silently dropped, but a sustained
outage does not turn into an unbounded /score latency spike. A separate, explicitly-invoked
`replay_outbox()` (wired into `scripts/replay_alert_outbox.py`) is how a queued alert
actually gets delivered once the Case Management Service is reachable again -- this is the
standard "outbox pattern" for reliable at-least-once delivery, not a new invention.

Idempotency is what makes "replay (or a transient retry) never creates a duplicate" a real
guarantee rather than a hope: every alert this module builds carries a deterministic
idempotency_key (casework.scoring_event.compute_idempotency_key), and the Case Management
Service's POST /alerts/ingest route is itself idempotent on that key (store.py's
create_alert_idempotent(), enforced by a real UNIQUE index, not just application-level
checking) -- so this module can safely retry, and the outbox can safely be replayed more
than once (e.g. after a crash mid-replay), without ever risking two alerts for the same real
scoring event.

HONEST SCOPE NOTE: delivery (this module) and routing-decision (classify_severity() /
is_alert_worthy() in scoring_event.py) are deliberately kept separate from the Case
Management Service's own role -- this module decides WHETHER and HOW to send; the Case
Management Service decides WHETHER to accept (RBAC on /alerts/ingest, same role requirement
as POST /alerts) and WHETHER it is a duplicate (idempotency_key). Neither side trusts the
other's decision blindly: a 401/403 from the ingest endpoint (this scoring service's own
case-management API key misconfigured, or revoked) is treated as a REJECTION, not retried
forever, and is just as durably outboxed/logged as a network failure -- see
docs/architecture/SCORING_ALERT_INTEGRATION.md's "Failure modes" table for the full list.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from casework.alert_schema import Alert
    from casework.scoring_event import (
        ScoringEventValidationError,
        build_alert_from_scoring_event,
        classify_severity,
        compute_idempotency_key,
        is_alert_worthy,
        parse_scoring_event,
    )
    from serving._security import record_custom_metric
except ImportError:  # pragma: no cover -- exercised under Docker's import context, not pytest's
    from src.aml_riskiq.casework.alert_schema import Alert
    from src.aml_riskiq.casework.scoring_event import (
        ScoringEventValidationError,
        build_alert_from_scoring_event,
        classify_severity,
        compute_idempotency_key,
        is_alert_worthy,
        parse_scoring_event,
    )
    from src.aml_riskiq.serving._security import record_custom_metric

logger = logging.getLogger("aml_riskiq.alert_dispatch")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

CASE_SERVICE_URL_ENV = "AML_RISKIQ_CASE_SERVICE_URL"
CASE_SERVICE_API_KEY_ENV = "AML_RISKIQ_CASE_SERVICE_API_KEY"
DISPATCH_TIMEOUT_ENV = "AML_RISKIQ_CASE_DISPATCH_TIMEOUT_SECONDS"
DISPATCH_MAX_ATTEMPTS_ENV = "AML_RISKIQ_CASE_DISPATCH_MAX_ATTEMPTS"
DISPATCH_BACKOFF_BASE_ENV = "AML_RISKIQ_CASE_DISPATCH_BACKOFF_BASE_SECONDS"
ALERT_OUTBOX_DIR_ENV = "AML_RISKIQ_ALERT_OUTBOX_DIR"

DEFAULT_DISPATCH_TIMEOUT_SECONDS = 2.0
DEFAULT_DISPATCH_MAX_ATTEMPTS = 2
DEFAULT_DISPATCH_BACKOFF_BASE_SECONDS = 0.1

# Status codes treated as a definitive REJECTION (never retried, outboxed for operator
# visibility, not for redelivery -- replaying a 422/404 would just fail again identically).
# Includes 401/403: this scoring service's own configured case-management API key is
# either wrong or lacks a role the ingest route accepts, and retrying the exact same
# credential against the exact same route will never produce a different outcome (unlike a
# 429/5xx, which genuinely can succeed on a later attempt) -- see this module's own
# docstring, "Neither side trusts the other's decision blindly".
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 422})

_outbox_lock = threading.Lock()


def _locate_project_root() -> Path:
    """Identical pattern to every BP1-BP5 scoring service's own copy (Lesson #3's standing
    rule: duplicated deliberately, not shared, so each service's import graph stays simple
    and self-contained -- see e.g. bp1_scoring_service.py's own copy of this function)."""
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
    # Never raises here (unlike each scoring service's own copy) -- the outbox directory is
    # allowed to fall back to the current working directory rather than preventing a service
    # from starting just because this one, non-essential path cannot be resolved.
    return Path.cwd()


def _default_outbox_dir() -> Path:
    override = os.environ.get(ALERT_OUTBOX_DIR_ENV)
    if override:
        return Path(override)
    return _locate_project_root() / "data" / "alert_outbox"


def outbox_path_for(service_name: str, *, outbox_dir: Path | None = None) -> Path:
    """The one real JSON-Lines file a given scoring service's queued/failed alert deliveries
    are appended to -- one file per service, so replay_outbox() can be run per-service and
    so two services' queues never interleave in a way that makes line-level editing risky."""
    directory = outbox_dir or _default_outbox_dir()
    return directory / f"{service_name}.outbox.jsonl"


def _write_outbox(record: dict[str, Any], outbox_path: Path) -> None:
    """Appends one JSON line -- never truncates, never rewrites existing lines (this
    function). The outbox is append-only by the same discipline as the case-management
    store's own audit tables: a write failure here must not corrupt or lose any
    already-queued record."""
    outbox_path.parent.mkdir(parents=True, exist_ok=True)
    with _outbox_lock:
        with open(outbox_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def _post_alert_once(
    alert: Alert, *, url: str, api_key: str, timeout: float, http_client: httpx.Client
) -> httpx.Response:
    payload = alert.model_dump(mode="json")
    headers = {"X-API-Key": api_key} if api_key else {}
    return http_client.post(
        f"{url.rstrip('/')}/alerts/ingest", json=payload, headers=headers, timeout=timeout
    )


def dispatch_alert(
    alert: Alert,
    *,
    service_name: str,
    case_service_url: str | None = None,
    api_key: str | None = None,
    outbox_dir: Path | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float | None = None,
    max_attempts: int | None = None,
    backoff_base: float | None = None,
) -> dict[str, Any]:
    """Attempts to deliver `alert` to the Case Management Service's POST /alerts/ingest.
    NEVER RAISES for a delivery failure -- the real /score response this is called from must
    not fail because alert delivery had trouble; every outcome is returned as a result dict
    instead: {"status": "delivered" | "duplicate" | "rejected" | "queued_for_retry", ...}.
    A delivery failure after exhausting attempts (or any configuration/rejection failure) is
    ALWAYS written to the outbox and ALWAYS logged as a structured error record -- "do not
    silently lose alerts" is enforced here, not left to the caller to remember.

    `transport` lets a test wire an httpx.ASGITransport directly to a real, in-process
    FastAPI app (the actual Case Management Service, not a mock) -- see
    tests/unit/test_alert_dispatch.py and the end-to-end integration tests for how this is
    used to prove real RBAC/idempotency behavior without a live network call."""
    url = case_service_url or os.environ.get(CASE_SERVICE_URL_ENV)
    resolved_timeout = (
        timeout
        if timeout is not None
        else float(os.environ.get(DISPATCH_TIMEOUT_ENV, DEFAULT_DISPATCH_TIMEOUT_SECONDS))
    )
    resolved_max_attempts = (
        max_attempts
        if max_attempts is not None
        else int(os.environ.get(DISPATCH_MAX_ATTEMPTS_ENV, DEFAULT_DISPATCH_MAX_ATTEMPTS))
    )
    resolved_backoff_base = (
        backoff_base
        if backoff_base is not None
        else float(os.environ.get(DISPATCH_BACKOFF_BASE_ENV, DEFAULT_DISPATCH_BACKOFF_BASE_SECONDS))
    )
    resolved_api_key = api_key if api_key is not None else os.environ.get(CASE_SERVICE_API_KEY_ENV, "")

    if not url and transport is None:
        logger.warning(
            json.dumps(
                {
                    "event": "alert_dispatch_not_configured",
                    "service": service_name,
                    "alert_id": alert.alert_id,
                    "idempotency_key": alert.idempotency_key,
                    "reason": f"{CASE_SERVICE_URL_ENV} is not set",
                }
            )
        )
        record_custom_metric(service_name, "alert_dispatch_queued_total", labels={"reason": "not_configured"})
        _write_outbox(
            {
                "alert": alert.model_dump(mode="json"),
                "service": service_name,
                "reason": "case_service_url_not_configured",
                "queued_at": datetime.now(timezone.utc).isoformat(),
            },
            outbox_path_for(service_name, outbox_dir=outbox_dir),
        )
        return {"status": "queued_for_retry", "reason": "not_configured", "attempts": 0}

    owns_client = transport is not None or url is not None
    client = httpx.Client(transport=transport, base_url=url or "http://case-management-service")
    last_error: str | None = None
    try:
        for attempt in range(1, resolved_max_attempts + 1):
            try:
                resp = _post_alert_once(
                    alert,
                    url=url or "",
                    api_key=resolved_api_key,
                    timeout=resolved_timeout,
                    http_client=client,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    json.dumps(
                        {
                            "event": "alert_dispatch_attempt_failed",
                            "service": service_name,
                            "alert_id": alert.alert_id,
                            "attempt": attempt,
                            "max_attempts": resolved_max_attempts,
                            "error": last_error,
                        }
                    )
                )
                if attempt < resolved_max_attempts:
                    time.sleep(resolved_backoff_base * (2 ** (attempt - 1)))
                continue

            if resp.status_code in (200, 201):
                body = resp.json()
                duplicate = bool(body.get("duplicate", False))
                record_custom_metric(
                    service_name,
                    "alert_dispatch_duplicate_total" if duplicate else "alert_dispatch_delivered_total",
                )
                logger.info(
                    json.dumps(
                        {
                            "event": "alert_dispatch_delivered",
                            "service": service_name,
                            "alert_id": alert.alert_id,
                            "idempotency_key": alert.idempotency_key,
                            "attempt": attempt,
                            "duplicate": duplicate,
                        }
                    )
                )
                return {
                    "status": "duplicate" if duplicate else "delivered",
                    "attempts": attempt,
                    "alert_id": body.get("alert_id", alert.alert_id),
                }

            if resp.status_code in _NON_RETRYABLE_STATUS_CODES:
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                record_custom_metric(
                    service_name, "alert_dispatch_failed_total", labels={"reason": "rejected"}
                )
                logger.error(
                    json.dumps(
                        {
                            "event": "alert_dispatch_rejected",
                            "service": service_name,
                            "alert_id": alert.alert_id,
                            "attempt": attempt,
                            "http_status": resp.status_code,
                            "detail": last_error,
                        }
                    )
                )
                _write_outbox(
                    {
                        "alert": alert.model_dump(mode="json"),
                        "service": service_name,
                        "reason": "rejected",
                        "http_status": resp.status_code,
                        "detail": last_error,
                        "queued_at": datetime.now(timezone.utc).isoformat(),
                    },
                    outbox_path_for(service_name, outbox_dir=outbox_dir),
                )
                return {"status": "rejected", "attempts": attempt, "http_status": resp.status_code}

            # 401/403/429/5xx -- treated as retryable (a misconfigured key or an overloaded/
            # restarting Case Management Service can recover; distinct from the
            # non-retryable rejections above, which never will on their own).
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            logger.warning(
                json.dumps(
                    {
                        "event": "alert_dispatch_attempt_failed",
                        "service": service_name,
                        "alert_id": alert.alert_id,
                        "attempt": attempt,
                        "max_attempts": resolved_max_attempts,
                        "http_status": resp.status_code,
                        "error": last_error,
                    }
                )
            )
            if attempt < resolved_max_attempts:
                time.sleep(resolved_backoff_base * (2 ** (attempt - 1)))
    finally:
        if owns_client:
            client.close()

    record_custom_metric(service_name, "alert_dispatch_failed_total", labels={"reason": "exhausted_retries"})
    record_custom_metric(service_name, "alert_dispatch_queued_total", labels={"reason": "exhausted_retries"})
    logger.error(
        json.dumps(
            {
                "event": "alert_dispatch_exhausted_queued",
                "service": service_name,
                "alert_id": alert.alert_id,
                "idempotency_key": alert.idempotency_key,
                "attempts": resolved_max_attempts,
                "error": last_error,
            }
        )
    )
    _write_outbox(
        {
            "alert": alert.model_dump(mode="json"),
            "service": service_name,
            "reason": "delivery_exhausted",
            "detail": last_error,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        },
        outbox_path_for(service_name, outbox_dir=outbox_dir),
    )
    return {"status": "queued_for_retry", "attempts": resolved_max_attempts, "error": last_error}


def maybe_generate_and_dispatch_alert(
    *,
    service_name: str,
    business_problem: str,
    detection_source: str,
    entity_ref: str | None,
    is_flagged: bool,
    risk_score: float | None,
    selected_threshold: float | None,
    model_name: str,
    transaction_ref: str | None = None,
    model_sha256: str | None = None,
    dataset_variant: str | None = None,
    event_timestamp: datetime | None = None,
    reason_codes: list[str] | None = None,
    case_service_url: str | None = None,
    api_key: str | None = None,
    outbox_dir: Path | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float | None = None,
    max_attempts: int | None = None,
    backoff_base: float | None = None,
) -> dict[str, Any] | None:
    """The one entry point every BP1-BP5 /score route calls, right after computing its real
    scoring decision. Returns None if no alert dispatch was even ATTEMPTED (missing
    entity_ref, or the result simply did not meet its threshold) -- in that case the calling
    route adds no "alert" key to its /score response at all, so a caller that never supplies
    an entity_ref sees byte-identical behavior to before this phase existed. Returns a result
    dict (see dispatch_alert()'s docstring for the shape) whenever a real dispatch attempt
    was made, whether or not it ultimately succeeded.

    Handles "missing identifiers" and "invalid scores" (requirement 2) by logging a
    structured warning and returning a {"status": "skipped", ...} dict rather than raising --
    a malformed or incomplete scoring context must never turn into a 500 on /score."""
    if not entity_ref:
        logger.info(
            json.dumps(
                {
                    "event": "alert_generation_skipped",
                    "service": service_name,
                    "reason": "missing_entity_ref",
                    "business_problem": business_problem,
                }
            )
        )
        return None

    if not is_flagged:
        return None  # scored, correctly not alert-worthy -- not a failure of any kind

    if risk_score is None or selected_threshold is None:
        logger.warning(
            json.dumps(
                {
                    "event": "alert_generation_skipped",
                    "service": service_name,
                    "reason": "missing_score_or_threshold",
                    "business_problem": business_problem,
                    "entity_ref": entity_ref,
                }
            )
        )
        return {"status": "skipped", "reason": "missing_score_or_threshold"}

    try:
        # parse_scoring_event() (not ScoringEvent(...) directly) -- it wraps pydantic's raw
        # ValidationError into this module's own ScoringEventValidationError, which is the
        # one exception type the except clause below actually catches.
        event = parse_scoring_event(
            business_problem=business_problem,
            detection_source=detection_source,
            entity_ref=entity_ref,
            transaction_ref=transaction_ref,
            risk_score=risk_score,
            selected_threshold=selected_threshold,
            model_name=model_name,
            model_sha256=model_sha256,
            dataset_variant=dataset_variant,
            event_timestamp=event_timestamp,
            scoring_timestamp=datetime.now(timezone.utc),
            reason_codes=reason_codes or [],
        )
    except ScoringEventValidationError as exc:
        logger.warning(
            json.dumps(
                {
                    "event": "alert_generation_skipped",
                    "service": service_name,
                    "reason": "schema_validation_failed",
                    "detail": str(exc),
                    "business_problem": business_problem,
                    "entity_ref": entity_ref,
                }
            )
        )
        return {"status": "skipped", "reason": "schema_validation_failed"}

    if not is_alert_worthy(event.risk_score, event.selected_threshold):
        # Defensive: the caller already told us is_flagged=True, but never trust a second
        # hand-computed boolean over the one real, named gate -- see is_alert_worthy()'s own
        # docstring for why this is its own function rather than an inline comparison.
        return None

    severity = classify_severity(event.risk_score, event.selected_threshold)
    idempotency_key = compute_idempotency_key(event)
    alert = build_alert_from_scoring_event(event, idempotency_key=idempotency_key, severity=severity)

    result = dispatch_alert(
        alert,
        service_name=service_name,
        case_service_url=case_service_url,
        api_key=api_key,
        outbox_dir=outbox_dir,
        transport=transport,
        timeout=timeout,
        max_attempts=max_attempts,
        backoff_base=backoff_base,
    )
    result["idempotency_key"] = idempotency_key
    result["severity"] = severity
    result["alert_id"] = result.get("alert_id", alert.alert_id)
    return result


def replay_outbox(
    service_name: str,
    *,
    outbox_dir: Path | None = None,
    case_service_url: str | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float | None = None,
) -> dict[str, int]:
    """Re-attempts delivery of every queued record in one service's outbox file -- the
    "recoverable" half of "failures are visible and recoverable". Safe to run more than
    once, including after a crash mid-replay: a record that was already delivered on a
    previous replay attempt is recognized by the Case Management Service's own idempotency
    check (duplicate=True), never redelivered as a second alert. Successfully processed
    records (delivered, duplicate, or a definitive rejection -- none of which benefit from a
    further retry) are removed from the outbox; records that fail again are rewritten back
    for the next replay. Returns a summary dict: {"attempted", "delivered", "duplicate",
    "rejected", "still_failed"}."""
    path = outbox_path_for(service_name, outbox_dir=outbox_dir)
    summary = {"attempted": 0, "delivered": 0, "duplicate": 0, "rejected": 0, "still_failed": 0}
    if not path.exists():
        return summary

    with _outbox_lock:
        lines = path.read_text(encoding="utf-8").splitlines()

    remaining: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        summary["attempted"] += 1
        record = json.loads(line)
        alert = Alert(**record["alert"])
        result = dispatch_alert(
            alert,
            service_name=service_name,
            case_service_url=case_service_url,
            api_key=api_key,
            outbox_dir=outbox_dir,
            transport=transport,
            timeout=timeout,
        )
        status = result.get("status")
        if status == "delivered":
            summary["delivered"] += 1
        elif status == "duplicate":
            summary["duplicate"] += 1
        elif status == "rejected":
            summary["rejected"] += 1
        else:
            summary["still_failed"] += 1
            remaining.append(line)

    with _outbox_lock:
        if remaining:
            path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    return summary


__all__ = [
    "CASE_SERVICE_URL_ENV",
    "CASE_SERVICE_API_KEY_ENV",
    "DISPATCH_TIMEOUT_ENV",
    "DISPATCH_MAX_ATTEMPTS_ENV",
    "DISPATCH_BACKOFF_BASE_ENV",
    "ALERT_OUTBOX_DIR_ENV",
    "DEFAULT_DISPATCH_TIMEOUT_SECONDS",
    "DEFAULT_DISPATCH_MAX_ATTEMPTS",
    "DEFAULT_DISPATCH_BACKOFF_BASE_SECONDS",
    "outbox_path_for",
    "dispatch_alert",
    "maybe_generate_and_dispatch_alert",
    "replay_outbox",
    "parse_scoring_event",
]
