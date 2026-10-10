# Security Threat Model

Scope: the 5 FastAPI scoring services (BP1/BP2/BP3-rule/BP4/BP5) and their shared hardening module
(`src/aml_riskiq/serving/_security.py`). Out of scope: the notebooks/pipeline (not a running service),
GitHub Pages static report site (no application logic, see `pages.yml`), and anything below the
application layer (TLS termination, network segmentation, host OS hardening) -- those are a real
deployer's gateway/infra responsibility, not this codebase's, per `SECURITY.md`'s own scope note.

## Assets
- The trained model artifacts themselves (`.pkl`/rule `.json`) -- not secret, but integrity-sensitive
  (a swapped artifact would silently change every score).
- `/score` responses (a risk score + explanation for a submitted synthetic transaction) -- not real
  customer data in this project's own tests, but the application should behave as if it were.
- API keys (`AML_RISKIQ_API_KEYS`) -- credential material.
- Audit log stream (who called what, when, from where).

## Threats considered, and this platform's real current posture

| Threat | Mitigation in place | Real gap |
|---|---|---|
| Unauthenticated access to `/score` | `require_api_key` dependency, constant-time compare | Open mode is the *default* (documented) -- `AML_RISKIQ_REQUIRE_AUTH` makes this fail-closed, but only if a deployer sets it |
| Credential stuffing / brute-force on `/score` | Rate limiting (`slowapi`, 60/min default) + 401 on bad key | No account lockout, no IP-reputation check -- rate limiting alone is the only brake |
| Timing side-channel on key comparison | `secrets.compare_digest` | None known |
| API key leaked via logs | Only an 8-char SHA-256 fingerprint is ever logged, never the raw key | None known |
| A caller with a valid key doing something only a different role should do | `require_role()` primitive exists | **Not applied to any route today** -- every valid key currently has identical access to `/score` on its service (see `docs/audit/DEFECT_REGISTER.md` DEF-003) |
| Malformed / oversized request body crashing the service | Pydantic request-model validation (FastAPI default) | No explicit request-size limit configured at the application layer -- relies on a reverse proxy/gateway in front, per this module's own scope note |
| A compromised/rogue model artifact silently swapped in | `/health` exposes a live-recomputed SHA-256 + mtime of the loaded artifact (`MODEL_REGISTRY.md`) so a caller/monitor CAN detect drift from the registry's recorded hash | Nothing *automatically* alerts on a mismatch today -- detection requires a caller or monitor to actually compare against `MODEL_REGISTRY.md` |
| Denial of service via request flood | Rate limiting bounds a single caller's rate | No protection against a distributed flood across many IPs -- that is explicitly a gateway/CDN concern, not this module's |
| Dependency supply-chain vulnerability | CodeQL + Dependabot wired into CI (`.github/workflows/codeql.yml`, `.github/dependabot.yml`) | None known beyond standard CI-cadence lag |
| Container escape / privilege escalation inside a compromised container | **Fixed this session**: all 5 service Dockerfiles now run as a non-root `app` user | Base image (`python:3.11-slim`) vulnerabilities still depend on Dependabot's base-image update cadence |
| `/health` or `/metrics` leaking sensitive data to an unauthenticated caller | Both are deliberately unauthenticated by design (liveness-probe/scrape-target requirement) but checked to expose only model-registry metadata and request counts, never transaction content | None known -- re-verify this invariant on any future addition to either route |

## Residual risks (explicitly not mitigated by this codebase)

- **TLS termination, network segmentation, host hardening**: the deployer's gateway/reverse-proxy
  responsibility, not reimplemented here (see `_security.py`'s own "HONEST SCOPE NOTE").
- **Open mode as the default**: a deployer who does not explicitly set `AML_RISKIQ_API_KEYS` and
  `AML_RISKIQ_REQUIRE_AUTH=true` gets an unauthenticated service with only a startup warning, by design
  (keeps local dev/CI friction-free) -- this is a real, deliberate trade-off, not an oversight, but it
  means secure-by-default is opt-in, not automatic.
- **Role differentiation**: `require_role()` exists but protects nothing yet (DEF-003).
- **Live artifact-integrity alerting**: `/health`'s fingerprint makes tampering *detectable*, not
  *automatically alerted on*.

## Review cadence
Re-review this document whenever a new route is added to any service, when `_security.py` changes, or
at minimum alongside any `SECURITY.md` update.
