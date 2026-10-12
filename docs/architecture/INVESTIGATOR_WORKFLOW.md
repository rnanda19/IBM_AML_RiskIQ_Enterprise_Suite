# Investigator Workflow -- Design and Honest Scope

Addresses the external benchmark review's Prompt 5 ("connect detection to auditable case
management"). Implemented as a new package, `src/aml_riskiq/casework/`, in an earlier session, and
**wired into a real, RBAC-protected, persisted REST API** --
`src/aml_riskiq/serving/case_management_service.py` -- in the 2026-10-12 RBAC/case-management phase.
This document now describes both: the package (design/foundation) and the service (what actually runs).
See `docs/security/RBAC.md` for the service's permission matrix and
`docs/security/THREAT_MODEL.md` for its threat-model entry.

## What exists now

- **`alert_schema.py`**: a versioned `Alert` Pydantic model (schema_version, alert_id, entity
  reference, business problem, detection source, risk score, threshold, model name/fingerprint,
  timestamps, reason codes, status, audit history) and `CaseStatus` enum. `alert_from_score_response()`
  builds an `Alert` from the exact response shape each BP1/BP2/BP4/BP5 scoring service's
  `score_transaction()` already returns (`probability`/`threshold`/`champion_name`/`dataset_variant`),
  or BP3's rule-equivalent (`rule_score`).
- **`case_lifecycle.py`**: a conservative state machine (`NEW -> ASSIGNED -> UNDER_REVIEW ->
  ESCALATED -> CLOSED`, with `UNRESOLVED` as a side-branch that can be re-assigned) --
  `transition()` returns a new `Alert` with an appended `CaseEvent`, never mutates in place, and
  raises `InvalidTransitionError` on any transition outside the allowed graph.
- **`dedup.py`**: `cluster_alerts()` groups alerts referencing the same entity within a configurable
  time window (for an investigator to review together -- NOT a claim they're the same detection);
  `exact_duplicates()` separately catches true same-detection duplicates (identical entity +
  transaction + BP + detection source + threshold).
- **`reconciliation.py`**: `build_reconciliation_report()` -- the counts Prompt 5 asked for
  (transactions evaluated, alerts generated, deduplicated, cases by status), with an internal
  self-check that every alert is accounted for exactly once.
- **`evidence_export.py`**: `export_evidence()` -- one JSON-serializable bundle per alert: subject,
  detection details, model provenance, timestamps, full case history. Satisfies Prompt 5's acceptance
  criterion ("an independent reviewer must be able to start with a sample alert and reconstruct why it
  was created... and how it was handled afterward") for any `Alert` object, real or test.

18 original tests (`tests/unit/test_casework.py`), all synthetic fixtures built in the test file itself.
The 2026-10-12 phase added: `prev_event_hash`/`event_hash` on every `CaseEvent` (a SHA-256 hash chain) and
`verify_history_integrity()`, plus `assign()`, `add_note()`, `add_evidence()` on `Alert` (12 more tests in
`test_casework.py`); a full SQLite-backed `AlertStore` persistence layer, `src/aml_riskiq/casework/store.py`
(20 tests, `tests/unit/test_casework_store.py`); and the REST API described below (43 tests,
`tests/integration/case_management/test_case_management_service.py`). flake8/black/isort/mypy/bandit all
clean on the new code; 0 regressions in the pre-existing suite.

## What exists now -- the REST API (added 2026-10-12)

`src/aml_riskiq/serving/case_management_service.py` is a real, standalone FastAPI service (not a
notebook, not a script) exposing the `casework` package as 12 routes: create/list/get alerts, assign,
add a note, add evidence, export evidence, transition status, verify integrity, and a reconciliation
report, plus `/health` and `/metrics`. Every non-public route is RBAC-protected (`analyst`,
`investigator`, `compliance_officer`, `admin` -- see `docs/security/RBAC.md` for the full matrix) using
the same `_security.py` auth module every BP1-BP5 scoring service already shares, so there is exactly one
auth module in the whole platform, not a second one invented for this service. It has its own Dockerfile
(`src/docker/case_management/`), its own rate-limit budget (`AML_RISKIQ_CASE_RATE_LIMIT`), and its own CI
job in `.github/workflows/docker-verify.yml` (build, fail-closed-auth check, a live create-then-reject
unauthenticated-write check against the running container).

## What does NOT exist yet (disclosed, not hidden)

- **Not wired into any BP1-BP5 scoring service.** None of BP1/BP2/BP4/BP5's `/score` routes construct an
  `Alert` automatically today -- the Case Management Service's `POST /alerts` still requires a caller
  (human or script) to submit the alert; there is no automatic pipeline from a scoring decision straight
  into a case. Building that pipeline is real future work.
- **No real case data.** Every example in this project's tests (unit and integration) is synthetic,
  built directly in the test files. The service has never been pointed at a real scored transaction.
- **A real architecture gap this work surfaced, still open**: none of the 5 scoring services' `/score`
  requests or responses carry a transaction or account identifier today -- each takes only raw feature
  values and returns only a probability (see `alert_schema.py`'s module docstring). `alert_from_score_response()`
  requires the caller to supply `entity_ref` themselves because the service has no way to supply one.
  Fixing this at the service layer (adding an identifier field to each BP's request/response schema) is
  a prerequisite for an automatic scoring-to-case pipeline, and has not been done.
- **No identity directory.** The Case Management Service's `actor` fields are API-key fingerprints, not
  named users -- see `docs/security/RBAC.md`'s "Identity model" section.
- **RBAC still does not reach BP1-BP5's `/score` routes.** `require_role()`/`require_any_role()` now
  genuinely protect the Case Management Service (this is what closed `docs/audit/DEFECT_REGISTER.md`'s
  DEF-003 for this surface), but the 5 scoring services still have only `/health` and a single-tier
  `/score` -- there is still no second route on any of them for a role distinction to protect.
- **Tamper-evidence, not tamper-proofing.** The hash chain over `CaseEvent.history` detects an
  out-of-band edit on reload; it cannot prove the very first event in a chain was the true original. See
  `SECURITY.md`'s "Case management audit trail" section.
- **SQLite is not cluster-aware.** The persistence layer is a single on-disk file, correct for this
  platform's one-process-per-container shape; a multi-replica deployment of this service would need a
  real client-server database instead.

## Why the package came before the route (historical note)

The `casework` package was deliberately shipped as a tested foundation, not a route, in the batch that
first built it: wiring it into a live FastAPI service, adding a persistent store, and protecting it with
RBAC was substantially more surface area than that batch's work should have covered alongside everything
else changed at the time. The 2026-10-12 RBAC/case-management phase is that deferred work, done as its
own scoped batch once the foundation existed to build it on.

## See it run

[`CASEWORK_WORKED_EXAMPLE.md`](CASEWORK_WORKED_EXAMPLE.md) is a real, captured transcript of the
`casework` package's own functions run end to end on one synthetic alert -- `/score`-shaped input through
investigator transitions to a JSON audit-reconstruction bundle. It demonstrates the package's plumbing
directly (useful for understanding the data model), not the live service. For the live service, exercise
`src/aml_riskiq/serving/case_management_service.py` itself (see `docs/deployment/DEPLOYMENT_GUIDE.md`) or
read `tests/integration/case_management/test_case_management_service.py`, which runs it end to end
including real RBAC enforcement.
