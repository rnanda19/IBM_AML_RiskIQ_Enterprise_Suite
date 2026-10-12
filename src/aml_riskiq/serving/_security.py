"""
Shared API hardening for the platform's FastAPI scoring services (BP1/BP2/BP4/BP5's
model-backed services and BP3's rule-based service).

HYPER pattern: this module is written ONCE and imported identically by all 5 services,
rather than re-implementing auth/rate-limiting/audit-logging five times with five chances
to drift out of sync.

What this module provides, and the honest limits of each:

1. API-KEY AUTH (`require_api_key` dependency)
   - Controlled by one shared env var: AML_RISKIQ_API_KEYS (comma-separated list of valid
     keys). Checked against the `X-API-Key` request header.
   - If AML_RISKIQ_API_KEYS is UNSET, auth is a documented no-op ("open mode") -- this is
     what keeps local development, this project's own pytest suite, and CI green without
     every test having to inject a fake key. A loud, unmissable startup warning is printed
     to stderr in this mode so it is never silently insecure in an environment where someone
     expected it to be locked down.
   - If AML_RISKIQ_API_KEYS IS set, every request to a protected endpoint must present a
     matching `X-API-Key` header or receive 401. Keys are compared with `secrets.compare_digest`
     (constant-time) to avoid a timing side-channel, and the raw key is never logged -- only a
     short, non-reversible fingerprint (first 8 hex chars of its SHA-256) is recorded for audit
     correlation.
   - Deliberately NOT applied to `/health`: liveness/readiness probes (Docker healthcheck,
     Kubernetes, a load balancer) must be able to reach `/health` without a credential, which
     is standard practice -- `/health` here returns no transaction data, only service metadata
     that was already public in this repo's own saved validation reports.

2. FAIL-CLOSED PRODUCTION GATE (`AML_RISKIQ_REQUIRE_AUTH`)
   - Open mode above is a deliberate default so local dev / CI / pytest stay green with zero
     setup -- but that same default is wrong for a real deployment, where an operator who
     forgot to set AML_RISKIQ_API_KEYS should get a hard failure at startup, not a service
     that silently serves every request unauthenticated.
   - Set AML_RISKIQ_REQUIRE_AUTH=true (or "1"/"yes", case-insensitive) to make that failure
     explicit: if it is true AND AML_RISKIQ_API_KEYS is unset/empty, `warn_if_open_mode()`
     (called once at service startup, before the app can serve traffic) raises RuntimeError
     instead of only warning, so the service refuses to boot rather than boot open. Leaving
     AML_RISKIQ_REQUIRE_AUTH unset preserves the exact open-mode-by-default behavior this
     module has always had; this is strictly additive.

3. RATE LIMITING (`get_limiter()` + `@limiter.limit(...)`)
   - Real, enforced via `slowapi` (a FastAPI/Starlette wrapper around the battle-tested
     `limits` library), keyed by the caller's remote address by default.
   - Default budget for `/score` is DEFAULT_SCORE_RATE_LIMIT ("60/minute") -- generous enough
     for this project's own synthetic-fixture test suite (a handful of calls per test) and for
     real interactive use, while still bounding a single caller's worst case. Override per-
     deployment via the AML_RISKIQ_SCORE_RATE_LIMIT env var (same string syntax `slowapi`/
     `limits` accepts, e.g. "600/minute").

4. AUDIT LOGGING (`audit_log` + `AuditLogMiddleware`)
   - Every request to every route gets ONE structured JSON line on the `aml_riskiq.audit`
     logger (stdout by default), with: UTC ISO timestamp, service name, HTTP method, path,
     status code, latency in milliseconds, caller IP, and the API-key fingerprint described
     above (or "anonymous" in open mode / for unauthenticated requests).
   - Written to stdout, not to a project-local file: this is the standard shape for a
     container workload (Notebook 4's own Dockerfiles run these services as the container's
     main process) -- log collection (Docker's own log driver, a Kubernetes sidecar, CloudWatch,
     etc.) is the deployer's responsibility, not this module's. Nothing here invents a
     logging backend that would need its own operational support.

5. ROLE-AWARE API KEYS (`require_role` dependency factory)
   - AML_RISKIQ_API_KEYS entries may optionally carry a role prefix, "role:key" (e.g.
     "investigator:abc123,admin:def456"). A bare key with no "role:" prefix is assigned the
     default role "service" for backward compatibility -- every key configured before this
     capability existed keeps working identically, with role "service".
   - `require_role(role)` returns a FastAPI dependency that, in closed mode, additionally
     requires the matched key's role to equal the requested role (or "admin", which is
     treated as satisfying every role check) -- 403 if the caller's key is valid but the
     wrong role, 401 if no valid key at all. In open mode it is a no-op, same as
     `require_api_key`.
   - HONEST SCOPE NOTE: this is a primitive, not yet applied to any of the 5 scoring
     services' routes (none have more than `/health` and `/score` today, so there is not yet
     a second route for a role distinction to protect). It exists so `/score` or a future
     route can adopt per-role requirements without changing this module again.

6. METRICS (`metrics_endpoint` + the counters `AuditLogMiddleware` already updates)
   - A minimal, dependency-free `/metrics` route in Prometheus text-exposition format:
     request counts by service/method/path/status, and total latency (so avg latency is
     `latency_seconds_sum / requests_total` per label set) -- both are real, computed from
     the same per-request data `AuditLogMiddleware` already logs, not a new data source.
   - Call `wire_metrics_endpoint(app)` once per service (after `harden_app`) to mount it.
     Deliberately unauthenticated, same reasoning as `/health`: a scrape target must be
     reachable without a credential, and it exposes no transaction data, only request
     counts/latency already visible in the audit log.
   - HONEST SCOPE NOTE: in-process counters only (reset on restart, not shared across
     multiple worker processes) -- adequate for this platform's single-process-per-container
     deployment shape, not a drop-in for a multi-worker production deployment without an
     external aggregator (e.g. the Prometheus multiprocess mode a real deployment would add).

HONEST SCOPE NOTE: this is application-layer hardening appropriate for a service sitting
behind a real API gateway / reverse proxy in production (TLS termination, network-level
DDoS protection, and centralized log shipping are all gateway/infra concerns this module
does not and should not reimplement). What it closes is the gap that existed before this
file: zero auth, zero rate limiting, zero audit trail, directly on five services that score
real (synthetic, in this project's own tests) financial-crime risk.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import secrets
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

API_KEYS_ENV_VAR = "AML_RISKIQ_API_KEYS"
RATE_LIMIT_ENV_VAR = "AML_RISKIQ_SCORE_RATE_LIMIT"
CASE_RATE_LIMIT_ENV_VAR = "AML_RISKIQ_CASE_RATE_LIMIT"
REQUIRE_AUTH_ENV_VAR = "AML_RISKIQ_REQUIRE_AUTH"
DEFAULT_SCORE_RATE_LIMIT = "60/minute"
# Higher default than /score: case-management routes are typically called by a human
# investigator working a queue, not a high-throughput scoring pipeline.
DEFAULT_CASE_RATE_LIMIT = "120/minute"

_audit_logger = logging.getLogger("aml_riskiq.audit")
if not _audit_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False


DEFAULT_KEY_ROLE = "service"
ADMIN_ROLE = "admin"

# The 4 standing platform roles (RBAC phase, 2026-10-12) -- see docs/security/RBAC.md for
# the full per-route permission matrix. "administrator" in the business language is this
# module's existing ADMIN_ROLE ("admin") -- not a 5th string -- so every API key configured
# before this phase keeps working identically.
ANALYST_ROLE = "analyst"
INVESTIGATOR_ROLE = "investigator"
COMPLIANCE_OFFICER_ROLE = "compliance_officer"
PLATFORM_ROLES = (ANALYST_ROLE, INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE, ADMIN_ROLE)


def _configured_api_keys() -> set[str] | None:
    """Returns the configured key set, or None if AML_RISKIQ_API_KEYS is unset (open mode).
    Re-reads the env var on every call (not cached at import time) so a test's monkeypatch
    of the env var takes effect without needing to reimport the module."""
    parsed = _configured_api_keys_with_roles()
    if parsed is None:
        return None
    return set(parsed.keys())


def _configured_api_keys_with_roles() -> dict[str, str] | None:
    """Returns {key: role}, or None if AML_RISKIQ_API_KEYS is unset (open mode). An entry
    without a "role:" prefix gets DEFAULT_KEY_ROLE, so every key configured before role
    support existed keeps working identically. Re-read on every call, same
    monkeypatch-friendliness as _configured_api_keys()."""
    raw = os.environ.get(API_KEYS_ENV_VAR)
    if raw is None or raw.strip() == "":
        return None
    result: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            role, _, key = entry.partition(":")
            role, key = role.strip(), key.strip()
        else:
            role, key = DEFAULT_KEY_ROLE, entry
        if key:
            result[key] = role or DEFAULT_KEY_ROLE
    return result


def _truthy(value: str | None) -> bool:
    """Parses a boolean-ish env var string ("true"/"1"/"yes", case-insensitive -> True;
    anything else, including unset/empty, -> False)."""
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _require_auth_enabled() -> bool:
    """Whether AML_RISKIQ_REQUIRE_AUTH is set to a truthy value. Re-read on every call, same
    monkeypatch-friendliness as _configured_api_keys()."""
    return _truthy(os.environ.get(REQUIRE_AUTH_ENV_VAR))


def _key_fingerprint(key: str) -> str:
    """Short, non-reversible identifier for audit logs -- never logs the raw key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def resolve_caller_role(x_api_key: str | None) -> tuple[str, str]:
    """Returns (role, caller_id) without raising -- the one role-aware primitive a route
    handler can call directly when its required role depends on something other than a
    static Depends() (e.g. the request body, as in case_management_service's /transition,
    where CLOSED/ESCALATED require compliance_officer+ but UNDER_REVIEW/UNRESOLVED only
    require investigator+). role is one of: "anonymous" (open mode -- AML_RISKIQ_API_KEYS
    unset, matches every other primitive's open-mode behavior), "none" (closed mode, no
    X-API-Key header at all), "invalid" (closed mode, header present but matches no
    configured key), or the caller's real configured role string (ADMIN_ROLE included --
    this function does NOT apply the admin-satisfies-every-role bypass itself; that is
    require_any_role()'s job, so a caller of this function sees the literal matched role
    and decides for itself). caller_id mirrors require_api_key's return value ("anonymous"
    or the key fingerprint) for audit-log correlation."""
    configured = _configured_api_keys_with_roles()
    if configured is None:
        return "anonymous", "anonymous"
    if x_api_key is None:
        return "none", "anonymous"
    for candidate_key, candidate_role in configured.items():
        if secrets.compare_digest(x_api_key, candidate_key):
            return candidate_role, _key_fingerprint(x_api_key)
    return "invalid", "anonymous"


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: enforces AML_RISKIQ_API_KEYS when it is set, else is a documented
    no-op. Returns a caller identifier ("anonymous" in open mode, else the key's fingerprint)
    that route handlers / the audit middleware can use for correlation."""
    configured = _configured_api_keys()
    if configured is None:
        return "anonymous"
    if x_api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header.")
    # Constant-time membership check against every configured key, so a caller cannot use
    # response timing to learn whether a prefix of their guess matched any real key.
    matched = any(secrets.compare_digest(x_api_key, candidate) for candidate in configured)
    if not matched:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return _key_fingerprint(x_api_key)


def require_any_role(*roles: str) -> Callable[[str | None], str]:
    """Returns a FastAPI dependency requiring a valid API key whose configured role is one of
    `roles`, or ADMIN_ROLE (admin satisfies every role check) -- 403 if the caller's key is
    valid but none of the accepted roles, 401 if no valid key at all. In open mode it is a
    no-op, identical to `require_api_key`. This is the general form `require_role()` below
    delegates to; use this one directly whenever a route accepts more than one role (e.g.
    "investigator OR compliance_officer")."""

    def _dependency(x_api_key: str | None = Header(default=None)) -> str:
        matched_role, caller_id = resolve_caller_role(x_api_key)
        if matched_role == "anonymous":
            return "anonymous"
        if matched_role == "none":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header.")
        if matched_role == "invalid":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
        if matched_role != ADMIN_ROLE and matched_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Key has role '{matched_role}', this route requires one of {sorted(roles)}.",
            )
        return caller_id

    return _dependency


def require_role(role: str) -> Callable[[str | None], str]:
    """Returns a FastAPI dependency requiring a valid API key whose configured role equals
    `role`, or ADMIN_ROLE (admin satisfies every role check) -- 403 if the caller's key is valid but the
    wrong role, 401 if no valid key at all. In open mode it is a no-op, identical to
    `require_api_key`. Sugar for require_any_role(role) -- kept as its own name since most
    callers (every BP1-BP5 route today) need exactly one role, not a set."""
    return require_any_role(role)


def warn_if_open_mode(service_name: str) -> None:
    """Call once at service startup (module import time). When AML_RISKIQ_API_KEYS is unset:
    - if AML_RISKIQ_REQUIRE_AUTH is also truthy, raises RuntimeError and refuses to let the
      service start in open mode (the fail-closed production gate -- see module docstring
      section 2);
    - otherwise prints an unmissable stderr warning and lets the service start in open mode,
      exactly as before this gate existed, so open mode is never silently in effect in an
      environment where someone expected auth to be enforced, and local dev / CI are
      unaffected by default."""
    if _configured_api_keys() is not None:
        return
    if _require_auth_enabled():
        raise RuntimeError(
            f"[{service_name}] REFUSING TO START: {REQUIRE_AUTH_ENV_VAR} is set but "
            f"{API_KEYS_ENV_VAR} is unset/empty. Set {API_KEYS_ENV_VAR} to a comma-separated "
            "list of keys, or unset AML_RISKIQ_REQUIRE_AUTH to run in open mode (not "
            "recommended outside local development)."
        )
    print(
        f"[{service_name}] WARNING: {API_KEYS_ENV_VAR} is not set -- this service is "
        "running WITHOUT API-key auth (open mode). Set AML_RISKIQ_API_KEYS to a "
        f"comma-separated list of keys to require authentication on protected endpoints, or "
        f"set {REQUIRE_AUTH_ENV_VAR}=true to make a missing key set a hard startup failure "
        "instead of a warning.",
        file=sys.stderr,
    )


def get_limiter() -> Limiter:
    """One Limiter per process, keyed by remote address (the caller's source IP as seen by
    this service -- behind a reverse proxy, configure the proxy to forward the real client IP
    if per-caller limiting across proxied requests matters for a given deployment)."""
    return Limiter(key_func=get_remote_address)


def score_rate_limit() -> str:
    """The configured /score rate-limit string, re-read from the env var on every call for
    the same monkeypatch-friendliness as _configured_api_keys()."""
    return os.environ.get(RATE_LIMIT_ENV_VAR, DEFAULT_SCORE_RATE_LIMIT)


def case_rate_limit() -> str:
    """The configured case-management rate-limit string -- same env-var-override pattern as
    score_rate_limit(), separate budget/env-var since case-management traffic (a human
    investigator working a queue) has a different realistic shape than /score."""
    return os.environ.get(CASE_RATE_LIMIT_ENV_VAR, DEFAULT_CASE_RATE_LIMIT)


REQUEST_ID_HEADER = "X-Request-ID"


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emits one structured JSON audit line per request, for every route (health checks
    included, so a gap in traffic is visible too) -- regardless of whether auth or rate
    limiting allowed, rejected, or throttled the request.

    REQUEST CORRELATION (added 2026-10-12, Improvement 3 production-readiness pass): every
    request gets a correlation identifier -- the caller's own `X-Request-ID` header if it
    sent one (so a caller's own tracing ID round-trips through this service unchanged,
    standard practice for a service sitting behind a gateway that already assigns one), or a
    freshly generated UUID4 otherwise. It is echoed back on the response's `X-Request-ID`
    header and included in the audit-log line as `request_id`, so a single real request can
    be traced end to end (gateway log -> this service's audit log -> any downstream service
    it calls, e.g. a scoring service's alert-dispatch call to case-management, which the
    caller can also pass the same header on) without needing a dedicated tracing backend."""

    def __init__(self, app: FastAPI, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.monotonic()
        caller_key = request.headers.get("x-api-key")
        caller_id = _key_fingerprint(caller_key) if caller_key else "anonymous"
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            audit_log(
                service_name=self._service_name,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=elapsed_ms,
                client_ip=get_remote_address(request),
                caller_id=caller_id,
                request_id=request_id,
            )
            _record_metric(self._service_name, request.method, request.url.path, status_code, elapsed_ms)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


_metrics_lock = threading.Lock()
_request_counts: dict[tuple[str, str, str, int], int] = {}
_latency_sums: dict[tuple[str, str, str, int], float] = {}


def _record_metric(service_name: str, method: str, path: str, status_code: int, latency_ms: float) -> None:
    """In-process counters only -- reset on restart, not shared across multiple worker
    processes (see module docstring section 6's scope note)."""
    key = (service_name, method, path, status_code)
    with _metrics_lock:
        _request_counts[key] = _request_counts.get(key, 0) + 1
        _latency_sums[key] = _latency_sums.get(key, 0.0) + (latency_ms / 1000.0)


def render_metrics() -> str:
    """Renders the current in-process counters as Prometheus text-exposition format."""
    lines = [
        "# HELP aml_riskiq_requests_total Total requests by service, method, path, status.",
        "# TYPE aml_riskiq_requests_total counter",
    ]
    with _metrics_lock:
        counts = dict(_request_counts)
        sums = dict(_latency_sums)
    for (service_name, method, path, status_code), count in sorted(counts.items()):
        labels = f'service="{service_name}",method="{method}",path="{path}",status="{status_code}"'
        lines.append(f"aml_riskiq_requests_total{{{labels}}} {count}")
    lines.append("# HELP aml_riskiq_request_latency_seconds_sum Summed request latency by label set.")
    lines.append("# TYPE aml_riskiq_request_latency_seconds_sum counter")
    for (service_name, method, path, status_code), total_seconds in sorted(sums.items()):
        labels = f'service="{service_name}",method="{method}",path="{path}",status="{status_code}"'
        lines.append(f"aml_riskiq_request_latency_seconds_sum{{{labels}}} {total_seconds:.6f}")
    lines.extend(_render_custom_metric_block(_custom_counters, "counter"))
    lines.extend(_render_custom_metric_block(_custom_gauges, "gauge"))
    return "\n".join(lines) + "\n"


def wire_readiness_endpoint(app: FastAPI, check_fn: Callable[[], dict[str, bool]]) -> None:
    """Mounts GET /ready on the given app (added 2026-10-12, Improvement 3 production-
    readiness pass), deliberately distinct from /health.

    HONEST SCOPE NOTE on why these two are not just aliases of each other in THIS
    architecture: every BP1-BP5 service loads its champion model (or, for BP3, its
    near-train-flagged lookup table) synchronously at MODULE IMPORT time, before the FastAPI
    app object is even constructed -- a load failure already raises before the process can
    serve any traffic at all, so there is no real window where this process is "alive but
    not ready" the way there would be for, say, a service that connects to a database
    asynchronously after startup. /health and /ready report overlapping information for
    that reason. /ready still exists, separately, because (a) standard container
    orchestration (Kubernetes readiness probes, a load balancer's own health-check
    convention) expects a distinct readiness endpoint and (b) it gives each service a place
    to assert something more specific than "the process didn't crash on import" -- e.g.
    case-management's real check actually queries its SQLite store, not just checks that the
    module imported.

    `check_fn` returns {check_name: passed}; /ready is 200 (`{"status": "ready", ...}`) only
    if every value is truthy, else 503 (`{"status": "not_ready", ...}`) -- and an exception
    raised inside `check_fn` is caught and reported as a failed check, never an unhandled
    500 (a readiness probe failing loudly as "not ready" is the whole point; crashing the
    endpoint that reports it would defeat that point)."""

    @app.get("/ready")
    def _ready() -> Response:
        from starlette.responses import JSONResponse

        checks: dict[str, Any]
        try:
            checks = dict(check_fn())
            ready = bool(checks) and all(checks.values())
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: a readiness check
            # must never itself crash the endpoint reporting it; see docstring above.
            checks = {"check_raised_exception": True, "_error": str(exc)}
            ready = False
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )


def wire_metrics_endpoint(app: FastAPI) -> None:
    """Mounts GET /metrics on the given app, deliberately unauthenticated (see module
    docstring section 6). Call once, after harden_app()."""

    @app.get("/metrics")
    def _metrics() -> Response:
        return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")


# ----------------------------------------------------------------------------------------
# 7. CUSTOM BUSINESS METRICS (`record_custom_metric` / `set_custom_gauge`) -- added for the
#    end-to-end AML workflow integration phase (2026-10-12). The generic per-request counters
#    above (section 6) already cover HTTP-level observability (request counts/latency by
#    service/method/path/status) for any new route, including the Case Management Service's
#    new /alerts/ingest endpoint -- no new code needed there. What they cannot express is a
#    BUSINESS-level event that is not 1:1 with one HTTP request: a scoring service's alert
#    dispatch can retry several times (several HTTP attempts) for what is logically ONE
#    alert-generation decision, and "duplicate suppressed" / "unresolved alert count" are not
#    properties of any single request at all. This small, generic, dependency-free extension
#    lets any service record a NAMED counter or gauge, rendered under its own Prometheus
#    HELP/TYPE block alongside the generic request metrics -- written once here (same HYPER
#    reuse pattern as the rest of this module), not reimplemented per service.
#    HONEST SCOPE NOTE: same in-process-only limitation as section 6's counters -- reset on
#    restart, not shared across multiple worker processes/replicas.
# ----------------------------------------------------------------------------------------
_custom_metrics_lock = threading.Lock()
_custom_counters: dict[tuple[str, str, tuple[tuple[str, str], ...]], float] = {}
_custom_gauges: dict[tuple[str, str, tuple[tuple[str, str], ...]], float] = {}


def record_custom_metric(
    service_name: str, metric_name: str, *, value: float = 1.0, labels: dict[str, str] | None = None
) -> None:
    """Increments a named, monotonic business-level counter (e.g. "alerts_delivered_total").
    `metric_name` becomes the Prometheus metric name verbatim (caller's responsibility to
    pick a valid, stable name); `labels` are rendered as extra label=value pairs alongside
    the always-present `service` label."""
    key = (service_name, metric_name, tuple(sorted((labels or {}).items())))
    with _custom_metrics_lock:
        _custom_counters[key] = _custom_counters.get(key, 0.0) + value


def set_custom_gauge(
    service_name: str, metric_name: str, value: float, *, labels: dict[str, str] | None = None
) -> None:
    """Sets (not increments) a named gauge to its current real value (e.g.
    "unresolved_alerts" -- a live count, not something that only ever goes up)."""
    key = (service_name, metric_name, tuple(sorted((labels or {}).items())))
    with _custom_metrics_lock:
        _custom_gauges[key] = value


def _render_custom_metric_block(
    metrics: dict[tuple[str, str, tuple[tuple[str, str], ...]], float], metric_type: str
) -> list[str]:
    lines: list[str] = []
    with _custom_metrics_lock:
        snapshot = dict(metrics)
    by_name: dict[str, list[tuple[str, tuple[tuple[str, str], ...], float]]] = {}
    for (service_name, metric_name, label_items), value in snapshot.items():
        by_name.setdefault(metric_name, []).append((service_name, label_items, value))
    for metric_name in sorted(by_name):
        full_name = f"aml_riskiq_{metric_name}"
        lines.append(
            f"# HELP {full_name} Business-level {metric_type} recorded via "
            "record_custom_metric/set_custom_gauge."
        )
        lines.append(f"# TYPE {full_name} {metric_type}")
        for service_name, label_items, value in sorted(by_name[metric_name]):
            all_labels = (("service", service_name),) + label_items
            label_str = ",".join(f'{k}="{v}"' for k, v in all_labels)
            lines.append(f"{full_name}{{{label_str}}} {value}")
    return lines


def audit_log(
    *,
    service_name: str,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
    client_ip: str,
    caller_id: str,
    request_id: str | None = None,
) -> None:
    """Writes one structured audit record. Pulled out of the middleware as its own function
    so a route handler that needs to log something ad hoc (not just the generic request/
    response shape) can reuse the exact same record shape and logger. `request_id` is
    optional (defaults to a fresh UUID4 when not supplied, e.g. for an ad hoc call not tied
    to an in-flight HTTP request) so every existing caller of this function keeps working
    unchanged."""
    import json as _json
    from datetime import datetime, timezone

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": service_name,
        "method": method,
        "path": path,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "client_ip": client_ip,
        "caller_id": caller_id,
        "request_id": request_id or str(uuid.uuid4()),
    }
    _audit_logger.info(_json.dumps(record))


def _json_safe(value: object) -> object:
    """Recursively replaces any non-finite float (NaN/Infinity/-Infinity) with its plain
    string name, leaving every other value untouched. Real bug this closes (found 2026-10-12,
    Improvement 3 production-readiness pass): a request carrying a NaN/Infinity field value
    (a valid Python float, and FastAPI's own JSON body parsing accepts the non-standard but
    widely-supported NaN/Infinity/-Infinity tokens) that FAILS Pydantic validation (e.g. via
    `serving/_request_validation.py`'s FiniteFloatFieldsModel) still crashed with an
    unhandled 500 -- not the expected clean 422 -- because FastAPI's default
    RequestValidationError handler echoes the raw offending value back inside the error
    detail, and strict JSON encoding (correctly) refuses to serialize a literal NaN/Infinity.
    Confirmed empirically against a real running service before this fix existed. This
    function is the generic fix: sanitize error payloads before they are serialized, so a
    non-finite input value is reported as a readable string ("NaN", "Infinity",
    "-Infinity") instead of crashing the response encoder -- never exposes anything beyond
    what the caller already sent."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if value != value else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, BaseException):
        # Pydantic v2 puts the raw exception object (not a string) in a model-level
        # validator error's `ctx.error` field -- found alongside the NaN/Infinity bug this
        # function exists for for, same empirical confirmation, same fix shape: render it as
        # text instead of letting the default JSON encoder crash on a non-serializable object.
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
    """Replaces FastAPI's default RequestValidationError handler so a non-finite float in
    the rejected input (see `_json_safe` above) is always reportable as a clean 422, never an
    unhandled 500. Behaviorally identical to FastAPI's own default handler (same
    `{"detail": [...]}` shape, same 422 status) for every other validation failure -- this
    only changes what happens with an otherwise-unserializable value."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": _json_safe(exc.errors())},
    )


def harden_app(app: FastAPI, service_name: str) -> Limiter:
    """Wires rate limiting + audit logging onto an already-built FastAPI app. Call this once,
    right after `app = FastAPI(...)`, in each service module. Returns the Limiter so the
    service can decorate its own `/score` route with `@limiter.limit(score_rate_limit())`.

    API-key auth is deliberately NOT wired here as a blanket dependency -- it is attached per
    route (via `Depends(require_api_key)`) so each service can choose which routes are
    protected (every service protects `/score`; none protect `/health`, for the liveness-probe
    reason documented at the top of this module).

    Also calls `warn_if_open_mode()`, which raises RuntimeError and prevents the service from
    starting if AML_RISKIQ_REQUIRE_AUTH is set but AML_RISKIQ_API_KEYS is not (see module
    docstring section 2) -- callers do not need to call it separately."""
    limiter = get_limiter()
    app.state.limiter = limiter
    # NOTE: the ignore markers on the next two lines follow slowapi's own documented
    # pattern -- the exception-handler and BaseHTTPMiddleware stubs are stricter than
    # slowapi's real, widely-used API actually requires (both calls are copied from
    # slowapi's own README).
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_middleware(AuditLogMiddleware, service_name=service_name)  # type: ignore[arg-type]
    warn_if_open_mode(service_name)
    return limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


__all__ = [
    "REQUEST_ID_HEADER",
    "wire_readiness_endpoint",
    "API_KEYS_ENV_VAR",
    "RATE_LIMIT_ENV_VAR",
    "REQUIRE_AUTH_ENV_VAR",
    "DEFAULT_KEY_ROLE",
    "ADMIN_ROLE",
    "require_api_key",
    "require_role",
    "require_any_role",
    "resolve_caller_role",
    "ANALYST_ROLE",
    "INVESTIGATOR_ROLE",
    "COMPLIANCE_OFFICER_ROLE",
    "PLATFORM_ROLES",
    "case_rate_limit",
    "CASE_RATE_LIMIT_ENV_VAR",
    "get_limiter",
    "score_rate_limit",
    "harden_app",
    "audit_log",
    "AuditLogMiddleware",
    "warn_if_open_mode",
    "render_metrics",
    "wire_metrics_endpoint",
    "record_custom_metric",
    "set_custom_gauge",
]
