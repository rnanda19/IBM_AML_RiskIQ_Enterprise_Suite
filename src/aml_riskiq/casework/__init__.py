"""Investigator case-management layer: a unified alert schema, case-lifecycle state machine,
cross-BP deduplication, reconciliation reporting, and evidence export.

HONEST SCOPE NOTE (read before using any of this): this is a new capability added this
session, built against this platform's real existing outputs (each scoring service's actual
/score response shape, documented in each BP's own service module) -- it is NOT wired into
any of the 5 live scoring services' routes, and no BP6 rollup behavior was changed. Building
that live wiring (a case-management API, a database-backed store, RBAC-protected routes using
src/aml_riskiq/serving/_security.py's require_role()) is real future work, not done here.
Everything in this package operates on Alert objects a caller constructs or passes in --
nothing here fabricates transaction data, scores, or case outcomes.

See docs/architecture/INVESTIGATOR_WORKFLOW.md for the full design rationale, including a
real, disclosed gap this work surfaced: none of the 5 scoring services' /score requests or
responses currently carry a transaction/account identifier (each takes only raw feature
values and returns only a probability) -- so alert_from_score_response() below requires the
caller to supply entity_ref/transaction_ref themselves; this package cannot invent one."""
