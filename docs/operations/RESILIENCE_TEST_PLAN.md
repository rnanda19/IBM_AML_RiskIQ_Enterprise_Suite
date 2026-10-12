# Resilience Test Plan

Added 2026-10-12 (Improvement 3, production-readiness pass). Scope: this document states,
for each resilience property this platform's own architecture can reasonably be expected to
have, what is automated and passing today (with the exact test to point at), what is
automated against real infrastructure in CI (not this local sandbox), and what genuinely
needs live infrastructure this development environment does not have and is therefore
**not** claimed as verified. Nothing below should be read as a claim that this platform has
been chaos-tested in a real production environment -- it has not. It is a portfolio/research
demonstration (see `README.md`'s own framing); this plan is the honest, current state of its
resilience evidence, not a certification.

## 1. Duplicate-event handling -- VERIFIED, multiple levels

A retry, a replay, or a genuine duplicate submission of the same scoring event must never
create a second case for the same real event.

- **Mechanism**: every automated alert carries a deterministic `idempotency_key`
  (`casework/scoring_event.py`'s `compute_idempotency_key`), enforced by a real SQLite
  `UNIQUE` index (`store.py`'s `idx_alerts_idempotency_key`), not an application-level check
  that could race.
- **Unit level**: `tests/unit/test_casework_store.py` (idempotent insert returns the
  original alert, not a second row) and `tests/unit/test_scoring_event.py` (idempotency-key
  determinism).
- **Integration level**: `tests/integration/case_management/test_case_management_service.py::
  test_ingest_same_idempotency_key_returns_200_same_alert_id_not_duplicated`.
- **Real multi-container level**: `.github/workflows/docker-verify.yml`'s
  `integrated-workflow` job's "Verify re-submitting the identical account does not create a
  duplicate alert" step -- a real repeated HTTP call against real running containers, not
  mocked. Confirmed passing in CI for commit `4c134f1` (see `ROADMAP.md`'s "CI re-verified on
  commit 4c134f1" entry).

## 2. Temporary dependency failure + recovery after failure -- VERIFIED, including a real-network test

A scoring service's call to the Case Management Service failing (network blip, the
Case Management Service briefly down) must not drop the alert or block the caller's `/score`
response indefinitely.

- **Mechanism**: the outbox pattern (`src/aml_riskiq/serving/_alert_dispatch.py`) -- a small,
  bounded number of fast inline retry attempts, then a durable local JSON-Lines outbox file
  if all of them fail, never an unbounded retry loop blocking `/score`. A separate,
  explicitly-invoked `scripts/replay_alert_outbox.py` delivers queued alerts once the
  dependency is reachable again, safely re-runnable (idempotency key) if a replay itself is
  interrupted partway through.
- **Unit level**: `tests/unit/test_alert_dispatch.py` (retry/backoff/outbox-on-exhaustion
  behavior against a stubbed client) and `tests/unit/test_replay_alert_outbox.py`, including
  `test_real_replay_outbox_against_unreachable_service_leaves_file_queued_and_exits_1` -- a
  REAL network call against a genuinely unreachable address (not a mock), confirming the
  record is honestly left queued (not falsely marked delivered) and the script's exit code
  reflects that.
- **What this does not cover**: a real Case Management Service outage lasting long enough to
  require operator intervention (disk filling with outbox files, manual outbox inspection)
  has no automated test here -- that is an operational runbook item, not yet written.

## 3. Interrupted / partial processing -- VERIFIED this pass (new test)

A crash, exception, or killed process partway through a multi-statement case-creation write
must leave no partial row behind -- a half-written case is strictly worse than a rejected one.

- **Mechanism**: `store.py`'s `_connect()` context manager wraps every public method's SQL
  statements in one transaction, committing only at the very end and rolling back on any
  exception (already existed; not new this pass).
- **New test added this pass**: `tests/unit/test_casework_store.py::
  test_create_alert_rolls_back_fully_when_interrupted_partway_through` -- builds a real Alert
  with two real, hash-chained history events (via `case_lifecycle.transition()`), injects a
  fault (a real `RuntimeError`) partway through the second event's insert, and confirms BOTH
  that `create_alert()` actually raises AND that the alert row itself is gone afterward (not
  just the second event) -- proving the first, already-"successful" insert inside the same
  transaction was rolled back too, not only the one that raised.

## 4. Service restart recovery -- VERIFIED this pass (new test), within this architecture's real limits

Data written before a restart must still be there (and still verifiably untampered) after one.

- **Mechanism**: `AlertStore` opens a fresh SQLite connection per call and commits before
  returning (see `_connect()`) -- there is no in-memory state that a restart would lose
  (already existed; not new this pass). The real durability guarantee this depends on is
  SQLite's own commit-before-return behavior plus the host filesystem's durability, both
  standard, not platform-invented.
- **New test added this pass**: `tests/unit/test_casework_store.py::
  test_data_survives_a_fresh_store_instance_against_the_same_db_file` -- writes an alert,
  an assignment, and a note through one `AlertStore` instance, discards it, then opens a
  SECOND, independent `AlertStore` instance against the same on-disk file (the closest
  simulation of "a new container process starts against the same persistent volume" this
  sandbox can do without a live Docker daemon) and confirms every field, including the
  hash-chain integrity check, reads back correctly.
- **What this does not cover** (needs live infrastructure this sandbox does not have -- no
  Docker daemon, see `DEPLOYMENT_GUIDE.md`'s own disclosed limitation): an actual
  `docker restart` / container crash-and-recreate cycle, verifying the bind-mounted volume
  survives a real container lifecycle event (not just a new Python object in the same
  process), and confirming `AML_RISKIQ_REQUIRE_AUTH`'s fail-closed startup gate behaves
  correctly across a real restart with a misconfigured environment. This is the next real
  verification step once a Docker-capable environment is available -- `docker-verify.yml`'s
  existing jobs already prove container startup/health from cold, which is the adjacent,
  already-covered case.

## 5. Explicitly not attempted here (would need infrastructure this platform does not run)

- **Real network partition / packet loss between containers**: the outbox pattern (section 2)
  is designed to tolerate this, but there is no chaos-engineering harness (e.g. Toxiproxy,
  `tc netem`) wired into CI to inject it for real.
- **Disk-full mid-write**: SQLite's own transaction semantics (section 3) should make this
  safe in principle (a failed write rolls back), but it has not been forced and observed.
- **Multi-replica / concurrent-writer SQLite contention under real load**: `store.py`'s own
  module docstring already discloses this platform's one-process-per-container deployment
  shape is not cluster-aware; load-testing concurrent writers is out of scope for this
  pass.
- **A dedicated secret-scanning pre-commit/CI hook** (e.g. `gitleaks`, `detect-secrets`): not
  yet added -- see `SECRETS_MANAGEMENT.md`'s 2026-10-12 verification section and
  `ROADMAP.md` for this as a disclosed, tracked gap.

## Summary table

| Property | Mechanism exists | Automated test | Real-infra evidence |
|---|---|---|---|
| Duplicate-event handling | Yes (idempotency key + UNIQUE index) | Yes (unit + integration) | Yes (real multi-container CI job) |
| Dependency-failure recovery | Yes (outbox pattern) | Yes, incl. a real-network test | Partial (not a sustained-outage drill) |
| Interrupted-write atomicity | Yes (SQLite transaction) | Yes (new this pass) | No live-infra fault injection |
| Service-restart recovery | Yes (stateless-connection design) | Yes (new this pass, process-level) | No (needs a Docker daemon; not available here) |
| Network partition / disk-full | Design-compatible, unverified | No | No |
