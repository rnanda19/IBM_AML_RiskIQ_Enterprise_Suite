# Scoring-to-Alert Integration

Architecture reference for the **End-to-End AML Workflow Integration** phase (2026-10-12): how a BP1-BP5
scoring result becomes a traceable, investigable alert in the Case Management Service. Read this
alongside `docs/architecture/INVESTIGATOR_WORKFLOW.md` (the case-lifecycle side, unchanged by this phase)
and `docs/security/RBAC.md` (the role matrix this integration reuses rather than extends).

## Why this exists

Before this phase, `POST /alerts` on the Case Management Service (added 2026-10-12, earlier same day)
existed but nothing called it automatically -- a scoring result from BP1-BP5 and a case-management alert
were two disconnected systems, and `ROADMAP.md` tracked that gap explicitly ("No automatic pipeline from a
BP1-BP5 scoring decision into a Case Management Service alert"). This phase closes it: each scoring
service's own `/score` route now decides, using its own real result, whether the outcome is alert-worthy,
and if so dispatches a real alert carrying full scoring provenance to the Case Management Service.

## Component map

```
BP1 /score (XGBoost, binary)      ─┐
BP2 /score (RandomForest, 5-class) ─┤
BP3 /score (rule, no model)        ─┼──> maybe_generate_and_dispatch_alert()  ──> dispatch_alert()
BP4 /score (XGBoost, binary)       ─┤         (casework/scoring_event.py)         (serving/_alert_dispatch.py)
BP5 /score (XGBoost, binary)      ─┘                                                      │
                                                                                            │ POST /alerts/ingest
                                                                                            v
                                                                            Case Management Service (:8005)
                                                                            casework/store.py: create_alert_idempotent()
                                                                                            │
                                                                                            v
                                                              existing case lifecycle (assign/note/evidence/
                                                              transition/escalate/close), RBAC-enforced,
                                                              audit hash-chain -- all unchanged by this phase
```

Two new modules do the real work; everything downstream of `POST /alerts/ingest` is the pre-existing,
already-tested case-management code path, untouched.

### `casework/scoring_event.py` -- the validated contract

`ScoringEvent` (a Pydantic model) is the one shape every BP's scoring result is normalized into before any
alert decision is made. It rejects a missing/empty `entity_ref`, a NaN/infinite `risk_score`, and an
unsupported `schema_version` -- `parse_scoring_event()` wraps Pydantic's `ValidationError` into
`ScoringEventValidationError`, which the dispatch path catches and treats as "skip silently, log once",
never an unhandled exception that would take down a `/score` response over a bad event.

`is_alert_worthy(risk_score, selected_threshold)` is a plain `>=` comparison; `classify_severity()` turns
the *ratio* of score to threshold into one of `medium`/`high`/`critical` via two configurable band
multipliers (`DEFAULT_HIGH_SEVERITY_RATIO=1.5`, `DEFAULT_CRITICAL_SEVERITY_RATIO=2.0`) -- a routing
convenience for investigators, never fed back into the model and never treated as a different kind of
evidence than the raw score itself.

`compute_idempotency_key(event)` is a SHA-256 hex digest over the event's *stable identity* fields
(business problem, entity/transaction ref, detection source, risk score, threshold, model name/sha) --
deliberately excluding `scoring_timestamp`, so a retry of the same real scoring decision (different
wall-clock time, same underlying facts) produces the same key every time. This is the single mechanism
that makes every other reliability guarantee below possible.

### Per-BP alert-worthiness: never a fabricated threshold

Each BP decides alert-worthiness using only its own real, already-saved validation artifact -- never a
hand-tuned number invented for this phase (the project's standing "no threshold is ever quietly tuned
toward a target verdict" rule):

| BP | What crosses the line | Source of the threshold |
|---|---|---|
| BP1 | `probability >= selected_threshold` | The real saved validation report's `selected_threshold` |
| BP2 | `confidence >= 1/len(CLASS_NAMES)` | The mathematically-derived chance baseline for a 5-class classifier -- BP2's real validation report has no saved threshold (`selected_threshold: null`) because it is a multiclass typology classifier (argmax), not a binary detector; inventing a confidence cutoff here would be exactly the kind of fabrication this project's conventions forbid, so the honest substitute is the one number that needs no tuning: random-chance baseline |
| BP3 | `near_train_flagged is True` | A real, precomputed graph-structural lookup (not a model) -- `risk_score`/`selected_threshold` are normalized to a fixed `1.0`/`1.0` so the same `is_alert_worthy()` function still applies; an account absent from the graph (`near_train_flagged is None`) is honestly "unknown", never alert-worthy by omission |
| BP4 | `probability >= selected_threshold` | The real saved validation report's `selected_threshold` |
| BP5 | `probability >= selected_threshold` | The real saved validation report's `selected_threshold` |

### `serving/_alert_dispatch.py` -- reliable delivery

`maybe_generate_and_dispatch_alert()` is the one function every BP's `/score` route calls. It builds a
`ScoringEvent`, checks alert-worthiness, and -- only if warranted -- calls `dispatch_alert()`. Every
failure mode is caught internally; this function **never raises**, so a case-management outage or a
malformed event can never turn into a failed `/score` response for the caller who only wanted a score.

`dispatch_alert()` implements the standard outbox pattern for at-least-once delivery without blocking the
caller on an unbounded retry loop:

1. A small, bounded number of fast inline attempts (default 2, 2s timeout, short backoff) against
   `POST {case_service_url}/alerts/ingest`.
2. **Non-retryable rejections** (`400`/`401`/`403`/`404`/`422`) stop immediately and are logged as a
   rejection, not retried -- a `401`/`403` specifically means this scoring service's own
   `AML_RISKIQ_CASE_SERVICE_API_KEY` is misconfigured or lacks an accepted role, which retrying can never
   fix (unlike a `429`/`5xx`, which is retried).
3. If every inline attempt fails for a retryable reason (timeout, connection error, `429`/`5xx`), the
   alert is appended to a durable, append-only JSON-Lines outbox file
   (`data/alert_outbox/<service_name>.outbox.jsonl`) and the function returns immediately -- the alert is
   never silently dropped, and `/score`'s own latency never turns into an unbounded spike waiting on a
   down dependency.
4. `replay_outbox()` (wrapped by `scripts/replay_alert_outbox.py`) is the explicitly-invoked, operator-run
   mechanism that drains the outbox once case-management is reachable again. It is safe to run more than
   once, including after a crash mid-replay, because of idempotency (next section).

### Idempotency: why a retry or a replay never duplicates an alert

Every alert this module builds carries its `idempotency_key`. `POST /alerts/ingest` calls
`store.create_alert_idempotent()`, which is backed by a real SQLite **partial `UNIQUE` index**
(`idx_alerts_idempotency_key ... WHERE idempotency_key IS NOT NULL`) -- not an application-level
check-then-insert, which would have a race window. A second `POST /alerts/ingest` with the same key
returns the existing alert and `duplicate: true` (HTTP 200) instead of creating a second row; a new key
creates a new alert (HTTP 201). This is what makes "a retry never creates a duplicate alert" a real,
database-enforced guarantee rather than a hope, and is exactly what `replay_outbox()` relies on to be safe
to run repeatedly.

### `POST /alerts/ingest` -- the one new Case Management Service route

Added to `case_management_service.py`, protected by the same `require_any_role(ANALYST_ROLE,
INVESTIGATOR_ROLE, COMPLIANCE_OFFICER_ROLE)` dependency `POST /alerts` already uses -- deliberately never
a new bespoke "service" role, so a scoring service's case-management API key is indistinguishable, from
an authorization standpoint, from an analyst's own key. A malformed body gets FastAPI's automatic `422`,
which the dispatch client already treats as non-retryable. Three observability primitives were added
alongside it: `alert_ingest_created_total` / `alert_ingest_duplicate_total` counters and an
`unresolved_alerts_total` gauge (refreshed on every alert creation, ingest, and status transition) --
exposed through the pre-existing generic `record_custom_metric()`/`set_custom_gauge()` primitives in
`_security.py`, on the same `/metrics` endpoint every other counter already uses. Per-request
latency/count for `/alerts/ingest` itself is covered for free by the pre-existing `AuditLogMiddleware` /
`wire_metrics_endpoint()`, which instruments every route including this new one -- no new code was needed
for that part of "observability."

## Failure modes (what happens when something goes wrong)

| Failure | What happens | Where it's visible |
|---|---|---|
| Scoring event fails validation (missing identifier, NaN score, bad schema version) | Logged once, skipped silently -- `/score`'s own response is unaffected | `aml_riskiq.alert_dispatch` logger, structured JSON line, `event: scoring_event_validation_failed` |
| Case Management Service unreachable (down, network partition) | 2 fast inline retries, then queued to the local outbox file | `event: alert_dispatch_exhausted_queued` log line; file appears under `data/alert_outbox/` |
| Case-management API key misconfigured/revoked (401/403) | Rejected immediately, not retried, outboxed for operator visibility | `event: alert_dispatch_attempt_failed` with `attempt: 1` then a rejection log |
| Duplicate scoring event (retry, or outbox replay) | Recognized by `idempotency_key`, no second alert created, `duplicate: true` returned | `alert_ingest_duplicate_total` counter increments |
| Case-management database unavailable at ingest time | `POST /alerts/ingest` itself fails -- treated as a transient failure by the dispatch client (5xx), retried then outboxed | Case-management's own logs; `alert_ingest_created_total` does not increment |

## What this phase deliberately does NOT do

- **No new ML model.** Every alert-worthiness decision uses an existing, already-validated model/rule
  artifact and its own saved threshold (or the principled BP2/BP3 substitutes above) -- see
  "Per-BP alert-worthiness" above.
- **No change to case-management's own lifecycle, RBAC, or audit trail.** `/alerts/ingest` reuses the
  exact same role check, the exact same `AlertStore`, and produces alerts that go through the identical
  assign/note/evidence/transition/escalate/close path as one created by `POST /alerts` -- verified by
  `tests/integration/case_management/test_case_management_service.py`'s
  `test_ingest_created_alert_has_full_investigation_lifecycle_available`.
- **No claim that a model's score is proof of laundering.** A score and threshold decide whether an alert
  is *generated*; whether it is substantiated is an investigation decision made by a human through the
  existing case lifecycle -- this module only ever writes `status=new`, `generation_source=
  automated_scoring`, never a pre-populated verdict.

## Verification evidence

- **Unit level**: `tests/unit/test_scoring_event.py` (validation, severity routing, idempotency-key
  determinism), `tests/unit/test_alert_dispatch.py` (dispatch success/duplicate/retry/outbox/rejection,
  `maybe_generate_and_dispatch_alert()`'s every skip path, `replay_outbox()`), `tests/unit/
  test_replay_alert_outbox.py` (the CLI wrapper).
- **Integration level**: each BP's own test file gained wiring tests (`test_score_endpoint_with_entity_ref
  _attempts_alert_dispatch` and siblings); `tests/integration/case_management/
  test_case_management_service.py` gained 10+ tests for `/alerts/ingest` specifically, including structured
  audit-log and full-lifecycle verification.
- **End-to-end, in-process (no containers)**: `tests/integration/end_to_end/test_scoring_alert_e2e.py` runs
  the real FastAPI apps over a real `httpx` transport (Starlette's own sync `TestClient` transport, not a
  mock) -- normal scoring, threshold-triggered alerts, duplicate suppression, a simulated case-management
  outage with retry-then-outbox, and an authorization-failure scenario.
- **End-to-end, real containers**: `.github/workflows/docker-verify.yml`'s `integrated-workflow` job builds
  and brings up the real `case-management` + `bp3-network-graph-intelligence` Docker containers together
  (via the root `docker-compose.yml`) and exercises a real scoring-to-alert round trip over the real
  network between them, using a real, committed account key from BP3's own lookup table -- see that job's
  own comments for why BP3 (a deterministic rule) rather than a probabilistic BP was chosen for this
  specific check.

As of this writing, the `integrated-workflow` CI job has been written and locally YAML-validated but not
yet observed passing in GitHub Actions (Docker is unavailable in this development environment) -- confirm
its status on the repository's Actions tab before treating the real-container path as verified.
