# Investigator Workflow -- Design and Honest Scope

Addresses the external benchmark review's Prompt 5 ("connect detection to auditable case
management"). Implemented as a new package, `src/aml_riskiq/casework/`, this session.

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

18 new tests (`tests/unit/test_casework.py`), all synthetic fixtures built in the test file itself --
95/95 total project tests passing; flake8/black/isort/mypy/bandit all clean on the new code.

## What does NOT exist yet (disclosed, not hidden)

- **Not wired into any live scoring service.** None of BP1/BP2/BP4/BP5's `/score` routes construct an
  `Alert` today -- this package operates on `Alert` objects a caller builds or passes in. Wiring it in
  is real future work (and would need `require_role()` from `_security.py` to actually matter, since a
  case-management route is exactly the kind of second route role differentiation was built for).
- **No persistent store.** `Alert`/`CaseEvent` are in-memory Pydantic objects. A real deployment needs
  a database (or at minimum a file-backed store) to keep case state across process restarts -- not
  built here.
- **No real case data.** Every example in this session's tests is synthetic, built directly in the
  test file. This package has never touched a real scored transaction.
- **A real architecture gap this work surfaced**: none of the 5 scoring services' `/score` requests or
  responses carry a transaction or account identifier today -- each takes only raw feature values and
  returns only a probability (see `alert_schema.py`'s module docstring). `alert_from_score_response()`
  requires the caller to supply `entity_ref` themselves because the service has no way to supply one.
  Fixing this at the service layer (adding an identifier field to each BP's request/response schema) is
  a prerequisite for ever wiring this package into a live service, and has not been done.
- **No RBAC applied.** `require_role()` exists in `_security.py` (added earlier this session) but
  nothing in this package or the live services uses it yet.

## Why this is a package, not a route, this session

Wiring this into 5 live FastAPI services, adding a persistent store, and adding an identifier field to
every service's request/response schema (a breaking API change for all 5) is substantially more surface
area than one batch of this session's work should responsibly cover alongside everything already
changed. This package is the real, tested foundation that wiring would build on -- shipped honestly as a
foundation, not described as a finished investigator-workflow feature.

## See it run

[`CASEWORK_WORKED_EXAMPLE.md`](CASEWORK_WORKED_EXAMPLE.md) is a real, captured transcript of this
package's own functions run end to end on one synthetic alert -- `/score`-shaped input through
investigator transitions to a JSON audit-reconstruction bundle. It demonstrates the plumbing above
working, not a live service.
