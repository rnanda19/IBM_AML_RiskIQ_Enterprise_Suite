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
import os
import secrets
import sys
import threading
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

API_KEYS_ENV_VAR = "AML_RISKIQ_API_KEYS"
RATE_LIMIT_ENV_VAR = "AML_RISKIQ_SCORE_RATE_LIMIT"
REQUIRE_AUTH_ENV_VAR = "AML_RISKIQ_REQUIRE_AUTH"
DEFAULT_SCORE_RATE_LIMIT = "60/minute"

_audit_logger = logging.getLogger("aml_riskiq.audit")
if not _audit_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False


DEFAULT_KEY_ROLE = "service"
ADMIN_ROLE = "admin"


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


def require_role(role: str) -> Callable[[str | None], str]:
    """Returns a FastAPI dependency requiring a valid API key whose configured role equals
    `role`, or ADMIN_ROLE (admin satisfies every role check). In open mode it is a no-op,
    identical to require_api_key -- role checks only apply once AML_RISKIQ_API_KEYS is set.
    403 for a valid key with the wrong role (distinct from require_api_key's 401 for a
    missing/invalid key, so a caller can tell "not authenticated" from "authenticated, wrong
    permission")."""

    def _dependency(x_api_key: str | None = Header(default=None)) -> str:
        configured = _configured_api_keys_with_roles()
        if configured is None:
            return "anonymous"
        if x_api_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header.")
        matched_role: str | None = None
        for candidate_key, candidate_role in configured.items():
            if secrets.compare_digest(x_api_key, candidate_key):
                matched_role = candidate_role
                break
        if matched_role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
        if matched_role != role and matched_role != ADMIN_ROLE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Key has role '{matched_role}', this route requires '{role}'.",
            )
        return _key_fingerprint(x_api_key)

    return _dependency


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


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emits one structured JSON audit line per request, for every route (health checks
    included, so a gap in traffic is visible too) -- regardless of whether auth or rate
    limiting allowed, rejected, or throttled the request."""

    def __init__(self, app: FastAPI, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.monotonic()
        caller_key = request.headers.get("x-api-key")
        caller_id = _key_fingerprint(caller_key) if caller_key else "anonymous"
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
            )
            _record_metric(self._service_name, request.method, request.url.path, status_code, elapsed_ms)
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
    return "\n".join(lines) + "\n"


def wire_metrics_endpoint(app: FastAPI) -> None:
    """Mounts GET /metrics on the given app, deliberately unauthenticated (see module
    docstring section 6). Call once, after harden_app()."""

    @app.get("/metrics")
    def _metrics() -> Response:
        return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")


def audit_log(
    *,
    service_name: str,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
    client_ip: str,
    caller_id: str,
) -> None:
    """Writes one structured audit record. Pulled out of the middleware as its own function
    so a route handler that needs to log something ad hoc (not just the generic request/
    response shape) can reuse the exact same record shape and logger."""
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
    }
    _audit_logger.info(_json.dumps(record))


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
    "API_KEYS_ENV_VAR",
    "RATE_LIMIT_ENV_VAR",
    "REQUIRE_AUTH_ENV_VAR",
    "DEFAULT_KEY_ROLE",
    "ADMIN_ROLE",
    "require_api_key",
    "require_role",
    "get_limiter",
    "score_rate_limit",
    "harden_app",
    "audit_log",
    "AuditLogMiddleware",
    "warn_if_open_mode",
    "render_metrics",
    "wire_metrics_endpoint",
]
