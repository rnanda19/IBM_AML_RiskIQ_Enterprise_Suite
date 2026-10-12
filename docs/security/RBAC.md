# Role-Based Access Control (RBAC)

Added 2026-10-12 to close `docs/audit/DEFECT_REGISTER.md`'s DEF-003 ("No RBAC at the API
layer"). This document is the authoritative permission matrix for the **Case Management
Service** (`src/aml_riskiq/serving/case_management_service.py`) -- the first (and, as of this
writing, only) live routes that actually enforce `require_role()`/`require_any_role()` from
`src/aml_riskiq/serving/_security.py`. BP1-BP5's scoring services still have only `/health`
(unauthenticated) and `/score` (any valid key, any role) -- there still isn't a second route
on any of them for a role distinction to protect, so this phase did not change their routes.

## The 4 platform roles

| Role (API-key prefix) | `_security.py` constant | Who |
|---|---|---|
| `analyst` | `ANALYST_ROLE` | Raises/reviews alerts from monitoring output; does not work cases |
| `investigator` | `INVESTIGATOR_ROLE` | Works assigned cases: notes, evidence, routine transitions |
| `compliance_officer` | `COMPLIANCE_OFFICER_ROLE` | Sign-off authority: escalation, closure, reconciliation, audit verification |
| `admin` | `ADMIN_ROLE` (`"admin"`) | Satisfies every role check -- see "administrator" note below |

**"administrator" in the business language is the existing `admin` key, not a 5th role
string.** `require_any_role()`'s admin bypass already existed before this phase (it is how
every BP1-BP5 `/score` key configured as `admin:...` has worked since role-aware keys were
first added) -- this phase reuses it rather than inventing a parallel superuser concept.

Configure roles via the shared `AML_RISKIQ_API_KEYS` environment variable, comma-separated
`role:key` pairs, e.g.:

```
AML_RISKIQ_API_KEYS=analyst:k1,investigator:k2,compliance_officer:k3,admin:k4
```

A bare key with no `role:` prefix gets the pre-existing default role `service` (backward
compatible with every key configured before role-aware keys existed) -- `service`-role keys
satisfy no route in the matrix below except where `service` is explicitly listed, so a BP1-5
`/score` key does NOT automatically get any case-management permission, and vice versa: these
are two independent key sets with independent roles, not a single tiered hierarchy.

## Permission matrix -- Case Management Service

| Route | Method | analyst | investigator | compliance_officer | admin |
|---|---|---|---|---|---|
| `/health` | GET | public (no auth) | public | public | public |
| `/alerts` | POST (create) | ✅ | ✅ | ✅ | ✅ |
| `/alerts` | GET (list) | ✅ | ✅ | ✅ | ✅ |
| `/alerts/{id}` | GET | ✅ | ✅ | ✅ | ✅ |
| `/alerts/{id}/assign` | POST | ❌ | ✅ | ✅ | ✅ |
| `/alerts/{id}/notes` | POST | ❌ | ✅ | ✅ | ✅ |
| `/alerts/{id}/evidence` | POST | ❌ | ✅ | ✅ | ✅ |
| `/alerts/{id}/evidence_export` | GET | ❌ | ✅ | ✅ | ✅ |
| `/alerts/{id}/transition` -> `assigned`/`under_review`/`unresolved` | POST | ❌ | ✅ | ✅ | ✅ |
| `/alerts/{id}/transition` -> `escalated`/`closed` | POST | ❌ | ❌ | ✅ | ✅ |
| `/alerts/{id}/integrity` | GET | ❌ | ❌ | ✅ | ✅ |
| `/reconciliation` | GET | ❌ | ❌ | ✅ | ✅ |
| `/metrics` | GET | public (no auth) | public | public | public |

`/health` and `/metrics` are deliberately never auth-gated -- same reasoning as every BP1-BP5
service: a liveness probe or scrape target must be reachable without a credential, and neither
route exposes case content (only DB-reachability / request counters, per `_security.py`'s own
documented scope).

## Why `/transition` isn't one static role check

Every other row in the table maps to exactly one `Depends(require_any_role(...))` on its
route. `/transition` cannot: the role it requires depends on the **request body**
(`to_status`), not the route itself -- `under_review`/`unresolved` only need `investigator`,
`escalated`/`closed` need `compliance_officer`. The route's own `Depends()` enforces the
coarse floor (`investigator` or `compliance_officer`, so `analyst` cannot even reach the
handler); the handler then calls `resolve_caller_role()` directly (a new `_security.py`
primitive added this phase specifically for this case) to make the body-dependent decision.
`tests/integration/case_management/test_case_management_service.py`'s
`test_transition_to_closed_rejected_for_investigator` is the test proving an investigator who
clears the route-level gate is still blocked at the target-status check.

## Negative-authorization behavior (what a disallowed caller actually gets)

- No `X-API-Key` header at all, closed mode -> **401**.
- Header present, matches no configured key -> **401**.
- Header present, matches a configured key whose role is not accepted by the route (and is
  not `admin`) -> **403**, with the caller's actual role and the accepted set named in the
  response body (never which OTHER keys would have worked).
- Open mode (`AML_RISKIQ_API_KEYS` unset) -> every route is a documented no-op, identical to
  every BP1-BP5 service's open-mode behavior -- see `_security.py`'s own module docstring and
  `SECURITY.md`'s "Fail-closed production gate" section. Set `AML_RISKIQ_REQUIRE_AUTH=true`
  to make a missing key set a hard startup failure instead.

## Identity model (honestly stated)

There is no user directory anywhere in this platform. Every audit record's `actor` field
(`CaseEvent.actor`, `CaseNote.actor`, `EvidenceReference.actor`) is the authenticated caller's
API-key fingerprint -- the same non-reversible 8-hex-char SHA-256 prefix `_security.py`
already uses for its own audit log, never a human name, and never the raw key (confirmed by
`test_requests_emit_structured_audit_log_lines`, which asserts the raw key string never
appears in an emitted audit record). Mapping keys to named users is real future work, not
fabricated here.

## See also

- `docs/architecture/INVESTIGATOR_WORKFLOW.md` -- the `casework` package's own design doc,
  updated this phase to reflect what is now actually wired in (store, routes, RBAC) vs. what
  still isn't.
- `docs/security/THREAT_MODEL.md` -- DEF-003's threat-model entry, updated to "mitigated".
- `docs/audit/DEFECT_REGISTER.md` -- DEF-003's full resolution record.
- `tests/integration/case_management/test_case_management_service.py` -- the automated
  security test suite this matrix is tested against (43 tests: every ✅/❌ cell above has at
  least one corresponding positive or negative test).
