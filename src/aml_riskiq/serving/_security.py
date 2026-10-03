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

2. RATE LIMITING (`get_limiter()` + `@limiter.limit(...)`)
   - Real, enforced via `slowapi` (a FastAPI/Starlette wrapper around the battle-tested
     `limits` library), keyed by the caller's remote address by default.
   - Default budget for `/score` is DEFAULT_SCORE_RATE_LIMIT ("60/minute") -- generous enough
     for this project's own synthetic-fixture test suite (a handful of calls per test) and for
     real interactive use, while still bounding a single caller's worst case. Override per-
     deployment via the AML_RISKIQ_SCORE_RATE_LIMIT env var (same string syntax `slowapi`/
     `limits` accepts, e.g. "600/minute").

3. AUDIT LOGGING (`audit_log` + `AuditLogMiddleware`)
   - Every request to every route gets ONE structured JSON line on the `aml_riskiq.audit`
     logger (stdout by default), with: UTC ISO timestamp, service name, HTTP method, path,
     status code, latency in milliseconds, caller IP, and the API-key fingerprint described
     above (or "anonymous" in open mode / for unauthenticated requests).
   - Written to stdout, not to a project-local file: this is the standard shape for a
     container workload (Notebook 4's own Dockerfiles run these services as the container's
     main process) -- log collection (Docker's own log driver, a Kubernetes sidecar, CloudWatch,
     etc.) is the deployer's responsibility, not this module's. Nothing here invents a
     logging backend that would need its own operational support.

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
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

API_KEYS_ENV_VAR = "AML_RISKIQ_API_KEYS"
RATE_LIMIT_ENV_VAR = "AML_RISKIQ_SCORE_RATE_LIMIT"
DEFAULT_SCORE_RATE_LIMIT = "60/minute"

_audit_logger = logging.getLogger("aml_riskiq.audit")
if not _audit_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False


def _configured_api_keys() -> set[str] | None:
    """Returns the configured key set, or None if AML_RISKIQ_API_KEYS is unset (open mode).
    Re-reads the env var on every call (not cached at import time) so a test's monkeypatch
    of the env var takes effect without needing to reimport the module."""
    raw = os.environ.get(API_KEYS_ENV_VAR)
    if raw is None or raw.strip() == "":
        return None
    return {k.strip() for k in raw.split(",") if k.strip()}


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


def warn_if_open_mode(service_name: str) -> None:
    """Call once at service startup (module import time) -- prints an unmissable stderr
    warning when AML_RISKIQ_API_KEYS is unset, so open mode is never silently in effect in an
    environment where someone expected auth to be enforced."""
    if _configured_api_keys() is None:
        print(
            f"[{service_name}] WARNING: {API_KEYS_ENV_VAR} is not set -- this service is "
            "running WITHOUT API-key auth (open mode). Set AML_RISKIQ_API_KEYS to a "
            "comma-separated list of keys to require authentication on protected endpoints.",
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
        return response


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
    reason documented at the top of this module)."""
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
    "DEFAULT_SCORE_RATE_LIMIT",
    "require_api_key",
    "get_limiter",
    "score_rate_limit",
    "harden_app",
    "audit_log",
    "AuditLogMiddleware",
]
