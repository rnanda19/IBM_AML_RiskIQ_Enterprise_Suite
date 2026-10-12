# Deployment Guide

Real, verified-where-marked instructions for running this platform's 5 scoring services plus the Case
Management Service (added 2026-10-12). Anything not marked verified is a documented recommendation, not a
claim that it has been tested end-to-end in this session.

## Per-service Docker deployment (same pattern for all 5 services)

```bash
# from the repository root
docker compose -f src/docker/bp1_transaction_monitoring_detection/docker-compose.yml up --build
```
Ports (all now unique -- the BP2/BP4 8001 collision was fixed this session):

| BP | Port | Status |
|---|---|---|
| BP1 | 8000 | Build+run/health wired into CI (`docker-verify.yml`) |
| BP2 | 8001 | Build+run/health wired into CI; real artifact regenerated 2026-10-12 (DEF-001 resolved, `docs/audit/DEFECT_REGISTER.md`) |
| BP3 | 8003 | Build+run/health wired into CI; real lookup artifact generated 2026-10-12 (DEF-002 resolved) |
| BP4 | 8004 | Build+run/health wired into CI; port changed from 8001 this session to resolve a real collision with BP2 |
| BP5 | 8002 | Build+run/health wired into CI |
| BP6 | n/a | One-shot batch job, no exposed port, not a long-running service |
| Case Management | 8005 | Build+run/health wired into CI (`docker-verify.yml`'s `case-management` job); RBAC-protected -- see `docs/security/RBAC.md` |

```bash
# Case Management Service -- same pattern, own compose file, own port
docker compose -f src/docker/case_management/docker-compose.yml up --build
```

## Production configuration

All 5 scoring Dockerfiles bake in `AML_RISKIQ_REQUIRE_AUTH=true` -- a container built from this repo's own
Dockerfiles refuses to start without an API key by default. Running a service directly from source
(`uvicorn ...` with no Docker) still defaults to the open, friction-free local-dev posture documented in
`SECURITY.md` unless you set these yourself -- that source-level default is intentional, not an oversight
(see `_security.py`'s own header comment):

```bash
AML_RISKIQ_API_KEYS=service:a-real-random-key-here       # comma-separated; "role:key" or bare "key"
AML_RISKIQ_REQUIRE_AUTH=true                              # added this session -- refuses to start open
AML_RISKIQ_SCORE_RATE_LIMIT=60/minute                     # override the default if needed
```

Each service's `/health` (always unauthenticated) and `/metrics` (also unauthenticated, Prometheus text
format) are both safe to point a liveness probe / scrape target at without a credential -- neither
exposes transaction content, per `docs/security/THREAT_MODEL.md`.

### Case Management Service -- role configuration (added 2026-10-12)

The Case Management Service shares the same `_security.py` auth module and the same
`AML_RISKIQ_API_KEYS`/`AML_RISKIQ_REQUIRE_AUTH` environment variables, but it is the first service in the
platform where the role prefix actually matters -- configure at least one key per role you need:

```bash
AML_RISKIQ_API_KEYS=analyst:k-analyst,investigator:k-investigator,compliance_officer:k-compliance,admin:k-admin
AML_RISKIQ_REQUIRE_AUTH=true
AML_RISKIQ_CASE_RATE_LIMIT=120/minute                     # independent of AML_RISKIQ_SCORE_RATE_LIMIT
AML_RISKIQ_CASE_DB_PATH=/app/data/case_management/casework.db   # override the SQLite file location
```

**Compliance-only transition rule**: `POST /alerts/{id}/transition` accepts `investigator` or
`compliance_officer` at the route level, but transitioning a case to `escalated` or `closed` specifically
requires `compliance_officer` (or `admin`) -- an `investigator` key gets a 403 naming the mismatch only
when the request body's `to_status` is one of those two values. See `docs/security/RBAC.md`'s "Why
`/transition` isn't one static role check" section for why this one route needs a body-dependent check
instead of a single `Depends()` gate like every other route.

The SQLite database file (`data/case_management/casework.db` by default) is created automatically on
first write and is gitignored -- see `data/case_management/README.md`. It is a single on-disk file, so a
multi-replica deployment of this service needs a real client-server database instead (documented
limitation, not yet built).

## Running the real multi-service stack together

There is currently no root-level `docker-compose.yml` that brings up all 6 services (5 scoring + Case
Management) at once -- each one's `docker-compose.yml` is independent
(`src/docker/<bp-or-service>/docker-compose.yml`). To run several together, start each independently; the
port table above is collision-free so this is safe to do for all 6. Building a single root-level compose
file that brings up all of them as one stack is listed as a still-open task from earlier in this
project's history (Task #26) -- not yet done.

## Startup failure modes to expect

- **BP2 and BP3's previous known-broken startup failures (DEF-001/DEF-002) were fixed 2026-10-12** via
  real notebook re-runs that regenerated their missing artifacts -- see `docs/audit/DEFECT_REGISTER.md` for
  the resolution evidence. If you still see these fail, you are likely on a commit from before that fix.
- **Container refuses to start with no API key**: expected -- `AML_RISKIQ_REQUIRE_AUTH=true` is baked into
  every scoring Dockerfile. Set `AML_RISKIQ_API_KEYS` (see Production configuration above).
- **Any service**: `FileNotFoundError` for a validation-report JSON or model artifact means the image was
  built from a stale `COPY` path -- see `scripts/check_docker_copy_paths.py`, which is wired into CI
  specifically to catch this class of bug before it reaches a running container.

## Reproducing CI's own verification locally

```bash
docker build -f src/docker/bp1_transaction_monitoring_detection/Dockerfile -t bp1-scoring .
docker run -d --name bp1 -p 8000:8000 bp1-scoring
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/metrics
docker logs bp1   # if either curl fails
```

This mirrors exactly what `.github/workflows/docker-verify.yml` runs for BP1/BP4/BP5.

## Not yet verified in this session

The Dockerfile hardening changes made in an earlier session (non-root user, HEALTHCHECK, BP4's port move)
and the brand-new Case Management Service Dockerfile added 2026-10-12 have **not** been build-tested
locally -- this sandbox has no Docker daemon available. All of it will be verified for real the next time
`docker-verify.yml` runs in CI after this work is pushed, including the case-management job's own
live-container check (create an alert with an admin key, then confirm an unauthenticated write is
rejected with 401). If that run fails, the CI log is the authoritative signal, not this document's
description of the intended behavior.
