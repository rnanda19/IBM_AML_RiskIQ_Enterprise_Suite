# Deployment Guide

Real, verified-where-marked instructions for running this platform's 5 scoring services. Anything not
marked verified is a documented recommendation, not a claim that it has been tested end-to-end in this
session.

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

Each service's `/health` (always unauthenticated) and, as of this session, `/metrics` (also
unauthenticated, Prometheus text format) are both safe to point a liveness probe / scrape target at
without a credential -- neither exposes transaction content, per `docs/security/THREAT_MODEL.md`.

## Running the real multi-service stack together

There is currently no root-level `docker-compose.yml` that brings up all 5 services at once -- each BP's
`docker-compose.yml` is independent (`src/docker/<bp>/docker-compose.yml`). To run several together,
start each independently; the port table above is now collision-free so this is safe to do for all 5.
Building a single root-level compose file that brings up all 5 as one stack is listed as a still-open
task from earlier in this project's history (Task #26) -- not yet done.

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

The Dockerfile hardening changes made this session (non-root user, HEALTHCHECK, BP4's port move) have
**not** been build-tested locally -- this sandbox has no Docker daemon available. They will be verified
for real the next time `docker-verify.yml` runs in CI after this work is pushed. If that run fails, the
CI log is the authoritative signal, not this document's description of the intended behavior.
