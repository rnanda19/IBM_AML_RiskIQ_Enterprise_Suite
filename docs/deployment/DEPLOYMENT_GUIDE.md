# Deployment Guide

Real, verified-where-marked instructions for running this platform's 5 scoring services. Anything not
marked verified is a documented recommendation, not a claim that it has been tested end-to-end in this
session.

## Per-service Docker deployment (verified pattern for BP1/BP4/BP5; BP2/BP3 currently broken, see below)

```bash
# from the repository root
docker compose -f src/docker/bp1_transaction_monitoring_detection/docker-compose.yml up --build
```
Ports (all now unique -- the BP2/BP4 8001 collision was fixed this session):

| BP | Port | Status |
|---|---|---|
| BP1 | 8000 | Build+run verified in CI (`docker-verify.yml`) |
| BP2 | 8001 | **Known broken** -- container starts then crashes (DEF-001, `docs/audit/DEFECT_REGISTER.md`) |
| BP3 | 8003 | **Known broken** -- missing required artifact (DEF-002) |
| BP4 | 8004 | Build+run verified in CI; port changed from 8001 this session to resolve a real collision with BP2 |
| BP5 | 8002 | Build+run verified in CI |
| BP6 | n/a | One-shot batch job, no exposed port, not a long-running service |

## Production configuration (recommended, not yet the default)

Set these environment variables for any non-local deployment -- left unset, every service below defaults
to the friction-free local-dev posture documented in `SECURITY.md`:

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
start each independently; the port table above is now collision-free so this is safe to do for
BP1/BP4/BP5 (BP2/BP3 will still fail to start regardless, until their real artifacts are regenerated).
Building a single root-level compose file that brings up all 5 as one stack is listed as a still-open
task from earlier in this project's history (Task #26) -- not yet done.

## Startup failure modes to expect

- **BP2**: container builds, starts, then the uvicorn worker crashes with a `KeyError` within seconds of
  startup (DEF-001). This is a known, disclosed defect, not a deployment misconfiguration -- do not spend
  time debugging your environment for this one.
- **BP3**: container builds, starts, then fails with `FileNotFoundError` for the missing lookup Parquet
  (DEF-002). Same -- known, disclosed, not a deployment issue.
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
