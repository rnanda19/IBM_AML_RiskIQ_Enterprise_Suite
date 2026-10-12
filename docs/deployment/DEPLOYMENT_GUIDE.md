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

## Running the real multi-service stack together (added 2026-10-12)

A root-level `docker-compose.yml` now brings up all 6 services together, wired so each BP can reach
case-management as `http://case-management:8005` via Compose's own service-name DNS -- no manual network
config beyond the default bridge network Compose creates for this file. Each BP's
`depends_on: case-management: condition: service_healthy` means it only starts once case-management's own
Docker-native `HEALTHCHECK` reports healthy.

```bash
# from the repository root
mkdir -p data/case_management data/alert_outbox && chmod -R 777 data   # see note below
docker compose up --build
# or bring up a subset, e.g. just case-management + one BP:
docker compose up --build case-management bp1-transaction-monitoring
```

**The `mkdir`/`chmod` above matters on a fresh checkout.** `./data/case_management` and
`./data/alert_outbox` do not exist yet, and Docker auto-creates a missing bind-mount source directory as
root, mode `0755`. Every image in this stack drops to a non-root user (`USER app`/`USER appuser` in each
Dockerfile), which cannot write into a root-owned, group/other-unwritable directory -- case-management's
own SQLite `AlertStore` is opened eagerly at import time (`casework/store.py`), so a `PermissionError`
there crashes the process before it can ever serve `/health`, its `HEALTHCHECK` never reports healthy, and
`docker compose up` fails outright (bp1-5 all `depends_on: case-management: condition: service_healthy`).
This is exactly what the `integrated-workflow` CI job hit the first time it ran for real -- see that job's
own "Prepare writable bind-mount data directories" step for the same fix applied in CI.

Every `*_KEY`/`*_KEYS` environment variable in this file defaults to a committed, non-secret,
**local-development-only** placeholder (e.g. `CASE_SERVICE_CLIENT_KEY`, `BP1_API_KEYS`) -- override every
one of them via a real `.env` file or your secrets manager before running this anywhere reachable by
anyone but you; see the file's own header comment for the full list and the authorization model (each
BP's own `AML_RISKIQ_API_KEYS` is independent of every other service's; the case-service client key must
be one of the keys case-management's own `AML_RISKIQ_API_KEYS` maps to `analyst`/`investigator`/
`compliance_officer`, never a bespoke "service" role).

Each BP also mounts `./data/alert_outbox` -- if case-management is ever unreachable, a BP's attempted
alert dispatch queues there instead of being lost (see `docs/architecture/SCORING_ALERT_INTEGRATION.md`'s
"Failure modes" table). Drain it once case-management is reachable again:

```bash
python scripts/replay_alert_outbox.py --all
# or target one service specifically:
python scripts/replay_alert_outbox.py --service bp1_scoring_service
```

Exit code is `0` only if nothing is left queued afterward -- safe to wire into a cron job or a CI step
that should fail loudly on a persistent outage. This root `docker-compose.yml` is **additional to**, not a
replacement for, each service's own `src/docker/<bp-or-service>/docker-compose.yml` (those remain how
`docker-verify.yml`'s existing per-service CI jobs build and smoke-test one service in isolation).
`.github/workflows/docker-verify.yml`'s `integrated-workflow` job is what proves this root compose file
end to end in CI -- see `docs/architecture/SCORING_ALERT_INTEGRATION.md`'s "Verification evidence"
section for exactly what it checks, and this document's own closing section for its current
not-yet-observed-passing status.

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

**Also not yet verified (2026-10-12, End-to-End AML Workflow Integration)**: the root-level
`docker-compose.yml` and the `integrated-workflow` CI job described above are YAML-valid and reviewed
against the real request/response shapes of every endpoint they call, but have not been run with a real
Docker daemon in this development environment either (confirmed: `docker` is not on `PATH`, and there is
no disk space available to install supporting ML libraries to verify model inference locally as an
alternative check). Their first real GitHub Actions run did surface a real bug -- the bind-mount
permission issue documented above -- which is now fixed in both `docker-compose.yml`'s own consumer (the
`integrated-workflow` job) and this guide; that fix has not yet been observed passing in a fresh CI run.
Confirm the result on the repository's Actions tab before treating the integrated multi-container
workflow as verified.
